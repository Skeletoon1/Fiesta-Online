#!/usr/bin/env python3
r"""Build a tier of [Master]-style named sets that share one drop pool.

Generalization of build_master_slash.py. Where the original was specific to
a single 2-piece set (Slash), this script handles N sets at a tier (e.g.
the 9 level-35 sets sharing the SetItem35 pool). All Master variants are:

  * Stats locked at MAX_STAT for all 5 base stats (STR/CON/DEX/INT/MEN)
  * Existing fixed-bonus columns doubled (MaxHP, MaxSP, etc.)
  * Members of one shared drop pool (POOL_NAME) — pool fires at the
    configured rate on each boss; one random member is picked per fire
  * Sharing 3 random-option groups (armor/pants/boots) — no need for a
    separate group per set since the stat lock is uniform

Working folder must contain decoded CSVs and the plaintext drop tables —
see the docstring of build_master_slash.py for the file list.

The script is idempotent for the .txt files (skip-on-already-present) but
appends unconditionally to CSVs — re-decode them first if rerunning.
"""
import csv
import sys

# ---- configuration ----
TIER_LABEL = "Master"             # InxName + display prefix
DISPLAY_PREFIX = "[Master]"       # bracketed display name prefix
POOL_NAME = "MasterSet35"         # shared drop pool name
DROP_RATE_ZK = 5000               # per million, Zombie King
DROP_RATE_GOBK = 2500             # per million, Giant Goblin King
ZK_LEVEL = 45
GOBK_LEVEL = 55
MAX_STAT = 20                     # locked stat value for all 5 base stats

# Shared random-option groups (one per piece type — same lock applies to all)
ROPT_ARMOR = "MasterArmorOpt"
ROPT_PANTS = "MasterPantsOpt"
ROPT_BOOTS = "MasterBootsOpt"

# Sets to build at this tier. Existing Master Slash (52030, 52031) is included
# so it gets migrated to the shared pool / shared random groups.
# Format: (display_name, piece_inxnames, [optional_existing_ids])
SETS = [
    ("Slash",       ["SlashArmor", "SlashPants"],                       [52030, 52031]),
    ("Mighty",      ["MightyArmor", "MightyPants", "MightyBoots"],      None),
    ("PowerWield",  ["PowerWieldArmor", "PowerWieldPants"],             None),
    ("Mental",      ["MentalSetArmor", "MentalSetPants", "MentalSetBoots"], None),
    ("Poison",      ["PoisonArmor", "PoisonPants"],                     None),
    ("Time",        ["TimeArmor", "TimePants", "TimeBoots"],            None),
    ("Fire",        ["FireShirt", "FirePants"],                         None),
    ("Gleam",       ["GleamShirt", "GleamPants", "GleamBoots"],         None),
    ("NorthTear",   ["NorthTearArmor", "NorthTearPants"],               None),
]

# ID range for NEW items (existing Master Slash uses 52030/52031, so new IDs
# start at 52032).
NEW_ID_START = 52032

# ---- helpers ----
def load_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def piece_type(inx):
    """Classify a piece InxName as armor / pants / boots based on suffix."""
    low = inx.lower()
    if "armor" in low or "shirt" in low:
        return "armor"
    if "pants" in low:
        return "pants"
    if "boots" in low:
        return "boots"
    raise ValueError("Unknown piece type for InxName: %s" % inx)


def ropt_for(kind):
    return {"armor": ROPT_ARMOR, "pants": ROPT_PANTS, "boots": ROPT_BOOTS}[kind]


# ---- load source CSVs (decoded from live .shn) ----
ii_h, ii_rows = load_csv("ItemInfo.csv")
iis_h, iis_rows = load_csv("ItemInfoServer.csv")
gio_h, gio_rows = load_csv("GradeItemOption.csv")
ro_h, ro_rows = load_csv("RandomOption.csv")
roc_h, roc_rows = load_csv("RandomOptionCount.csv")
iv_h, iv_rows = load_csv("ItemViewInfo.csv")

inx_to_id = {r[1]: r[0] for r in ii_rows}
ii_by_id = {r[0]: r for r in ii_rows}
iis_by_id = {r[0]: r for r in iis_rows}
iv_by_id = {r[0]: r for r in iv_rows}
gio_by_inx = {r[0]: r for r in gio_rows}

# Build set of ALL used item IDs so we can skip occupied slots when assigning
# new IDs. The 52000-range has more than just SetItem35 sets — Shout/Blow/
# Morale/Kick sets live at 52046+ for instance — so naive sequential
# assignment will collide.
used_ids = {int(r[0]) for r in ii_rows}

# ItemInfo column indices (looked up by name for safety)
ii_col = {name: i for i, name in enumerate(ii_h)}

# ItemInfoServer column indices
iis_col = {name: i for i, name in enumerate(iis_h)}

# GradeItemOption columns to double for the Master treatment (HP/SP if present)
GIO_DOUBLE_COLS = ["MaxHP", "MaxSP"]


def build_master_piece(template_id, new_id, original_inx, original_name):
    """Build cloned rows for a single piece. Returns dicts of new rows
    to append to each file, keyed by file name."""
    kind = piece_type(original_inx)
    master_inx = f"{TIER_LABEL}{original_inx}"
    master_display = f"{DISPLAY_PREFIX} {original_name}"

    # ItemInfo: clone + change ID, InxName, Name
    src_ii = ii_by_id[str(template_id)]
    new_ii = list(src_ii)
    new_ii[ii_col["ID"]] = str(new_id)
    new_ii[ii_col["InxName"]] = master_inx
    new_ii[ii_col["Name"]] = master_display

    # ItemInfoServer: clone + change ID, InxName, DropGroupA, RandomOptionDropGroup
    src_iis = iis_by_id[str(template_id)]
    new_iis = list(src_iis)
    new_iis[iis_col["ID"]] = str(new_id)
    new_iis[iis_col["InxName"]] = master_inx
    new_iis[iis_col["DropGroupA"]] = POOL_NAME
    new_iis[iis_col["RandomOptionDropGroup"]] = ropt_for(kind)

    # GradeItemOption: only if the template has one. Double HP / SP columns.
    new_gio = None
    src_gio = gio_by_inx.get(original_inx)
    if src_gio:
        gio_cols = {n: i for i, n in enumerate(gio_h)}
        new_gio = list(src_gio)
        new_gio[0] = master_inx
        for col in GIO_DOUBLE_COLS:
            if col in gio_cols:
                cur = int(new_gio[gio_cols[col]])
                if cur > 0:
                    new_gio[gio_cols[col]] = str(cur * 2)

    # ItemViewInfo: clone + change ID, InxName
    src_iv = iv_by_id[str(template_id)]
    new_iv = list(src_iv)
    new_iv[0] = str(new_id)
    new_iv[1] = master_inx

    return {
        "ItemInfo": new_ii,
        "ItemInfoServer": new_iis,
        "GradeItemOption": new_gio,
        "ItemViewInfo": new_iv,
        "kind": kind,
        "master_inx": master_inx,
    }


# ---- Section 1-8: build / update items across all sets ----
new_ii_rows = []
new_iis_rows = []
new_gio_rows = []
new_iv_rows = []

# Updates to existing items: (row_list_ref, ID-or-index, updates_dict)
# We'll edit ii_rows / iis_rows in place for migration of existing Master Slash.
updated_existing = []

next_new_id = NEW_ID_START
for set_name, pieces, existing_ids in SETS:
    for piece_idx, piece_inx in enumerate(pieces):
        template_id = inx_to_id.get(piece_inx)
        if not template_id:
            sys.stderr.write(f"ERROR: template piece {piece_inx} not in ItemInfo.csv\n")
            sys.exit(1)
        template_id = int(template_id)
        src_name = ii_by_id[str(template_id)][ii_col["Name"]]

        if existing_ids:
            # Existing Master item — migrate its pool / random group fields
            new_id = existing_ids[piece_idx]
            kind = piece_type(piece_inx)
            row = iis_by_id.get(str(new_id))
            if row is None:
                sys.stderr.write(
                    f"ERROR: existing Master ID {new_id} not in ItemInfoServer.csv\n"
                )
                sys.exit(1)
            old_pool = row[iis_col["DropGroupA"]]
            old_ropt = row[iis_col["RandomOptionDropGroup"]]
            row[iis_col["DropGroupA"]] = POOL_NAME
            row[iis_col["RandomOptionDropGroup"]] = ropt_for(kind)
            print(f"  migrated {new_id} {row[iis_col['InxName']]}: "
                  f"pool {old_pool} -> {POOL_NAME}, ropt {old_ropt} -> {ropt_for(kind)}")
        else:
            # Brand new clone -- skip any IDs already in use
            while next_new_id in used_ids:
                next_new_id += 1
            new_id = next_new_id
            used_ids.add(new_id)
            next_new_id += 1
            piece = build_master_piece(template_id, new_id, piece_inx, src_name)
            new_ii_rows.append(piece["ItemInfo"])
            new_iis_rows.append(piece["ItemInfoServer"])
            if piece["GradeItemOption"] is not None:
                new_gio_rows.append(piece["GradeItemOption"])
            new_iv_rows.append(piece["ItemViewInfo"])
            print(f"  cloned {template_id} {piece_inx} -> "
                  f"{new_id} {piece['master_inx']}")

# ---- write updated CSVs ----
# ItemInfo: append new
write_csv("ItemInfo.csv", ii_h, ii_rows + new_ii_rows)
print(f"+{len(new_ii_rows)} rows -> ItemInfo.csv")

# ItemInfoServer: existing rows have been edited in-place for migrations,
# new rows are appended
write_csv("ItemInfoServer.csv", iis_h, iis_rows + new_iis_rows)
print(f"+{len(new_iis_rows)} rows -> ItemInfoServer.csv (+ migrated existing)")

# GradeItemOption: append new
write_csv("GradeItemOption.csv", gio_h, gio_rows + new_gio_rows)
print(f"+{len(new_gio_rows)} rows -> GradeItemOption.csv")

# RandomOption / RandomOptionCount: shared groups for all sets
# Only add once each — idempotent check by group name
existing_ropt_groups = {r[0] for r in ro_rows}
new_ro_rows = []
for grp in (ROPT_ARMOR, ROPT_PANTS, ROPT_BOOTS):
    if grp in existing_ropt_groups:
        continue
    for t in range(5):
        new_ro_rows.append([grp, str(t), str(MAX_STAT), str(MAX_STAT), "1000"])
write_csv("RandomOption.csv", ro_h, ro_rows + new_ro_rows)
print(f"+{len(new_ro_rows)} rows -> RandomOption.csv")

existing_roc = {r[0] for r in roc_rows}
new_roc_rows = []
for grp in (ROPT_ARMOR, ROPT_PANTS, ROPT_BOOTS):
    if grp in existing_roc:
        continue
    new_roc_rows.append([grp, "5", "1000"])
write_csv("RandomOptionCount.csv", roc_h, roc_rows + new_roc_rows)
print(f"+{len(new_roc_rows)} rows -> RandomOptionCount.csv")

# ItemViewInfo: append new
write_csv("ItemViewInfo.csv", iv_h, iv_rows + new_iv_rows)
print(f"+{len(new_iv_rows)} rows -> ItemViewInfo.csv")

# ---- Section 7: ItemDropGroup.txt — register MasterSet35 pool (idempotent) ----
pool_record = (
    "#RECORD\t%s\t%s\t1\t1\t1000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t1002\t\n"
    % (POOL_NAME, POOL_NAME)
)
with open("ItemDropGroup.txt", "r", encoding="latin-1", newline="") as f:
    idg_content = f.read()

if pool_record in idg_content:
    print(f"  ItemDropGroup.txt already has {POOL_NAME} -- skip")
else:
    anchor = "#RECORD\tSetItem95\tSetItem95\t1\t1\t1000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t1002\t\n"
    if anchor not in idg_content:
        sys.stderr.write("FATAL: SetItem95 anchor not found in ItemDropGroup.txt\n")
        sys.exit(1)
    idg_content = idg_content.replace(anchor, anchor + pool_record, 1)
    with open("ItemDropGroup.txt", "w", encoding="latin-1", newline="") as f:
        f.write(idg_content)
    print(f"  inserted {POOL_NAME} record into ItemDropGroup.txt")

# ---- Section 8: ItemDropTable.txt — replace any existing MasterSlashSet
# entry with MasterSet35 (preserves rate); add MasterSet35 if not present ----
with open("ItemDropTable.txt", "r", encoding="latin-1", newline="") as f:
    idt_lines = f.readlines()

def update_boss_line(line, rate):
    """Ensure the boss line has a MasterSet35 entry at the given rate.
    If a MasterSlashSet entry exists, swap it. Otherwise add to first empty slot.
    Returns (new_line, action)."""
    # Already has MasterSet35 — leave alone (idempotent)
    if "\tMasterSet35\t" in line:
        return line, "already has MasterSet35"
    # Swap MasterSlashSet -> MasterSet35 preserving rate field (the one used today)
    import re
    m = re.search(r"\tMasterSlashSet\t(\d+)\t0\t0\tr\t-1\t", line)
    if m:
        old = m.group(0)
        new = f"\tMasterSet35\t{rate}\t0\t0\tr\t-1\t"
        return line.replace(old, new, 1), f"swapped MasterSlashSet({m.group(1)}) -> MasterSet35({rate})"
    # No master entry yet — find first empty slot after Ore02 and put MasterSet35 there
    empty = "-\t0\t0\t0\t-\t0"
    idx = line.find("Ore02")
    if idx >= 0:
        head, tail = line[:idx], line[idx:]
        if empty in tail:
            new_slot = f"MasterSet35\t{rate}\t0\t0\tr\t-1"
            return head + tail.replace(empty, new_slot, 1), f"added MasterSet35 at {rate} (new slot)"
    return line, "FAILED"

bosses = [("D_Zombieking", DROP_RATE_ZK), ("D_GiantGobleKing", DROP_RATE_GOBK)]
for i, line in enumerate(idt_lines):
    for boss, rate in bosses:
        if f"\t{boss}\t" in line:
            new, action = update_boss_line(line, rate)
            idt_lines[i] = new
            print(f"  {boss} (line {i+1}): {action}")

with open("ItemDropTable.txt", "w", encoding="latin-1", newline="") as f:
    f.writelines(idt_lines)

# ---- Section 9: RandomOptionTable.txt — add shared groups (idempotent) ----
rot_record = (
    "#RECORD\t{grp}\t0\t5\t5\t{m}\t{m}\t{m}\t{m}\t{m}\t{m}\t{m}\t{m}\t{m}\t{m}\t4\t;\t{grp}\t40\t\n"
)
new_records = {
    ROPT_ARMOR: rot_record.format(grp=ROPT_ARMOR, m=MAX_STAT),
    ROPT_PANTS: rot_record.format(grp=ROPT_PANTS, m=MAX_STAT),
    ROPT_BOOTS: rot_record.format(grp=ROPT_BOOTS, m=MAX_STAT),
}

with open("RandomOptionTable.txt", "r", encoding="latin-1", newline="") as f:
    rot_lines = f.readlines()

# Insert after the corresponding RandomNamed*05 anchors
anchors = {
    ROPT_ARMOR: "#RECORD\tRandomNamedA05\t",
    ROPT_PANTS: "#RECORD\tRandomNamedP05\t",
    ROPT_BOOTS: "#RECORD\tRandomNamedB05\t",
}

inserted = {g: False for g in new_records}
out_rot = []
joined = "".join(rot_lines)
for line in rot_lines:
    out_rot.append(line)
    for grp, anchor_prefix in anchors.items():
        if line.startswith(anchor_prefix) and not inserted[grp]:
            if new_records[grp] in joined:
                print(f"  RandomOptionTable.txt already has {grp} -- skip")
                inserted[grp] = True
            else:
                out_rot.append(new_records[grp])
                inserted[grp] = True
                print(f"  inserted {grp} after {anchor_prefix.strip()}")

if any(out_rot[i] != rot_lines[i] for i in range(min(len(out_rot), len(rot_lines)))):
    with open("RandomOptionTable.txt", "w", encoding="latin-1", newline="") as f:
        f.writelines(out_rot)

print()
print("All edits applied. Next: encode the 6 modified CSVs and deploy.")
print()
print("Files to encode + deploy:")
print("  shn (server root): ItemInfo, ItemInfoServer, GradeItemOption,")
print("                     RandomOption, RandomOptionCount")
print("  shn (server View/ + client ressystem): ItemViewInfo")
print("  txt (server World/): ItemDropGroup, ItemDropTable, RandomOptionTable")
