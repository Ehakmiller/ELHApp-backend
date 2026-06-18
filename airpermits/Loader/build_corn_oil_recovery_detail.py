from __future__ import annotations

from collections import Counter
from pathlib import Path
import csv
import json
import re


JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
OUT_CSV = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_corn_oil_recovery_detail.csv")
OUT_MD = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_corn_oil_recovery_detail.md")


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def classify_detail(lines: list[str], dco_enhancement: object) -> str:
    text = " ".join(lines + [clean(dco_enhancement)]).lower()
    if "fqpt" in text or "hi pro" in text or "fluid quip" in text or "msc" in text:
        return "Enhanced/high-protein linked DCO"
    if "tricanter" in text or "gs clean tech" in text:
        return "Tricanter / GS CleanTech style recovery"
    if "centrifuge" in text or "separation system" in text or "extraction system" in text:
        return "Separation / centrifuge system"
    if "loadout" in text and "tank" in text:
        return "Storage + loadout identified"
    if "tank" in text:
        return "Storage tanks identified"
    if clean(dco_enhancement):
        return "Technology flag only"
    return "Presence only; limited detail"


def tank_gallons(lines: list[str]) -> list[float]:
    values: list[float] = []
    for line in lines:
        for match in re.finditer(r"([0-9][0-9,]*(?:\.\d+)?)\s*(?:gallon|gal)\b", line, flags=re.I):
            try:
                values.append(float(match.group(1).replace(",", "")))
            except ValueError:
                pass
    return values


def main() -> None:
    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows: list[dict[str, object]] = []
    for record in data:
        if not isinstance(record, dict):
            continue
        operating_permit = record.get("operating_permit") if isinstance(record.get("operating_permit"), dict) else {}
        equipment = operating_permit.get("equipment") if isinstance(operating_permit.get("equipment"), dict) else {}
        corn_oil = equipment.get("corn_oil_systems") if isinstance(equipment.get("corn_oil_systems"), dict) else {}
        special = equipment.get("special_equipment") if isinstance(equipment.get("special_equipment"), dict) else {}
        tech_flags = record.get("tech_flags") if isinstance(record.get("tech_flags"), dict) else {}
        fac_info = record.get("fac_info") if isinstance(record.get("fac_info"), dict) else {}

        present = bool(
            corn_oil.get("present")
            or special.get("corn_oil_recovery")
            or clean(tech_flags.get("dco_enhancement"))
        )
        if not present:
            continue

        source_lines = [clean(line) for line in corn_oil.get("source_lines", []) if clean(line)]
        tanks = tank_gallons(source_lines)
        dco_enhancement = clean(tech_flags.get("dco_enhancement"))
        detail_class = classify_detail(source_lines, dco_enhancement)

        rows.append(
            {
                "EPM": clean(record.get("EPM_NUMBER") or record.get("epm_number") or fac_info.get("epm")),
                "Plant": clean(fac_info.get("plant_name") or record.get("plant_name")),
                "City": clean(fac_info.get("city") or record.get("city")),
                "State": clean(fac_info.get("state") or record.get("state")),
                "DCO enhancement / tech flag": dco_enhancement,
                "Corn oil detail class": detail_class,
                "Corn oil source evidence": "; ".join(source_lines[:8]),
                "Tank count from evidence": len(tanks) if tanks else "",
                "Largest tank gal": max(tanks) if tanks else "",
                "Total named tank gal": sum(tanks) if tanks else "",
                "Corn oil yield available": "No",
                "Source file": clean(operating_permit.get("source_file")),
            }
        )

    rows.sort(
        key=lambda row: (
            clean(row["State"]),
            clean(row["DCO enhancement / tech flag"]) or "zzz",
            clean(row["Plant"]),
        )
    )
    fields = list(rows[0]) if rows else []

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(clean(row["Corn oil detail class"]) for row in rows)
    with OUT_MD.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Corn Oil Recovery Detail\n\n")
        f.write(f"Source JSON: {JSON_PATH}\n\n")
        f.write("## Detail Class Counts\n\n")
        f.write("| Detail class | Count |\n|---|---:|\n")
        for label, count in counts.most_common():
            f.write(f"| {label} | {count} |\n")

        f.write("\n## Facility Detail\n\n")
        f.write("| EPM | Plant | City | DCO tech | Detail class | Evidence |\n")
        f.write("|---:|---|---|---|---|---|\n")
        for row in rows:
            plant = clean(row["Plant"]).replace("|", "/")
            evidence = clean(row["Corn oil source evidence"]).replace("|", "/").replace("\n", " ")
            if len(evidence) > 260:
                evidence = evidence[:257] + "..."
            f.write(
                f"| {row['EPM']} | {plant} | {row['City']} | "
                f"{row['DCO enhancement / tech flag'] or '-'} | "
                f"{row['Corn oil detail class']} | {evidence or '-'} |\n"
            )

    print(f"Wrote {len(rows)} corn oil recovery rows")
    print(f"CSV: {OUT_CSV}")
    print(f"Markdown: {OUT_MD}")
    print("\nDetail class counts:")
    for label, count in counts.most_common():
        print(f"  {label}: {count}")

    print("\nIowa records with stronger detail:")
    for row in rows:
        if row["State"] == "IA" and row["Corn oil detail class"] != "Presence only; limited detail":
            print(
                f"  EPM {row['EPM']}: {row['Plant']} - "
                f"{row['DCO enhancement / tech flag'] or row['Corn oil detail class']}"
            )


if __name__ == "__main__":
    main()
