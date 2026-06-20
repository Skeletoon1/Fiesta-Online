# Fiesta SHN Toolkit

A small, dependency-free toolkit for working with the `.shn` data tables that
drive a Fiesta Online / ShineProject server (the files under
`C:\FiestaServer\...`). It turns the **decode → edit → re-encode** grind into a
repeatable, verified command instead of re-deriving the SHN cipher from scratch
every time you want to tweak an item, a drop, or build a perfect set.

Everything is one file — `fiesta_shn.py` — using only the Python 3 standard
library. No `pip install`, no internet, nothing to set up beyond Python itself.

## What it does

| Command  | Purpose |
|----------|---------|
| `decode` | `.shn` → `.csv` + `.schema.json`, and tells you if the file is round-trip safe |
| `encode` | `.csv` + `.schema.json` → `.shn`, with automatic backup and verification |
| `verify` | re-encode a `.shn` in memory and confirm it matches byte-for-byte |
| `info`   | print the header, column types, and record count |
| `selftest` | run built-in correctness checks (no real file needed) |

## The two output files

When you `decode`, you get **two** files:

- **`Name.csv`** — the editable data. Open it in Excel, LibreOffice, or any text
  editor. One row per record, one column per field.
- **`Name.schema.json`** — the blueprint needed to rebuild a byte-identical
  `.shn`: the original 32-byte crypt header, the file's header id, every column's
  exact type and length, and the text encoding.

Edit the CSV, keep the schema next to it, run `encode`. That's the whole loop.

## Quick start (Windows)

1. Install Python 3 from <https://www.python.org/downloads/> and tick
   **"Add Python to PATH"** during setup.
2. Copy this folder somewhere handy (e.g. `C:\FiestaTools\`).

Then, from a Command Prompt:

```bat
:: Always work on a COPY of your server files first.
python fiesta_shn.py decode C:\FiestaServer\ShineTable\Item.shn

:: ...edit Item.csv...

python fiesta_shn.py encode Item.csv
:: -> writes Item.shn, backing up any existing Item.shn to Item.shn.bak
```

Prefer not to type? Use the drag-and-drop helpers in the [`windows`](windows/)
folder: drop a `.shn` onto `decode.bat`, or a `.csv` onto `encode.bat`.

## Typical workflow

```bat
:: 1. Decode (this also verifies the file is safe to edit)
python fiesta_shn.py decode Item.shn

:: 2. Edit Item.csv in your spreadsheet / editor

:: 3. Encode back. The original is saved as Item.shn.bak automatically.
python fiesta_shn.py encode Item.csv --out Item.shn

:: 4. (optional) double-check the result
python fiesta_shn.py verify Item.shn
```

To put the file back on the server, copy the new `Item.shn` over the live one
(keep your own backup of the original too).

## Round-trip safety

This is the part that makes the toolkit trustworthy:

- `decode` immediately re-encodes the file in memory and compares it to the
  original. It prints **`Round-trip: SAFE`** only when the rebuild is
  byte-for-byte identical. If it can't guarantee that, it prints **`UNSAFE`**
  and a hint, and (unless you pass `--force`) exits without writing — so you
  never edit a file the tool can't faithfully put back together.
- `encode` writes to a temporary file, decodes it back to confirm it parses,
  backs up any existing target to `.bak`, and only then moves the new file into
  place.

If a file decodes as `UNSAFE` under the default UTF-8 encoding, try
`--encoding latin-1`, which maps every byte 1:1 and is lossless for any content:

```bat
python fiesta_shn.py decode Strange.shn --encoding latin-1
python fiesta_shn.py encode Strange.csv --encoding latin-1
```

(The encoding you choose is recorded in the schema, so `encode` uses the right
one automatically unless you override it.)

## Encoding notes

- Default is **UTF-8**, matching the reference ShineTableParser implementation.
- For files with European or Korean text that don't round-trip under UTF-8, try
  `--encoding cp1252`, `--encoding euc-kr`, or the always-lossless
  `--encoding latin-1`.
- Whatever encoding makes `decode` report **SAFE** is the right one for that file.

## Column types

The tool understands every SHN column type used by the format: unsigned/signed
8/16/32-bit integers, 32-bit floats, fixed-width strings, and variable-length
strings. Run `info` on any file to see its layout:

```bat
python fiesta_shn.py info Item.shn
```

## Safety reminders

- **Always edit a copy.** Decode from a working copy, not directly from your live
  `C:\FiestaServer` files. Keep the `.shn.bak` files the tool creates.
- **Don't change column structure in the CSV.** Add/remove/reorder *rows* freely;
  the columns are defined by the schema. (Changing field widths or types means
  editing the schema deliberately — possible, but know what you're doing.)
- **Verify before deploying.** `verify` (or the SAFE line from `decode`) is your
  green light.

## How it works

The format and cipher are reimplemented from the open-source Zepheus
ShineTableParser (`FileCrypto.cs`, `SHNFile.cs`, `SHNColumn.cs`, `SHNReader.cs`,
`SHNWriter.cs`). An `.shn` file is a 32-byte crypt header, a 4-byte total length,
then an encrypted body containing a small header, the column definitions, and the
records. The body cipher is a position-keyed stream cipher whose keystream
depends only on byte position and body length — never on the data — which is why
encrypt and decrypt are the same operation and why exact round-trips are
achievable.

## Development

```bash
python3 fiesta_shn.py selftest   # correctness checks
python3 -m pytest tests/         # full test suite (if pytest is installed)
```
