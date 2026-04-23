"""
Rebuild skill_to_row.json to use new Tabiya IDs from the updated skills.csv
while preserving the existing embedding matrix row assignments.

Bridge: old internal ID --[ORIGINURI]--> new Tabiya ID
        old internal ID --[skill_to_row.json]--> row index
        => new Tabiya ID --> row index
"""
import csv
import json
import subprocess
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .../backend
S2R_PATH = ROOT / "resources/models/skill_to_row.json"
NEW_CSV = ROOT / "resources/skill_taxonomy/skills.csv"

# 1. Load current skill_to_row.json (old internal IDs -> row indices)
with open(S2R_PATH) as f:
    old_s2r = json.load(f)
print(f"Old skill_to_row: {len(old_s2r)} entries")
print(f"  Sample: {list(old_s2r.items())[:2]}")

# 2. Extract old CSV from git: old internal ID -> ORIGINURI
old_csv_bytes = subprocess.check_output(
    ["git", "show", "a7c44c4:backend/app/services/skills_utility/skills.csv"],
    cwd=str(ROOT.parent),
)
old_csv_text = old_csv_bytes.decode("utf-8", errors="replace")

old_id_to_uri = {}
reader = csv.DictReader(io.StringIO(old_csv_text))
for row in reader:
    old_id = row.get("ID", "").strip()
    uri = row.get("ORIGINURI", "").strip()
    if old_id and uri:
        old_id_to_uri[old_id] = uri

print(f"\nOld CSV: {len(old_id_to_uri)} ID->URI mappings")
print(f"  Sample: {list(old_id_to_uri.items())[:2]}")

# 3. Build URI -> row index (via old IDs)
uri_to_row = {}
missing_uri = 0
for old_id, row_idx in old_s2r.items():
    uri = old_id_to_uri.get(old_id)
    if uri:
        uri_to_row[uri] = row_idx
    else:
        missing_uri += 1

print(f"\nURI->row mappings: {len(uri_to_row)}")
print(f"  Old IDs without URI: {missing_uri}")

# 4. Parse new CSV: new Tabiya ID -> ORIGINURI
new_id_to_uri = {}
new_uri_to_id = {}
with open(NEW_CSV, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        new_id = row.get("ID", "").strip()
        uri = row.get("ORIGINURI", "").strip()
        if new_id and uri:
            new_id_to_uri[new_id] = uri
            new_uri_to_id[uri] = new_id

print(f"\nNew CSV: {len(new_id_to_uri)} Tabiya ID->URI mappings")
print(f"  Sample: {list(new_id_to_uri.items())[:2]}")

# 5. Build new skill_to_row: Tabiya ID -> row index
new_s2r = {}
mapped = 0
unmapped_new = 0
for new_id, uri in new_id_to_uri.items():
    row_idx = uri_to_row.get(uri)
    if row_idx is not None:
        new_s2r[new_id] = row_idx
        mapped += 1
    else:
        unmapped_new += 1

# Also check: old IDs that have no new counterpart
unmapped_old = 0
for uri, row_idx in uri_to_row.items():
    if uri not in new_uri_to_id:
        unmapped_old += 1

print(f"\n--- Results ---")
print(f"New skill_to_row entries: {len(new_s2r)}")
print(f"Successfully mapped: {mapped}")
print(f"New skills without old embedding row: {unmapped_new}")
print(f"Old skills without new Tabiya counterpart: {unmapped_old}")
print(f"Sample new mapping: {list(new_s2r.items())[:3]}")

# 6. Verify: row indices should be the same set (minus any gaps)
old_rows = set(old_s2r.values())
new_rows = set(new_s2r.values())
print(f"\nOld row index range: {min(old_rows)}-{max(old_rows)}")
print(f"New row index range: {min(new_rows)}-{max(new_rows)}")
print(f"Row indices preserved: {len(old_rows & new_rows)}/{len(old_rows)}")

# 7. Write new skill_to_row.json
backup_path = S2R_PATH.with_suffix(".json.bak")
with open(backup_path, "w") as f:
    json.dump(old_s2r, f)
print(f"\nBackup saved to {backup_path}")

with open(S2R_PATH, "w") as f:
    json.dump(new_s2r, f)
print(f"New skill_to_row.json written with {len(new_s2r)} entries")
