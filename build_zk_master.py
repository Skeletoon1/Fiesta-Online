#!/usr/bin/env python3
r"""Build [Master] versions of Zombie King's weapons + rings.

Unlike the set-based builder (build_named_sets.py), this one applies a
*delta formula* to weapon damage/aim/crit columns:

    Master_value = ZK_value + (ZK_value - Regular_value)

i.e. the Master version pushes the same bonus that ZK already adds over
the regular weapon by the same amount again. Random stats are locked at
the natural max of the weapon's random-option group (+15 for
RandomNamedMW04). Sockets, attack rate, class restrictions and every
other field are inherited verbatim from the ZK template.

Rings get a simpler treatment: the existing ZK ring rows are cloned and
re-pointed at a Master random-option group (locked at +11, the natural
RaAcc035 max). All other fields are copied as-is, including the per-ring
fixed stat distributions.

Both categories drop from D_Zombieking only via two new pools
(MasterZKWeapons, MasterZKRings) at 5000/M (0.5%) each.

Working folder must contain the same files as build_named_sets.py
(decoded CSVs + plaintext drop tables).
"""
import csv
import sys

# ---- configuration ----
WEAPON_POOL = "MasterZKWeapons"
RING_POOL = "MasterZKRings"
WEAPON_ROPT = "MasterZKWeaponOpt"
RING_ROPT = "MasterZKRingOpt"
WEAPON_MAX_STAT = 15   # natural max of RandomNamedMW04
RING_MAX_STAT = 11     # natural max of RaAcc035

# Per-stat fixed-bonus caps used in GradeItemOption rows for the Master
# version of every weapon / ring. These are the natural per-stat maxes
# computed across each category's ZK templates:
#   weapons: max(STR)=17 (Bridge Sword), CON=13 (Crusader), DEX=17 (Hide Axe),
#            INT=17 (Zest Staff), MEN=13 (Zest Wand)
#   rings:   STR/CON/DEX/INT all 12, MEN 11 (across the 6 D_ZombieRing0X)
# Applied uniformly: every Master weapon/ring gets ALL 5 stats at the
# category's per-stat max so the in-game tooltip shows both the fixed
# `+X` and the random `(+Y)` at their respective maxes for every stat.
WEAPON_GIO_CAP = {"STR": 17, "CON": 13, "DEX": 17, "INT": 17, "MEN": 13}
RING_GIO_CAP   = {"STR": 12, "CON": 12, "DEX": 12, "INT": 12, "MEN": 11}
DROP_RATE_ZK = 5000    # per million on D_Zombieking, both pools
DISPLAY_PREFIX = "[Master] "
INX_PREFIX = "MasterZK"
NEW_ID_START = 52064

# Mapping ZK weapon InxName -> regular template InxName (REG counterpart for
# the delta formula). The "MasterZK<short>" InxName is built from the
# weapon's class-neutral display name. The free-form display will become
# "[Master] " + ZK display name.
WEAPONS = [
    # (ZK_inx, REG_inx, short_label)
    ("D_ZombiekingBridgeSword",       "BridgeSword",      "BridgeSword"),
    ("D_OldFoxCrusader",              "Crusader",         "Crusader"),
    ("SkelKnightHideAxe",             "HideAxe",          "HideAxe"),
    ("D_ZombiekingStoutMace",         "StoutMace",        "StoutMace"),
    ("SkelKnightStoutHammer",         "StoutHammer",      "StoutHammer"),
    ("D_ZombiekingCloseBow",          "CloseBow",         "CloseBow"),
    ("S_ZombieCloseCrossBow",         "CloseCrossBow",    "CloseCrossBow"),
    ("D_ZombiekingZestStaff",         "ZestStaff",        "ZestStaff"),
    ("S_ZombieZestWand",              "ZestWand",         "ZestWand"),
    ("D_ZombiekingSpinClaw",          "SpinClaw",         "SpinClaw"),
    ("S_ZombieCloseSpinDoubleSword",  "SpinDoubleSword",  "SpinDualSwords"),
]

# Ring InxNames (all in D_ZombieRing pool, just clone with new random group)
RINGS = [
    ("D_ZombieRing01", "Ring01"),
    ("D_ZombieRing02", "Ring02"),
    ("D_ZombieRing03", "Ring03"),
    ("D_ZombieRing04", "Ring04"),
    ("D_ZombieRing05", "Ring05"),
    ("D_ZombieRing06", "Ring06"),
]

# Columns in ItemInfo to which the delta formula applies. Everything else
# is copied from ZK verbatim.
DELTA_COLUMNS = ["MinWC", "MaxWC", "MinMA", "MaxMA", "TH", "CriRate"]


def load_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---- load source CSVs ----
ii_h, ii_rows = load_csv("ItemInfo.csv")
iis_h, iis_rows = load_csv("ItemInfoServer.csv")
ro_h, ro_rows = load_csv("RandomOption.csv")
roc_h, roc_rows = load_csv("RandomOptionCount.csv")
iv_h, iv_rows = load_csv("ItemViewInfo.csv")
gio_h, gio_rows = load_csv("GradeItemOption.csv")

inx_to_id = {r[1]: r[0] for r in ii_rows}
ii_by_id = {r[0]: r for r in ii_rows}
iis_by_id = {r[0]: r for r in iis_rows}
iv_by_id = {r[0]: r for r in iv_rows}
gio_by_inx = {r[0]: r for r in gio_rows}
ii_col = {n: i for i, n in enumerate(ii_h)}
iis_col = {n: i for i, n in enumerate(iis_h)}

# build full set of used IDs so we skip any pre-occupied slots
used_ids = {int(r[0]) for r in ii_rows}


def next_free_id(start):
    i = start
    while i in used_ids:
        i += 1
    used_ids.add(i)
    return i


# ---- new rows accumulators ----
new_ii_rows = []
new_iis_rows = []
new_iv_rows = []
new_gio_rows = []
print("=== Master Zombie King weapons ===")

next_id = NEW_ID_START
for zk_inx, reg_inx, short in WEAPONS:
    if zk_inx not in inx_to_id or reg_inx not in inx_to_id:
        sys.stderr.write(f"ERROR: missing template — zk={zk_inx} reg={reg_inx}\n")
        sys.exit(1)
    zk_id = inx_to_id[zk_inx]
    reg_id = inx_to_id[reg_inx]
    zk_ii = ii_by_id[zk_id]
    reg_ii = ii_by_id[reg_id]
    zk_iis = iis_by_id[zk_id]
    zk_iv = iv_by_id[zk_id]

    new_id = next_free_id(next_id)
    next_id = new_id + 1
    new_inx = INX_PREFIX + short  # e.g. MasterZKZestStaff
    new_display = DISPLAY_PREFIX + zk_ii[ii_col["Name"]]

    # ItemInfo: start from ZK, override ID/InxName/Name, then apply delta
    # formula to specific stat columns.
    new_ii = list(zk_ii)
    new_ii[ii_col["ID"]] = str(new_id)
    new_ii[ii_col["InxName"]] = new_inx
    new_ii[ii_col["Name"]] = new_display
    for col in DELTA_COLUMNS:
        i = ii_col[col]
        zk_val = int(zk_ii[i])
        reg_val = int(reg_ii[i])
        new_ii[i] = str(zk_val + (zk_val - reg_val))
    new_ii_rows.append(new_ii)

    # ItemInfoServer: clone ZK, override ID/InxName/DropGroupA/RandomOpt
    new_iis = list(zk_iis)
    new_iis[iis_col["ID"]] = str(new_id)
    new_iis[iis_col["InxName"]] = new_inx
    new_iis[iis_col["DropGroupA"]] = WEAPON_POOL
    new_iis[iis_col["RandomOptionDropGroup"]] = WEAPON_ROPT
    new_iis_rows.append(new_iis)

    # ItemViewInfo: clone ZK, override ID/InxName
    new_iv = list(zk_iv)
    new_iv[0] = str(new_id)
    new_iv[1] = new_inx
    new_iv_rows.append(new_iv)

    # GradeItemOption: clone ZK row (keyed by InxName), rebadge to the
    # new InxName, and replace the 5 base-stat columns with the per-stat
    # caps so every Master weapon shows STR/CON/DEX/INT/MEN at their
    # respective maxes. ToHitRate / ToBlockRate / etc. are inherited.
    src_gio = gio_by_inx.get(zk_inx)
    if src_gio:
        new_gio = list(src_gio)
        new_gio[0] = new_inx
        gio_idx = {n: i for i, n in enumerate(gio_h)}
        for stat, cap in WEAPON_GIO_CAP.items():
            new_gio[gio_idx[stat]] = str(cap)
        new_gio_rows.append(new_gio)

    # Show the delta for verification
    deltas = []
    for col in DELTA_COLUMNS:
        i = ii_col[col]
        d = int(zk_ii[i]) - int(reg_ii[i])
        if d:
            deltas.append(f"{col}+{d}")
    delta_str = ", ".join(deltas) if deltas else "no deltas"
    print(f"  {new_id} {new_inx:25s} \"{new_display}\"  [{delta_str}]")

print()
print("=== Master Zombie King rings ===")
for zk_inx, short in RINGS:
    if zk_inx not in inx_to_id:
        sys.stderr.write(f"ERROR: missing ring template {zk_inx}\n")
        sys.exit(1)
    zk_id = inx_to_id[zk_inx]
    zk_ii = ii_by_id[zk_id]
    zk_iis = iis_by_id[zk_id]
    zk_iv = iv_by_id[zk_id]

    new_id = next_free_id(next_id)
    next_id = new_id + 1
    new_inx = INX_PREFIX + short  # e.g. MasterZKRing01
    new_display = DISPLAY_PREFIX + zk_ii[ii_col["Name"]]

    # Rings: pure clone (no delta), just rebadge ID/InxName/Name/pool/ropt
    new_ii = list(zk_ii)
    new_ii[ii_col["ID"]] = str(new_id)
    new_ii[ii_col["InxName"]] = new_inx
    new_ii[ii_col["Name"]] = new_display
    new_ii_rows.append(new_ii)

    new_iis = list(zk_iis)
    new_iis[iis_col["ID"]] = str(new_id)
    new_iis[iis_col["InxName"]] = new_inx
    new_iis[iis_col["DropGroupA"]] = RING_POOL
    new_iis[iis_col["RandomOptionDropGroup"]] = RING_ROPT
    new_iis_rows.append(new_iis)

    new_iv = list(zk_iv)
    new_iv[0] = str(new_id)
    new_iv[1] = new_inx
    new_iv_rows.append(new_iv)

    # GradeItemOption: clone the ZK ring row, rebadge, and cap all 5 base
    # stats at the per-stat ring max. Result: every Master ring shows
    # STR/CON/DEX/INT/MEN at their respective max (e.g. 12,12,12,12,11)
    # alongside the locked +11 random rolls.
    src_gio = gio_by_inx.get(zk_inx)
    if src_gio:
        new_gio = list(src_gio)
        new_gio[0] = new_inx
        gio_idx = {n: i for i, n in enumerate(gio_h)}
        for stat, cap in RING_GIO_CAP.items():
            new_gio[gio_idx[stat]] = str(cap)
        new_gio_rows.append(new_gio)

    print(f"  {new_id} {new_inx:25s} \"{new_display}\"")

# ---- write CSVs ----
write_csv("ItemInfo.csv", ii_h, ii_rows + new_ii_rows)
write_csv("ItemInfoServer.csv", iis_h, iis_rows + new_iis_rows)
write_csv("ItemViewInfo.csv", iv_h, iv_rows + new_iv_rows)
write_csv("GradeItemOption.csv", gio_h, gio_rows + new_gio_rows)
print()
print(f"+{len(new_ii_rows)} rows -> ItemInfo / ItemInfoServer / ItemViewInfo")
print(f"+{len(new_gio_rows)} rows -> GradeItemOption (fixed-bonus rows)")

# ---- random option groups (idempotent) ----
def add_ropt_group(group, max_stat):
    existing = {r[0] for r in ro_rows}
    new_rows = []
    if group not in existing:
        for t in range(5):
            new_rows.append([group, str(t), str(max_stat), str(max_stat), "1000"])
    return new_rows

new_ro = add_ropt_group(WEAPON_ROPT, WEAPON_MAX_STAT) + add_ropt_group(RING_ROPT, RING_MAX_STAT)
write_csv("RandomOption.csv", ro_h, ro_rows + new_ro)
print(f"+{len(new_ro)} rows -> RandomOption.csv")

existing_roc = {r[0] for r in roc_rows}
new_roc = []
for grp in (WEAPON_ROPT, RING_ROPT):
    if grp not in existing_roc:
        new_roc.append([grp, "5", "1000"])
write_csv("RandomOptionCount.csv", roc_h, roc_rows + new_roc)
print(f"+{len(new_roc)} rows -> RandomOptionCount.csv")

# ---- ItemDropGroup.txt: add 2 pool records (idempotent) ----
with open("ItemDropGroup.txt", "r", encoding="latin-1", newline="") as f:
    idg = f.read()
anchor = "#RECORD\tSetItem95\tSetItem95\t1\t1\t1000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t1002\t\n"
for pool in (WEAPON_POOL, RING_POOL):
    rec = ("#RECORD\t%s\t%s\t1\t1\t1000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t1002\t\n"
           % (pool, pool))
    if rec in idg:
        print(f"  ItemDropGroup.txt already has {pool} -- skip")
    else:
        if anchor not in idg:
            sys.stderr.write("FATAL: anchor not found in ItemDropGroup.txt\n")
            sys.exit(1)
        idg = idg.replace(anchor, anchor + rec, 1)
        print(f"  inserted {pool} record")
with open("ItemDropGroup.txt", "w", encoding="latin-1", newline="") as f:
    f.write(idg)

# ---- ItemDropTable.txt: add 2 drop slots to D_Zombieking line ----
with open("ItemDropTable.txt", "r", encoding="latin-1", newline="") as f:
    idt = f.readlines()

def add_slot(line, item, rate):
    if f"\t{item}\t" in line:
        return line, f"already has {item}"
    empty = "-\t0\t0\t0\t-\t0"
    idx = line.find("Ore02")
    if idx < 0:
        return line, "no Ore02 anchor"
    head, tail = line[:idx], line[idx:]
    if empty not in tail:
        return line, "no empty slot after Ore02"
    new_slot = f"{item}\t{rate}\t0\t0\tr\t-1"
    return head + tail.replace(empty, new_slot, 1), f"added {item} at {rate}"

for i, line in enumerate(idt):
    if "\tD_Zombieking\t" in line:
        for pool in (WEAPON_POOL, RING_POOL):
            line, action = add_slot(line, pool, DROP_RATE_ZK)
            print(f"  D_Zombieking (line {i+1}): {action}")
        idt[i] = line
        break
with open("ItemDropTable.txt", "w", encoding="latin-1", newline="") as f:
    f.writelines(idt)

# ---- RandomOptionTable.txt: register the two new groups (idempotent) ----
def rot_record(grp, max_stat, label):
    return (f"#RECORD\t{grp}\t0\t5\t5\t{max_stat}\t{max_stat}\t{max_stat}\t{max_stat}"
            f"\t{max_stat}\t{max_stat}\t{max_stat}\t{max_stat}\t{max_stat}\t{max_stat}\t4\t;\t{label}\t40\t\n")

with open("RandomOptionTable.txt", "r", encoding="latin-1", newline="") as f:
    rot = f.readlines()
joined = "".join(rot)

# Insert weapon group after RandomNamedMW04 anchor; ring after RaAcc035
def insert_after_anchor(anchor_prefix, record, label):
    if record in "".join(rot):
        print(f"  RandomOptionTable.txt already has {label} -- skip")
        return
    for i, ln in enumerate(rot):
        if ln.startswith(anchor_prefix):
            rot.insert(i + 1, record)
            print(f"  inserted {label} after {anchor_prefix.strip()}")
            return
    sys.stderr.write(f"WARN: anchor {anchor_prefix} not found for {label}\n")

insert_after_anchor("#RECORD\tRandomNamedMW04\t",
                    rot_record(WEAPON_ROPT, WEAPON_MAX_STAT, WEAPON_ROPT),
                    WEAPON_ROPT)
insert_after_anchor("#RECORD\tRaAcc035\t",
                    rot_record(RING_ROPT, RING_MAX_STAT, RING_ROPT),
                    RING_ROPT)
with open("RandomOptionTable.txt", "w", encoding="latin-1", newline="") as f:
    f.writelines(rot)

print()
print("All edits applied. Encode 4 .shn files (ItemInfo, ItemInfoServer,")
print("RandomOption, RandomOptionCount, ItemViewInfo) and deploy.")
