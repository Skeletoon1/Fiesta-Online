"""Tests for the Fiesta SHN toolkit.

Run with:  python -m pytest tests/      (or just: python fiesta_shn.py selftest)
"""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fiesta_shn as fs  # noqa: E402


def make_table():
    t = fs.ShnTable()
    t.crypt_header = bytes(range(32))
    t.header = 0xDEADBEEF
    t.encoding = "utf-8"
    t.columns = [
        fs.Column("ID", 3, 4),        # uint32
        fs.Column("Level", 1, 1),     # byte
        fs.Column("Signed8", 20, 1),  # sbyte
        fs.Column("U16", 2, 2),       # uint16
        fs.Column("I16", 13, 2),      # int16
        fs.Column("I32", 22, 4),      # int32
        fs.Column("Rate", 5, 4),      # float
        fs.Column("Name", 9, 16),     # string[16]
    ]
    t.rows = [
        [1, 10, -1, 5, -3, -5, 3.5, "Sword"],
        [2, 255, 127, 65535, 32767, 2147483647, 0.125, "Bow of Doom"],
        [4294967295, 0, -128, 0, -32768, -2147483648, -1.0, ""],
    ]
    return t


# -- cipher -----------------------------------------------------------------
def test_cipher_is_self_inverse():
    sample = bytes(range(256)) * 5 + b"\x01\x02\x03"
    assert fs.shn_crypt(fs.shn_crypt(sample)) == sample


def test_cipher_actually_transforms():
    sample = b"hello world" * 4
    assert fs.shn_crypt(sample) != sample


def test_cipher_data_independent():
    # XOR-ing zeros yields the raw keystream.
    assert fs.shn_crypt(b"\x00" * 100) == bytes(fs._keystream(100))


def test_cipher_empty():
    assert fs.shn_crypt(b"") == b""


# -- structural round-trip --------------------------------------------------
def test_encode_decode_roundtrip():
    t = make_table()
    raw = fs.encode_bytes(t)
    back = fs.decode_bytes(raw, "utf-8")
    assert back.header == t.header
    assert back.crypt_header == t.crypt_header
    assert back.rows == t.rows
    assert [(c.name, c.type, c.length) for c in back.columns] == \
           [(c.name, c.type, c.length) for c in t.columns]


def test_reencode_is_byte_identical():
    t = make_table()
    raw = fs.encode_bytes(t)
    back = fs.decode_bytes(raw, "utf-8")
    assert fs.encode_bytes(back) == raw


def test_declared_length_matches_file_size():
    raw = fs.encode_bytes(make_table())
    assert struct.unpack("<I", raw[32:36])[0] == len(raw)


def test_trailing_bytes_preserved():
    t = make_table()
    t.trailing = b"\xde\xad\xbe\xef"
    raw = fs.encode_bytes(t)
    back = fs.decode_bytes(raw, "utf-8")
    assert back.trailing == t.trailing
    assert fs.encode_bytes(back) == raw


# -- schema -----------------------------------------------------------------
def test_schema_roundtrip():
    t = make_table()
    schema = fs.schema_from_table(t, "Test.shn")
    t2 = fs.table_from_schema(schema)
    t2.rows = t.rows
    assert fs.encode_bytes(t2) == fs.encode_bytes(t)


# -- CSV + disk workflow ----------------------------------------------------
def test_csv_disk_roundtrip(tmp_path):
    t = make_table()
    shn = tmp_path / "Item.shn"
    shn.write_bytes(fs.encode_bytes(t))

    import argparse
    dec = argparse.Namespace(input=str(shn), out=str(tmp_path / "Item"),
                             encoding="utf-8", force=False)
    assert fs.cmd_decode(dec) == 0

    enc = argparse.Namespace(input=str(tmp_path / "Item.csv"),
                             schema=str(tmp_path / "Item.schema.json"),
                             out=str(tmp_path / "Item2.shn"),
                             encoding=None, force=False)
    assert fs.cmd_encode(enc) == 0

    assert (tmp_path / "Item.shn").read_bytes() == (tmp_path / "Item2.shn").read_bytes()


def test_encode_makes_backup(tmp_path):
    t = make_table()
    shn = tmp_path / "Item.shn"
    shn.write_bytes(fs.encode_bytes(t))

    import argparse
    fs.cmd_decode(argparse.Namespace(input=str(shn), out=str(tmp_path / "Item"),
                                     encoding="utf-8", force=False))
    fs.cmd_encode(argparse.Namespace(input=str(tmp_path / "Item.csv"),
                                     schema=str(tmp_path / "Item.schema.json"),
                                     out=str(shn), encoding=None, force=False))
    assert (tmp_path / "Item.shn.bak").exists()


def test_csv_handles_special_characters(tmp_path):
    t = make_table()
    t.rows[0][-1] = 'a, "b", c'  # commas + quotes in a string field
    shn = tmp_path / "Sp.shn"
    shn.write_bytes(fs.encode_bytes(t))

    import argparse
    fs.cmd_decode(argparse.Namespace(input=str(shn), out=str(tmp_path / "Sp"),
                                     encoding="utf-8", force=False))
    rows = fs.read_csv_rows(str(tmp_path / "Sp.csv"), t.columns)
    assert rows[0][-1] == 'a, "b", c'


# -- error handling ---------------------------------------------------------
def test_too_small_file_rejected():
    with pytest.raises(ValueError):
        fs.decode_bytes(b"\x00" * 10)


def test_string_overflow_rejected():
    t = make_table()
    t.rows[0][-1] = "x" * 100  # longer than the 16-byte Name field
    with pytest.raises(ValueError):
        fs.encode_bytes(t)


def test_float_roundtrips_exactly():
    t = make_table()
    t.rows = [[0, 0, 0, 0, 0, 0, v, ""] for v in (1.1, 3.14159, 1e-7, -2.5e9)]
    raw = fs.encode_bytes(t)
    assert fs.encode_bytes(fs.decode_bytes(raw, "utf-8")) == raw
