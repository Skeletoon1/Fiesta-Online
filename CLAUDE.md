# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

A single-file, dependency-free Python toolkit (`fiesta_shn.py`, stdlib only) for
reading and writing the `.shn` data tables used by a **Fiesta Online /
ShineProject** private server (the files under `C:\FiestaServer\...`). It exists
so that editing game data (items, drops, mobs, vendors, etc.) is a repeatable,
**verified** decode → edit → re-encode loop instead of re-deriving the SHN cipher
each time.

The cipher and format are faithfully reimplemented from the open-source Zepheus
ShineTableParser. An `.shn` is a 32-byte crypt header, a 4-byte total length, then
an encrypted body (header + column definitions + records).

## The tool

Run with `python fiesta_shn.py <command>` (use `python3` inside WSL):

| Command | What it does |
|---------|--------------|
| `decode <file>.shn` | → `<file>.csv` + `<file>.schema.json`; prints `Round-trip: SAFE`/`UNSAFE` |
| `encode <file>.csv` | `.csv` + `.schema.json` → `.shn`; auto-creates a `.bak`, re-verifies |
| `verify <file>.shn` | re-encode in memory and confirm it matches byte-for-byte |
| `info <file>.shn` | print header, column types, record count |
| `selftest` | built-in correctness checks (no real file needed) |

The **`.csv`** is the editable data (one row per record). The **`.schema.json`**
is the blueprint needed to rebuild a byte-identical `.shn` (crypt header, header
id, column types/lengths, text encoding). Keep them together. Add/edit/remove
*rows* in the CSV freely; do not change column structure unless you also edit the
schema deliberately.

## SAFE workflow for editing the live game (follow every time)

1. Run `python fiesta_shn.py selftest` and confirm `SELFTEST PASSED`.
2. **COPY** the target `.shn` out of `C:\FiestaServer` into a working folder —
   never edit in place.
3. `decode` the copy and confirm it prints **`Round-trip: SAFE`**. If it says
   `UNSAFE`, stop and retry with `--encoding latin-1` (lossless for any file).
4. Make the requested change in the `.csv`.
5. `encode` the `.csv` (this auto-creates a `.bak` and re-verifies).
6. `verify` the resulting `.shn` and confirm **SAFE**.
7. Back up the original on the server, then copy the new `.shn` into
   `C:\FiestaServer`.

### Rules
- Always keep a `.bak`; never edit a `.shn` directly.
- Never deploy a file that didn't report `Round-trip: SAFE`.
- **Stop before Step 7** (touching `C:\FiestaServer`) and confirm with the user,
  unless they have explicitly told you to deploy.

## Important real-world notes

- **Changes load on server start.** The server reads `.shn` files at startup, so
  edits go live only after the relevant server/world process is **restarted** —
  not the instant the file is saved.
- **Server vs client files.** Fiesta keeps `.shn` files in both the server and
  the client. Server-only values (drop rates, mob HP/EXP) just need the server
  file. Things players *see* (item names/icons, vendor/shop displays) are also
  read from the **client** `.shn` — those edits must be mirrored client-side or
  the client and server will disagree.
- The tool guarantees the *file* stays valid; only the user can confirm the
  *change* does what they intended in-game. Encourage testing on a copy/server
  before exposing players.

## Repo layout
- `fiesta_shn.py` — the toolkit.
- `tests/test_shn.py` — pytest suite (`python -m pytest tests/`).
- `windows/*.bat` — drag-and-drop helpers (decode/encode/verify/info).
- `README.md`, `INSTALL-WINDOWS.txt` — usage & Windows setup.
- `CONNECT-FROM-IPAD.md` — remote access (Tailscale + Blink Shell) so this CLI
  can be driven from an iPad.

## Conventions
- Live game data (`*.shn`, `*.csv`, `*.schema.json`, `*.bak`) is gitignored —
  do not commit server data into the repo.
- Keep the toolkit dependency-free (Python standard library only).
- If you change `fiesta_shn.py`, run `python fiesta_shn.py selftest` and
  `python -m pytest tests/` before considering it done.
