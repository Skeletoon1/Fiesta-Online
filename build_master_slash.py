#!/usr/bin/env python3
r"""Build the [Master] Slash set across all relevant files.

One-off script: appends rows to the decoded CSVs, inserts a new pool record
into ItemDropGroup.txt, adds drop slots to D_Zombieking + D_GiantGobleKing
in ItemDropTable.txt, clones view/render rows in ItemViewInfo.csv, and
registers the random option groups in RandomOptionTable.txt. After this
runs, encode each .shn and deploy.

Working folder must contain the following files pulled from the live server:

  Decoded CSVs (from `python fiesta_shn.py decode <file>.shn --encoding latin-1`):
    - ItemInfo.csv          (+ ItemInfo.schema.json)
    - ItemInfoServer.csv    (+ ItemInfoServer.schema.json)
    - GradeItemOption.csv   (+ GradeItemOption.schema.json)
    - RandomOption.csv      (+ RandomOption.schema.json)
    - RandomOptionCount.csv (+ RandomOptionCount.schema.json)
    - ItemViewInfo.csv      (+ ItemViewInfo.schema.json)
        source: Server\9Data\Shine\View\ItemViewInfo.shn

  Plaintext drop / random-option tables (copy verbatim):
    - ItemDropGroup.txt
    - ItemDropTable.txt
    - RandomOptionTable.txt
        source: Server\9Data\Shine\World\*.txt

The script is idempotent for the plaintext files (skips inserts if already
present) but appends to the CSVs unconditionally -- if you've already run
it once, re-decode the CSVs first.
"""
import csv
import sys

NAME = "Master"
ITEM_ID_ARMOR = 52030
ITEM_ID_PANTS = 52031
INX_ARMOR = "MasterSlashArmor"
INX_PANTS = "MasterSlashPants"
DISPLAY_ARMOR = "[Master] Slash Armor"
DISPLAY_PANTS = "[Master] Slash Pants"
POOL = "MasterSlashSet"
ROPT_ARMOR = "MasterSlashA"
ROPT_PANTS = "MasterSlashP"
DROP_RATE = 1000  # per million = 0.1%


def append_csv(path, rows):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)
    print("  +%d rows -> %s" % (len(rows), path))


# 1. ItemInfo — clone 52002/52003, change ID + InxName + Name
ARMOR_TEMPLATE = ["52002","SlashArmor","Slash Armor","0","6","1","7","19","5","0","1000","35","2","0","0","52","0","0","30","0","39","1000","1000","1000","1000","0","0","0","0","0","0","3","16000","1000","1","0","0","0","0","2","10","3","0","0","0","0","0","0","0","0","0","0","0","-","-","SlashSet","0"]
PANTS_TEMPLATE = ["52003","SlashPants","Slash Pants","0","6","1","19","19","5","0","1000","35","2","0","0","40","0","0","23","0","30","1000","1000","1000","1000","0","0","0","0","0","0","3","16000","1000","1","0","0","0","0","3","10","23","0","0","0","0","0","0","0","0","0","0","0","-","-","SlashSet","0"]

armor_row = list(ARMOR_TEMPLATE)
armor_row[0:3] = [str(ITEM_ID_ARMOR), INX_ARMOR, DISPLAY_ARMOR]
pants_row = list(PANTS_TEMPLATE)
pants_row[0:3] = [str(ITEM_ID_PANTS), INX_PANTS, DISPLAY_PANTS]
append_csv("ItemInfo.csv", [armor_row, pants_row])

# 2. ItemInfoServer — clone, change ID + InxName + DropGroupA + RandomOptionDropGroup
#    template: 52002,SlashArmor,Weapon,0,SetItem35,-,RandomNamedA05,300000,120000,0,0,20,IS_BODY,0,0,0,0
append_csv("ItemInfoServer.csv", [
    [str(ITEM_ID_ARMOR), INX_ARMOR, "Weapon", "0", POOL, "-", ROPT_ARMOR,
     "300000","120000","0","0","20","IS_BODY","0","0","0","0"],
    [str(ITEM_ID_PANTS), INX_PANTS, "Weapon", "0", POOL, "-", ROPT_PANTS,
     "300000","120000","0","0","17","IS_LEG","0","0","0","0"],
])

# 3. GradeItemOption — keyed by InxName; doubled MaxHP / MaxSP
#    cols: InxName, STR, CON, DEX, INT, MEN, RPo, RDi, RCu, RMS, ToHit, ToBlock, MaxHP, MaxSP, WC+, MA+
append_csv("GradeItemOption.csv", [
    [INX_ARMOR, "0","0","0","0","0","0","0","0","0","1000","1000","600","0","0","0"],
    [INX_PANTS, "0","0","0","0","0","0","0","0","0","1000","1000","0","600","0","0"],
])

# 4. RandomOption — 5 stats forced to +20 each
#    cols: DropItemIndex, RandomOptionType, Min, Max, TypeDropRate
ropt_rows = []
for t in range(5):
    ropt_rows.append([ROPT_ARMOR, str(t), "20", "20", "1000"])
for t in range(5):
    ropt_rows.append([ROPT_PANTS, str(t), "20", "20", "1000"])
append_csv("RandomOption.csv", ropt_rows)

# 5. RandomOptionCount — force 100% chance of all 5 stats
append_csv("RandomOptionCount.csv", [
    [ROPT_ARMOR, "5", "1000"],
    [ROPT_PANTS, "5", "1000"],
])

# 6. ItemDropGroup.txt — insert new pool record after SetItem95
new_pool = ("#RECORD\t%s\t%s\t1\t1\t1000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t1002\t\n"
            % (POOL, POOL))
with open("ItemDropGroup.txt", "r", encoding="latin-1", newline="") as f:
    content = f.read()

# anchor: SetItem95 line is unique; insert our record immediately after it
anchor = "#RECORD\tSetItem95\tSetItem95\t1\t1\t1000\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t1002\t\n"
if anchor not in content:
    sys.stderr.write("FATAL: SetItem95 anchor not found in ItemDropGroup.txt\n")
    sys.exit(1)
if new_pool in content:
    print("  ItemDropGroup.txt already contains %s -- skipping insert" % POOL)
else:
    content = content.replace(anchor, anchor + new_pool, 1)
    with open("ItemDropGroup.txt", "w", encoding="latin-1", newline="") as f:
        f.write(content)
    print("  inserted %s record into ItemDropGroup.txt (after SetItem95)" % POOL)

# 7. ItemDropTable.txt — add drop slot to D_Zombieking + D_GiantGobleKing
with open("ItemDropTable.txt", "r", encoding="latin-1", newline="") as f:
    lines = f.readlines()

def add_drop_to_line(line, item, rate):
    """Replace the first empty drop slot after 'Ore02' with `item rate ...`.
    Returns (new_line, ok)."""
    new_slot = "%s\t%d\t0\t0\tr\t-1" % (item, rate)
    empty = "-\t0\t0\t0\t-\t0"
    idx = line.find("Ore02")
    if idx < 0:
        return line, False
    head, tail = line[:idx], line[idx:]
    if empty not in tail:
        return line, False
    tail = tail.replace(empty, new_slot, 1)
    return head + tail, True

zk_done = False
gk_done = False
for i, line in enumerate(lines):
    if "\tD_Zombieking\t" in line and not zk_done:
        if "MasterSlashSet" in line:
            print("  D_Zombieking line %d already has MasterSlashSet -- skipping" % (i + 1))
            zk_done = True
            continue
        new, ok = add_drop_to_line(line, POOL, DROP_RATE)
        lines[i] = new
        print("  D_Zombieking line %d: %s" % (i + 1, "updated" if ok else "FAILED"))
        zk_done = ok
    elif "\tD_GiantGobleKing\t" in line and not gk_done:
        if "MasterSlashSet" in line:
            print("  D_GiantGobleKing line %d already has MasterSlashSet -- skipping" % (i + 1))
            gk_done = True
            continue
        new, ok = add_drop_to_line(line, POOL, DROP_RATE)
        lines[i] = new
        print("  D_GiantGobleKing line %d: %s" % (i + 1, "updated" if ok else "FAILED"))
        gk_done = ok

if not (zk_done and gk_done):
    sys.stderr.write("FATAL: did not find both bosses (zk=%s, gk=%s)\n"
                     % (zk_done, gk_done))
    sys.exit(1)

with open("ItemDropTable.txt", "w", encoding="latin-1", newline="") as f:
    f.writelines(lines)
print("  ItemDropTable.txt updated")

# 8. ItemViewInfo.csv -- clone view/render rows for the new IDs.
#    Without these the server's drop pipeline silently suppresses drops
#    for the new items (no render entry = no drop, no log line).
#    Templates pulled from live decode (Server\9Data\Shine\View\ItemViewInfo.shn).
ARMOR_VIEW_TEMPLATE = ["52002","SlashArmor","51","ItemEqu000","0","-","0","-","0","0","0","0","0","0","2","-","HideArmor","1","1","1.0","GrdFigBody","0","SFX_ItemEqu","SFX_ItemPutAmor","SFX_ItemPutAmor","5","-"]
PANTS_VIEW_TEMPLATE = ["52003","SlashPants","50","ItemEqu000","0","-","0","-","0","0","0","0","0","0","2","-","HidePants","1","2","1.0","GrdFigLeg","0","SFX_ItemEqu","SFX_ItemPutAmor","SFX_ItemPutAmor","5","-"]

armor_view = list(ARMOR_VIEW_TEMPLATE)
armor_view[0:2] = [str(ITEM_ID_ARMOR), INX_ARMOR]
pants_view = list(PANTS_VIEW_TEMPLATE)
pants_view[0:2] = [str(ITEM_ID_PANTS), INX_PANTS]
append_csv("ItemViewInfo.csv", [armor_view, pants_view])

# 9. RandomOptionTable.txt -- register the new random option groups.
#    THIS file is the server's source of truth for random options at drop
#    time, NOT RandomOption.shn (which appears to be legacy on this build).
#    Without entries here, items reference an unknown group and drops are
#    silently aborted.
#    Format: DropItemIndex, OptionHide, MinOpCount, MaxOpCount,
#            StrMin, StrMax, ConMin, ConMax, DexMin, DexMax,
#            IntMin, IntMax, MenMin, MenMax, CheckSum
#    Lock all 5 stats to exactly +20 by setting Min=Max=20 and Min/MaxOp=5.
ropt_armor_record = (
    "#RECORD\t%s\t0\t5\t5\t20\t20\t20\t20\t20\t20\t20\t20\t20\t20\t4\t;\t%s\t40\t\n"
    % (ROPT_ARMOR, INX_ARMOR)
)
ropt_pants_record = (
    "#RECORD\t%s\t0\t5\t5\t20\t20\t20\t20\t20\t20\t20\t20\t20\t20\t4\t;\t%s\t40\t\n"
    % (ROPT_PANTS, INX_PANTS)
)

with open("RandomOptionTable.txt", "r", encoding="latin-1", newline="") as f:
    rot_lines = f.readlines()

inserted_a = inserted_p = False
out_rot = []
for line in rot_lines:
    out_rot.append(line)
    if (line.startswith("#RECORD\tRandomNamedA05\t")
            and not inserted_a and ropt_armor_record not in "".join(rot_lines)):
        out_rot.append(ropt_armor_record)
        inserted_a = True
        print("  inserted %s after RandomNamedA05" % ROPT_ARMOR)
    elif (line.startswith("#RECORD\tRandomNamedP05\t")
            and not inserted_p and ropt_pants_record not in "".join(rot_lines)):
        out_rot.append(ropt_pants_record)
        inserted_p = True
        print("  inserted %s after RandomNamedP05" % ROPT_PANTS)

# Skip-on-already-present (idempotent)
if not inserted_a and ropt_armor_record in "".join(rot_lines):
    print("  RandomOptionTable.txt already has %s -- skipping" % ROPT_ARMOR)
if not inserted_p and ropt_pants_record in "".join(rot_lines):
    print("  RandomOptionTable.txt already has %s -- skipping" % ROPT_PANTS)

if inserted_a or inserted_p:
    with open("RandomOptionTable.txt", "w", encoding="latin-1", newline="") as f:
        f.writelines(out_rot)

print()
print("All edits applied. Next: encode each .shn and run verify.")
print()
print("Files modified (encode + deploy each):")
print("  shn: ItemInfo, ItemInfoServer, GradeItemOption,")
print("       RandomOption, RandomOptionCount, ItemViewInfo")
print("  txt: ItemDropGroup, ItemDropTable, RandomOptionTable")
print()
print("Deploy paths (the toolkit's `deploy` defaults handle Shine root files;")
print("for ItemViewInfo use --server-dir <...>\\Shine\\View, and copy the .txt")
print("files into <...>\\Shine\\World manually with timestamped backups).")
