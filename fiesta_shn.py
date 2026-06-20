#!/usr/bin/env python3
"""
Fiesta Online SHN toolkit
=========================

A single-file, dependency-free (Python 3 standard library only) tool for working
with the .shn data tables used by Fiesta Online / ShineProject servers
(C:\\FiestaServer\\... on a typical Windows install).

It can:

    decode   .shn  -> .csv  +  .schema.json   (and auto-verifies round-trip safety)
    encode   .csv  +  .schema.json  -> .shn    (backs up + verifies before replacing)
    verify   .shn                              (decode then re-encode, compare bytes)
    info     .shn                              (print header / column summary)
    selftest                                   (run built-in correctness checks)

Why a schema file?
    The .csv holds the editable data. The .schema.json holds everything needed to
    rebuild a *byte-identical* .shn: the original 32-byte crypt header, the file
    "header" id, the exact column types/lengths and the text encoding. Edit the
    CSV, keep the schema next to it, re-encode. Done.

Safety model:
    - `decode` always re-encodes in memory and compares against the original file.
      It tells you plainly whether the file is ROUND-TRIP SAFE before you edit it.
    - `encode` never blindly clobbers a live file: it writes to a temp file, decodes
      it back to confirm it parses, makes a .bak of any existing target, and only
      then moves the new file into place.

The cipher and file format are reimplemented from the open-source Zepheus
ShineTableParser (TakenBerry/Fiesta_Utils, FileCrypto.cs / SHNFile.cs /
SHNColumn.cs / SHNReader.cs / SHNWriter.cs).
"""

import argparse
import csv
import json
import os
import struct
import sys

# ---------------------------------------------------------------------------
# Cipher
# ---------------------------------------------------------------------------
#
# Direct port of Zepheus FileCrypto.Crypt. The keystream depends only on the
# byte position and the body length -- never on the data itself -- so the
# function is its own inverse: encrypt and decrypt are the same operation.
#
#   byte num = (byte)length;
#   for (int i = length - 1; i >= 0; i--) {
#       data[i] = (byte)(data[i] ^ num);
#       byte n = (byte)i;
#       n = (byte)(n & 15);
#       n = (byte)(n + 0x55);
#       n = (byte)(n ^ ((byte)(((byte)i) * 11)));
#       n = (byte)(n ^ num);
#       n = (byte)(n ^ 170);
#       num = n;
#   }


def _keystream(length):
    """Return the `length`-byte keystream used by FileCrypto.Crypt."""
    ks = bytearray(length)
    num = length & 0xFF
    for i in range(length - 1, -1, -1):
        ks[i] = num
        n = i & 15
        n = (n + 0x55) & 0xFF
        n ^= ((i & 0xFF) * 11) & 0xFF
        n ^= num
        n ^= 0xAA
        num = n & 0xFF
    return ks


def shn_crypt(data):
    """Encrypt or decrypt an SHN body (same operation). Returns bytes."""
    data = bytes(data)
    n = len(data)
    if n == 0:
        return b""
    ks = _keystream(n)
    a = int.from_bytes(data, "little")
    b = int.from_bytes(ks, "little")
    return (a ^ b).to_bytes(n, "little")


# ---------------------------------------------------------------------------
# Column type table  (TypeByte -> behaviour)
# ---------------------------------------------------------------------------
#
# Fixed-size scalar types: struct format + byte size.
FIXED_TYPES = {
    1:  ("<B", 1),   # byte
    12: ("<B", 1),   # byte
    16: ("<B", 1),   # byte  (0x10)
    20: ("<b", 1),   # sbyte (0x14)
    2:  ("<H", 2),   # uint16
    13: ("<h", 2),   # int16 (0x0D)
    21: ("<h", 2),   # int16 (0x15)
    3:  ("<I", 4),   # uint32
    11: ("<I", 4),   # uint32 (0x0B)
    18: ("<I", 4),   # uint32 (0x12)
    27: ("<I", 4),   # uint32 (0x1B)
    22: ("<i", 4),   # int32  (0x16)
    5:  ("<f", 4),   # float
}
FLOAT_TYPES = {5}
STRING_TYPES = {9, 24}        # fixed-width string, width = column length (0x18)
VAR_STRING_TYPES = {26}       # variable-length string (0x1A)

ALL_KNOWN_TYPES = set(FIXED_TYPES) | STRING_TYPES | VAR_STRING_TYPES


def type_name(t):
    if t in FLOAT_TYPES:
        return "float"
    if t in STRING_TYPES:
        return "string"
    if t in VAR_STRING_TYPES:
        return "varstring"
    if t in FIXED_TYPES:
        fmt = FIXED_TYPES[t][0]
        return {
            "<B": "uint8", "<b": "int8", "<H": "uint16", "<h": "int16",
            "<I": "uint32", "<i": "int32",
        }[fmt]
    return "unknown"


# ---------------------------------------------------------------------------
# Low-level reader / writer over an in-memory buffer
# ---------------------------------------------------------------------------
class Reader:
    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def read(self, n):
        end = self.pos + n
        if end > len(self.buf):
            raise EOFError(
                "Unexpected end of SHN body at offset %d (wanted %d bytes)"
                % (self.pos, n)
            )
        b = self.buf[self.pos:end]
        self.pos = end
        return b

    def scalar(self, fmt, size):
        return struct.unpack(fmt, self.read(size))[0]

    def u16(self):
        return self.scalar("<H", 2)

    def u32(self):
        return self.scalar("<I", 4)

    def i32(self):
        return self.scalar("<i", 4)

    def padded_string(self, length, encoding):
        raw = self.read(length)
        nul = raw.find(b"\x00")
        if nul == -1:
            nul = length
        return raw[:nul].decode(encoding)


class Writer:
    def __init__(self):
        self._parts = []

    def write(self, b):
        self._parts.append(b)

    def scalar(self, fmt, value):
        self.write(struct.pack(fmt, value))

    def u16(self, v):
        self.scalar("<H", v)

    def i16(self, v):
        self.scalar("<h", v)

    def u32(self, v):
        self.scalar("<I", v)

    def padded_string(self, s, length, encoding):
        data = s.encode(encoding)
        if len(data) > length:
            raise ValueError(
                "string %r encodes to %d bytes, exceeds field width %d"
                % (s, len(data), length)
            )
        self.write(data + b"\x00" * (length - len(data)))

    def getvalue(self):
        return b"".join(self._parts)


# ---------------------------------------------------------------------------
# In-memory SHN model
# ---------------------------------------------------------------------------
class Column:
    __slots__ = ("name", "type", "length")

    def __init__(self, name, type_, length):
        self.name = name
        self.type = type_
        self.length = length


class ShnTable:
    def __init__(self):
        self.crypt_header = b"\x00" * 32   # 32 opaque bytes, preserved verbatim
        self.header = 0                    # uint32 "header" id
        self.columns = []                  # list[Column]
        self.rows = []                     # list[list[value]]
        self.encoding = "utf-8"
        self.trailing = b""                # any bytes after the declared body
        # Values kept for reporting; recomputed on encode:
        self.declared_record_count = None
        self.declared_default_record_length = None

    # -- derived ---------------------------------------------------------
    def default_record_length(self):
        """2 (rowLength field) + sum of all column lengths -- matches Zepheus."""
        return 2 + sum(c.length for c in self.columns)


# ---------------------------------------------------------------------------
# Decoding:  raw .shn bytes  ->  ShnTable
# ---------------------------------------------------------------------------
def decode_bytes(raw, encoding="utf-8"):
    if len(raw) < 36:
        raise ValueError("File too small to be a valid SHN (%d bytes)" % len(raw))

    t = ShnTable()
    t.encoding = encoding
    t.crypt_header = raw[0:32]
    total_len = struct.unpack("<I", raw[32:36])[0]
    body_len = total_len - 36
    if body_len < 0:
        raise ValueError("Corrupt SHN: declared length %d < 36" % total_len)
    if 36 + body_len > len(raw):
        raise ValueError(
            "Corrupt/truncated SHN: declared body needs %d bytes but file has %d"
            % (36 + body_len, len(raw))
        )

    t.trailing = raw[36 + body_len:]
    body = shn_crypt(raw[36:36 + body_len])

    r = Reader(body)
    t.header = r.u32()
    record_count = r.u32()
    default_record_length = r.u32()
    column_count = r.u32()
    t.declared_record_count = record_count
    t.declared_default_record_length = default_record_length

    # Columns
    for _ in range(column_count):
        name = r.padded_string(48, encoding)
        type_byte = r.u32() & 0xFF
        length = r.i32()
        t.columns.append(Column(name, type_byte, length))

    computed_drl = t.default_record_length()
    if computed_drl != default_record_length:
        # Not fatal -- we keep going and the round-trip verify will report it --
        # but warn loudly because it means the column lengths look inconsistent.
        sys.stderr.write(
            "WARNING: default record length mismatch (file says %d, columns sum to %d)\n"
            % (default_record_length, computed_drl)
        )

    # Rows
    drl = default_record_length
    for _ in range(record_count):
        row_length = r.u16()
        values = []
        for c in t.columns:
            ty = c.type
            if ty in FIXED_TYPES:
                fmt, size = FIXED_TYPES[ty]
                values.append(r.scalar(fmt, size))
            elif ty in STRING_TYPES:
                values.append(r.padded_string(c.length, encoding))
            elif ty in VAR_STRING_TYPES:
                values.append(r.padded_string(row_length - drl + 1, encoding))
            else:
                raise ValueError("Unknown column type %d (column %r)" % (ty, c.name))
        t.rows.append(values)

    return t


# ---------------------------------------------------------------------------
# Encoding:  ShnTable  ->  raw .shn bytes
# ---------------------------------------------------------------------------
def encode_bytes(t):
    enc = t.encoding
    drl = t.default_record_length()

    body = Writer()
    body.u32(t.header & 0xFFFFFFFF)
    body.u32(len(t.rows) & 0xFFFFFFFF)
    body.u32(drl & 0xFFFFFFFF)
    body.u32(len(t.columns) & 0xFFFFFFFF)

    # Columns
    for c in t.columns:
        body.padded_string(c.name, 48, enc)
        body.u32(c.type & 0xFFFFFFFF)
        body.u32(c.length & 0xFFFFFFFF)

    # Rows
    for ridx, row in enumerate(t.rows):
        if len(row) != len(t.columns):
            raise ValueError(
                "Row %d has %d values but there are %d columns"
                % (ridx, len(row), len(t.columns))
            )
        rowbuf = Writer()
        unk_length = 0
        for c, value in zip(t.columns, row):
            ty = c.type
            try:
                if ty in FIXED_TYPES:
                    fmt, _ = FIXED_TYPES[ty]
                    if ty in FLOAT_TYPES:
                        rowbuf.scalar(fmt, float(value))
                    else:
                        rowbuf.scalar(fmt, int(value))
                elif ty in STRING_TYPES:
                    rowbuf.padded_string(str(value), c.length, enc)
                elif ty in VAR_STRING_TYPES:
                    s = str(value)
                    unk_length += len(s)
                    rowbuf.padded_string(s, len(s.encode(enc)) + 1, enc)
                else:
                    raise ValueError("Unknown column type %d" % ty)
            except (struct.error, ValueError) as exc:
                raise ValueError(
                    "Row %d, column %r (%s): %s"
                    % (ridx, c.name, type_name(ty), exc)
                )
        row_length = drl + unk_length
        body.i16(row_length)
        body.write(rowbuf.getvalue())

    plain = body.getvalue()
    encrypted = shn_crypt(plain)

    out = Writer()
    out.write(t.crypt_header)
    out.u32((len(encrypted) + 36) & 0xFFFFFFFF)
    out.write(encrypted)
    out.write(t.trailing)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Schema (JSON) <-> ShnTable
# ---------------------------------------------------------------------------
def schema_from_table(t, source_file=None):
    return {
        "format": "fiesta-shn",
        "version": 1,
        "source_file": source_file,
        "encoding": t.encoding,
        "crypt_header_hex": t.crypt_header.hex(),
        "header": int(t.header),
        "default_record_length": t.default_record_length(),
        "record_count": len(t.rows),
        "trailing_hex": t.trailing.hex(),
        "columns": [
            {"name": c.name, "type": c.type, "type_name": type_name(c.type),
             "length": c.length}
            for c in t.columns
        ],
    }


def table_from_schema(schema):
    t = ShnTable()
    t.encoding = schema.get("encoding", "utf-8")
    t.crypt_header = bytes.fromhex(schema["crypt_header_hex"])
    if len(t.crypt_header) != 32:
        raise ValueError("crypt_header_hex must decode to exactly 32 bytes")
    t.header = int(schema["header"])
    t.trailing = bytes.fromhex(schema.get("trailing_hex", ""))
    for col in schema["columns"]:
        t.columns.append(Column(col["name"], int(col["type"]), int(col["length"])))
    return t


# ---------------------------------------------------------------------------
# CSV <-> rows
# ---------------------------------------------------------------------------
def write_csv(path, t):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c.name for c in t.columns])
        for row in t.rows:
            w.writerow([format_value(c.type, v) for c, v in zip(t.columns, row)])


def read_csv_rows(path, columns):
    """Read data rows from CSV (header row is skipped; column order = schema order)."""
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            next(reader)  # discard header row
        except StopIteration:
            return []
        rows = []
        for lineno, raw in enumerate(reader, start=2):
            if not raw:
                continue
            if len(raw) != len(columns):
                raise ValueError(
                    "CSV line %d has %d fields, expected %d (one per column)"
                    % (lineno, len(raw), len(columns))
                )
            rows.append([parse_value(c.type, cell) for c, cell in zip(columns, raw)])
        return rows


def format_value(type_, value):
    if type_ in FLOAT_TYPES:
        # repr() of a float round-trips exactly through text.
        return repr(float(value))
    return value


def parse_value(type_, cell):
    if type_ in FIXED_TYPES and type_ not in FLOAT_TYPES:
        return int(cell)
    if type_ in FLOAT_TYPES:
        return float(cell)
    return cell  # strings


# ---------------------------------------------------------------------------
# High-level commands
# ---------------------------------------------------------------------------
def _verify_roundtrip(raw, encoding):
    """Decode then re-encode; return (ok, table, message)."""
    t = decode_bytes(raw, encoding)
    rebuilt = encode_bytes(t)
    if rebuilt == raw:
        return True, t, "byte-identical"
    # find first difference for a helpful message
    n = min(len(rebuilt), len(raw))
    diff = next((i for i in range(n) if rebuilt[i] != raw[i]), n)
    msg = ("re-encoded file differs (original %d bytes, rebuilt %d bytes, "
           "first difference at offset %d)" % (len(raw), len(rebuilt), diff))
    return False, t, msg


def cmd_decode(args):
    with open(args.input, "rb") as f:
        raw = f.read()

    ok, t, msg = _verify_roundtrip(raw, args.encoding)

    base = args.out if args.out else os.path.splitext(args.input)[0]
    csv_path = base + ".csv"
    schema_path = base + ".schema.json"

    write_csv(csv_path, t)
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_from_table(t, os.path.basename(args.input)), f, indent=2)

    print("Decoded %s" % args.input)
    print("  -> %s  (%d records, %d columns)"
          % (csv_path, len(t.rows), len(t.columns)))
    print("  -> %s" % schema_path)
    if ok:
        print("  Round-trip: SAFE (%s) -- edits will re-encode cleanly." % msg)
    else:
        print("  Round-trip: UNSAFE -- %s" % msg)
        if args.encoding != "latin-1":
            print("  Hint: try  --encoding latin-1  for a guaranteed lossless "
                  "round-trip on this file.")
        if not args.force:
            return 1
    return 0


def cmd_encode(args):
    schema_path = args.schema or (os.path.splitext(args.input)[0] + ".schema.json")
    if not os.path.exists(schema_path):
        sys.stderr.write("ERROR: schema not found: %s\n" % schema_path)
        return 1
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    t = table_from_schema(schema)
    if args.encoding:
        t.encoding = args.encoding
    t.rows = read_csv_rows(args.input, t.columns)

    raw = encode_bytes(t)

    # Sanity: the file we just built must decode back to the same logical data.
    check = decode_bytes(raw, t.encoding)
    if len(check.rows) != len(t.rows) or len(check.columns) != len(t.columns):
        sys.stderr.write("ERROR: internal check failed -- refusing to write.\n")
        return 1

    out_path = args.out or (os.path.splitext(args.input)[0] + ".shn")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(raw)

    if os.path.exists(out_path):
        bak_path = out_path + ".bak"
        if os.path.exists(bak_path) and not args.force:
            sys.stderr.write(
                "ERROR: backup %s already exists; pass --force to overwrite it.\n"
                % bak_path
            )
            os.remove(tmp_path)
            return 1
        os.replace(out_path, bak_path)
        print("Backed up existing file -> %s" % bak_path)

    os.replace(tmp_path, out_path)
    print("Encoded %s -> %s  (%d records, %d columns, %d bytes)"
          % (args.input, out_path, len(t.rows), len(t.columns), len(raw)))
    return 0


def cmd_verify(args):
    with open(args.input, "rb") as f:
        raw = f.read()
    ok, t, msg = _verify_roundtrip(raw, args.encoding)
    print("%s: %s (%s) -- %d records, %d columns"
          % (args.input, "SAFE" if ok else "UNSAFE", msg,
             len(t.rows), len(t.columns)))
    return 0 if ok else 1


def cmd_info(args):
    with open(args.input, "rb") as f:
        raw = f.read()
    t = decode_bytes(raw, args.encoding)
    print("File:           %s" % args.input)
    print("Size:           %d bytes" % len(raw))
    print("Crypt header:   %s" % t.crypt_header.hex())
    print("Header id:      %d" % t.header)
    print("Records:        %d (declared %s)"
          % (len(t.rows), t.declared_record_count))
    print("Columns:        %d" % len(t.columns))
    print("Record length:  %d (declared %s)"
          % (t.default_record_length(), t.declared_default_record_length))
    if t.trailing:
        print("Trailing bytes: %d" % len(t.trailing))
    print()
    print("  %-40s %-10s %s" % ("name", "type", "len"))
    print("  %-40s %-10s %s" % ("-" * 40, "-" * 10, "---"))
    for c in t.columns:
        print("  %-40s %-10s %d" % (c.name[:40], type_name(c.type), c.length))
    return 0


# ---------------------------------------------------------------------------
# Built-in self-test (no real .shn file required)
# ---------------------------------------------------------------------------
def cmd_selftest(_args):
    failures = 0

    def check(name, cond):
        nonlocal failures
        status = "ok" if cond else "FAIL"
        if not cond:
            failures += 1
        print("  [%s] %s" % (status, name))

    # 1. Cipher is its own inverse and data-independent.
    sample = bytes(range(256)) * 3 + b"\x00\x01\x02"
    check("cipher round-trips", shn_crypt(shn_crypt(sample)) == sample)
    check("cipher changes data", shn_crypt(sample) != sample)
    check("keystream independent of data",
          shn_crypt(b"\x00" * 64) == _keystream(64))

    # 2. Build a synthetic table, encode, decode, compare.
    t = ShnTable()
    t.crypt_header = bytes(range(32))
    t.header = 0xDEADBEEF
    t.encoding = "utf-8"
    t.columns = [
        Column("ID", 3, 4),         # uint32
        Column("Level", 1, 1),      # byte
        Column("Damage", 5, 4),     # float
        Column("Signed", 22, 4),    # int32
        Column("Name", 9, 16),      # string[16]
    ]
    t.rows = [
        [1, 10, 3.5, -5, "Sword"],
        [2, 99, 0.125, 2147483647, "Bow of Doom"],
        [4294967295, 255, -1.0, -2147483648, ""],
    ]
    raw = encode_bytes(t)
    back = decode_bytes(raw, "utf-8")
    check("encode/decode preserves header", back.header == t.header)
    check("encode/decode preserves crypt header",
          back.crypt_header == t.crypt_header)
    check("encode/decode preserves row count", len(back.rows) == len(t.rows))
    check("encode/decode preserves columns",
          [(c.name, c.type, c.length) for c in back.columns]
          == [(c.name, c.type, c.length) for c in t.columns])
    check("encode/decode preserves data", back.rows == t.rows)
    check("re-encode is byte-identical", encode_bytes(back) == raw)
    check("file size matches declared length",
          struct.unpack("<I", raw[32:36])[0] == len(raw))

    print()
    if failures:
        print("SELFTEST FAILED (%d checks failed)" % failures)
        return 1
    print("SELFTEST PASSED")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="fiesta_shn",
        description="Decode / edit / re-encode Fiesta Online .shn data tables.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    enc_help = "text encoding for strings (default utf-8; latin-1 is lossless)"

    d = sub.add_parser("decode", help="decode a .shn into .csv + .schema.json")
    d.add_argument("input")
    d.add_argument("--out", help="output base path (default: input without .shn)")
    d.add_argument("--encoding", default="utf-8", help=enc_help)
    d.add_argument("--force", action="store_true",
                   help="still write output even if round-trip is unsafe")
    d.set_defaults(func=cmd_decode)

    e = sub.add_parser("encode", help="encode a .csv (+ .schema.json) back to .shn")
    e.add_argument("input", help="the .csv file")
    e.add_argument("--schema", help="schema json (default: input base + .schema.json)")
    e.add_argument("--out", help="output .shn path (default: input base + .shn)")
    e.add_argument("--encoding", default=None,
                   help="override encoding from schema")
    e.add_argument("--force", action="store_true",
                   help="overwrite an existing .bak backup")
    e.set_defaults(func=cmd_encode)

    v = sub.add_parser("verify", help="check that a .shn round-trips byte-for-byte")
    v.add_argument("input")
    v.add_argument("--encoding", default="utf-8", help=enc_help)
    v.set_defaults(func=cmd_verify)

    i = sub.add_parser("info", help="print header and column summary")
    i.add_argument("input")
    i.add_argument("--encoding", default="utf-8", help=enc_help)
    i.set_defaults(func=cmd_info)

    s = sub.add_parser("selftest", help="run built-in correctness checks")
    s.set_defaults(func=cmd_selftest)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
