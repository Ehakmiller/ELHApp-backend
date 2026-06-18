from __future__ import annotations

from collections import Counter
from pathlib import Path
import csv
import json


JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
OUT_CSV = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_dryer_membrane_detail.csv")
OUT_MD = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_dryer_membrane_detail.md")


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def main() -> None:
    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows: list[dict[str, object]] = []
    dryer_counts: Counter[str] = Counter()
    membrane_counts: Counter[str] = Counter()

    for record in data:
        if not isinstance(record, dict):
            continue
        operating_permit = record.get("operating_permit") if isinstance(record.get("operating_permit"), dict) else {}
        equipment = operating_permit.get("equipment") if isinstance(operating_permit.get("equipment"), dict) else {}
        special = equipment.get("special_equipment") if isinstance(equipment.get("special_equipment"), dict) else {}
        dryers = equipment.get("dryers") if isinstance(equipment.get("dryers"), dict) else {}
        tech_flags = record.get("tech_flags") if isinstance(record.get("tech_flags"), dict) else {}
        fac_info = record.get("fac_info") if isinstance(record.get("fac_info"), dict) else {}

        dryer_type = clean(dryers.get("type"))
        tech_dryer_type = clean(tech_flags.get("dryer_types"))
        dryer_type_from_flags = clean(dryers.get("type_from_technology_flags"))
        if dryer_type:
            dryer_counts[dryer_type] += 1

        white_fox = clean(tech_flags.get("white_fox"))
        membrane = bool(special.get("membrane_dehydration") or white_fox)
        if membrane:
            membrane_counts[white_fox or "Permit-derived membrane mention"] += 1

        if not dryer_type and not tech_dryer_type and not membrane:
            continue

        source_lines = [clean(line) for line in dryers.get("source_lines", []) if clean(line)]
        rows.append(
            {
                "EPM": clean(record.get("EPM_NUMBER") or record.get("epm_number") or fac_info.get("epm")),
                "Plant": clean(fac_info.get("plant_name") or record.get("plant_name")),
                "City": clean(fac_info.get("city") or record.get("city")),
                "State": clean(fac_info.get("state") or record.get("state")),
                "Operating permit dryer type": dryer_type,
                "Tech flag dryer type": tech_dryer_type,
                "Dryer type from tech flags": dryer_type_from_flags,
                "Dryer count from permit": clean(dryers.get("count")),
                "Dryer confidence": clean(tech_flags.get("dryer_confidence")),
                "Membrane dehydration": "Yes" if membrane else "No",
                "Membrane / White Fox detail": white_fox,
                "Dryer source evidence": "; ".join(source_lines[:8]),
                "Source file": clean(operating_permit.get("source_file")),
            }
        )

    rows.sort(key=lambda row: (clean(row["State"]), clean(row["Plant"])))
    fields = list(rows[0]) if rows else []

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Dryer And Membrane Detail\n\n")
        f.write(f"Source JSON: {JSON_PATH}\n\n")
        f.write("## Dryer Type Counts\n\n")
        f.write("| Dryer type | Count |\n|---|---:|\n")
        for label, count in dryer_counts.most_common():
            f.write(f"| {label} | {count} |\n")

        f.write("\n## Membrane / White Fox Counts\n\n")
        f.write("| Membrane system | Count |\n|---|---:|\n")
        for label, count in membrane_counts.most_common():
            f.write(f"| {label} | {count} |\n")

        f.write("\n## Iowa Facility Detail\n\n")
        f.write("| EPM | Plant | City | Permit dryer | Tech dryer | Count | Membrane | Evidence |\n")
        f.write("|---:|---|---|---|---|---:|---|---|\n")
        for row in rows:
            if row["State"] != "IA":
                continue
            evidence = clean(row["Dryer source evidence"]).replace("|", "/").replace("\n", " ")
            if len(evidence) > 260:
                evidence = evidence[:257] + "..."
            f.write(
                f"| {row['EPM']} | {clean(row['Plant']).replace('|', '/')} | {row['City']} | "
                f"{row['Operating permit dryer type'] or '-'} | {row['Tech flag dryer type'] or '-'} | "
                f"{row['Dryer count from permit'] or '-'} | {row['Membrane / White Fox detail'] or '-'} | "
                f"{evidence or '-'} |\n"
            )

    print(f"Wrote {len(rows)} dryer/membrane rows")
    print(f"CSV: {OUT_CSV}")
    print(f"Markdown: {OUT_MD}")
    print("\nDryer type counts:")
    for label, count in dryer_counts.most_common():
        print(f"  {label}: {count}")
    print("\nMembrane / White Fox counts:")
    for label, count in membrane_counts.most_common():
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
