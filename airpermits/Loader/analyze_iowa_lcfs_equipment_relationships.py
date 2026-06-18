from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import csv
import json
import math
import statistics


JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
OUT_DIR = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary")
OUT_ROWS = OUT_DIR / "_iowa_lcfs_equipment_facility_rows.csv"
OUT_SUMMARY = OUT_DIR / "_iowa_lcfs_equipment_correlation_summary.csv"
OUT_NUMERIC = OUT_DIR / "_iowa_lcfs_energy_numeric_correlation_summary.csv"
OUT_MD = OUT_DIR / "_iowa_lcfs_equipment_correlation_report.md"


TECHNOLOGY_FLAGS = [
    "white_fox_membrane",
    "molecular_sieve_only",
    "chp",
    "waste_heat_recovery",
    "fiber_to_ethanol",
    "d3_capable",
    "generic_fiber_separation",
    "high_protein",
    "corn_oil_extraction",
    "edeniq",
    "fluid_quip",
    "icm_selective_milling",
    "icm_fst",
    "co2_capture",
    "rng_biogas",
]

NUMERIC_METRICS = [
    "dryer_mmbtu_hr",
    "boiler_mmbtu_hr",
    "rto_thermal_oxidizer_mmbtu_hr",
    "waste_heat_boiler_mmbtu_hr",
    "total_thermal_mmbtu_hr",
    "total_thermal_mmbtu_hr_per_mgy",
    "estimated_btu_per_gal_from_heat_input",
]


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def number(value: object) -> float | None:
    if value is None:
        return None
    try:
        out = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def parse_date(value: object) -> datetime:
    text = clean(value)
    if not text:
        return datetime.min
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            pass
    return datetime.min


def pathway_class(*values: object) -> str:
    text = " ".join(clean(v).lower() for v in values if clean(v))
    if "fiber" in text or "cellulosic" in text:
        return "fiber/cellulosic"
    if "sorghum" in text or "milo" in text:
        return "sorghum"
    if "corn" in text or "starch" in text or "ethanol" in text:
        return "corn starch"
    return "unknown"


def latest_lowest(rows: list[dict], date_key: str, ci_key: str) -> dict | None:
    valid = [row for row in rows if number(row.get(ci_key)) is not None]
    if not valid:
        return None
    latest = max(parse_date(row.get(date_key)) for row in valid)
    latest_rows = [row for row in valid if parse_date(row.get(date_key)) == latest]
    return min(latest_rows, key=lambda row: number(row.get(ci_key)) or 999)


def plant_scores(record: dict) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []

    lcfs = record.get("lcfs_detail") if isinstance(record.get("lcfs_detail"), dict) else {}
    for program, key in (("CA", "ca_detail"), ("OR", "or_detail")):
        detail = lcfs.get(key) if isinstance(lcfs.get(key), list) else []
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in detail:
            cls = pathway_class(row.get("pathway_type"), row.get("feedstock"), row.get("coproduct_type"))
            grouped[cls].append(row)
        for cls, rows in grouped.items():
            selected = latest_lowest(rows, "detail_date", "ci_score")
            if selected:
                out.append(
                    {
                        "program": program,
                        "pathway_class": cls,
                        "ci": number(selected.get("ci_score")),
                        "feedstock": clean(selected.get("feedstock")),
                        "coproduct_type": clean(selected.get("coproduct_type")),
                        "source_date": clean(selected.get("detail_date")),
                        "source_detail": "",
                    }
                )

    wa = record.get("wa_lcfs_ci_detail") if isinstance(record.get("wa_lcfs_ci_detail"), list) else []
    wa_active = [row for row in wa if clean(row.get("status") or row.get("Active")).lower() in {"active", "1", "true", "yes"}]
    grouped_wa: dict[str, list[dict]] = defaultdict(list)
    for row in wa_active:
        cls = pathway_class(row.get("feedstock_class"), row.get("Fuel Name"), row.get("Pathway Description"))
        grouped_wa[cls].append(row)
    for cls, rows in grouped_wa.items():
        selected = min(rows, key=lambda row: number(row.get("CI")) or 999)
        out.append(
            {
                "program": "WA",
                "pathway_class": cls,
                "ci": number(selected.get("CI")),
                "feedstock": clean(selected.get("feedstock_class") or selected.get("Fuel Name")),
                "coproduct_type": "",
                "source_date": clean(selected.get("Eff. Start Qtr/Yr")),
                "source_detail": clean(selected.get("Pathway Description")),
            }
        )

    bc = record.get("bc_lcfs_ci_detail") if isinstance(record.get("bc_lcfs_ci_detail"), list) else []
    bc_active = [row for row in bc if clean(row.get("status")).lower() == "active"]
    grouped_bc: dict[str, list[dict]] = defaultdict(list)
    for row in bc_active:
        cls = pathway_class(row.get("fuel_code"), row.get("company"))
        grouped_bc[cls].append(row)
    for cls, rows in grouped_bc.items():
        selected = max(rows, key=lambda row: (number(row.get("pathway_version")) or 0, parse_date(row.get("effective_date"))))
        out.append(
            {
                "program": "BC",
                "pathway_class": cls,
                "ci": number(selected.get("carbon_intensity_gCO2e_per_MJ")),
                "feedstock": "",
                "coproduct_type": "",
                "source_date": clean(selected.get("effective_date")),
                "source_detail": clean(selected.get("fuel_code")),
            }
        )

    cfa = record.get("canadian_fed_ci_detail") if isinstance(record.get("canadian_fed_ci_detail"), dict) else None
    if cfa and clean(cfa.get("status")).lower() == "active":
        out.append(
            {
                "program": "CFA",
                "pathway_class": pathway_class(cfa.get("grain_source"), cfa.get("fuel_type")),
                "ci": number(cfa.get("approved_ci_gco2e_mj")),
                "feedstock": clean(cfa.get("grain_source")),
                "coproduct_type": "",
                "source_date": clean(cfa.get("approval_date")),
                "source_detail": clean(cfa.get("ci_type")),
            }
        )

    return [row for row in out if row["ci"] is not None]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    if not x_var or not y_var:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / math.sqrt(x_var * y_var)


def main() -> None:
    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    facility_rows: list[dict[str, object]] = []
    for record in data:
        if not isinstance(record, dict):
            continue
        fac = record.get("fac_info") if isinstance(record.get("fac_info"), dict) else {}
        if clean(fac.get("state")).upper() != "IA":
            continue
        permit = record.get("operating_permit") if isinstance(record.get("operating_permit"), dict) else {}
        if not permit:
            continue
        equipment = permit.get("equipment") if isinstance(permit.get("equipment"), dict) else {}
        technology_flags = equipment.get("technology_flags") if isinstance(equipment.get("technology_flags"), dict) else {}
        dryers = equipment.get("dryers") if isinstance(equipment.get("dryers"), dict) else {}
        derivatives = permit.get("derivatives") if isinstance(permit.get("derivatives"), dict) else {}
        tech = record.get("tech_flags") if isinstance(record.get("tech_flags"), dict) else {}

        def metric_value(name: str) -> float | None:
            item = derivatives.get(name) if isinstance(derivatives.get(name), dict) else {}
            return number(item.get("value"))

        base = {
            "EPM": clean(fac.get("epm") or record.get("EPM_NUMBER") or record.get("epm_number")),
            "Plant": clean(fac.get("plant_name") or record.get("plant_name")),
            "City": clean(fac.get("city") or record.get("city")),
            "capacity_mgy": number(fac.get("ethanol_capacity_mgy")),
            "dryer_type": clean(dryers.get("type") or tech.get("dryer_types")),
            "dryer_type_from_technology_flags": clean(dryers.get("type_from_technology_flags") or tech.get("dryer_types")),
            "fiber_to_ethanol_technology": clean(technology_flags.get("fiber_to_ethanol_technology")),
            "fiber_to_ethanol_source": clean(technology_flags.get("fiber_to_ethanol_source")),
            "operating_permit_source": clean(permit.get("source_file")),
            "dryer_mmbtu_hr": metric_value("dryer_mmbtu_hr"),
            "boiler_mmbtu_hr": metric_value("boiler_mmbtu_hr"),
            "rto_thermal_oxidizer_mmbtu_hr": metric_value("rto_thermal_oxidizer_mmbtu_hr"),
            "waste_heat_boiler_mmbtu_hr": metric_value("waste_heat_boiler_mmbtu_hr"),
            "total_thermal_mmbtu_hr": metric_value("total_thermal_mmbtu_hr"),
            "total_thermal_mmbtu_hr_per_mgy": metric_value("total_thermal_mmbtu_hr_per_mgy"),
            "estimated_btu_per_gal_from_heat_input": metric_value("estimated_btu_per_gal_from_heat_input"),
        }
        for flag in TECHNOLOGY_FLAGS:
            base[flag] = bool(technology_flags.get(flag))

        for score in plant_scores(record):
            facility_rows.append({**base, **score})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if facility_rows:
        with OUT_ROWS.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(facility_rows[0]))
            writer.writeheader()
            writer.writerows(facility_rows)

    summary_rows: list[dict[str, object]] = []
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in facility_rows:
        groups[(clean(row["program"]), clean(row["pathway_class"]))].append(row)

    for (program, cls), rows in sorted(groups.items()):
        if len(rows) < 4:
            continue
        for flag in TECHNOLOGY_FLAGS:
            true_scores = [float(row["ci"]) for row in rows if row.get(flag)]
            false_scores = [float(row["ci"]) for row in rows if not row.get(flag)]
            if len(true_scores) < 2 or len(false_scores) < 2:
                continue
            xs = [1.0 if row.get(flag) else 0.0 for row in rows]
            ys = [float(row["ci"]) for row in rows]
            avg_true = statistics.mean(true_scores)
            avg_false = statistics.mean(false_scores)
            summary_rows.append(
                {
                    "program": program,
                    "pathway_class": cls,
                    "flag": flag,
                    "n_total": len(rows),
                    "n_flag_true": len(true_scores),
                    "n_flag_false": len(false_scores),
                    "avg_ci_flag_true": avg_true,
                    "avg_ci_flag_false": avg_false,
                    "avg_ci_true_minus_false": avg_true - avg_false,
                    "correlation_binary_flag_to_ci": pearson(xs, ys),
                    "interpretation": "lower CI associated with flag" if avg_true < avg_false else "higher CI associated with flag",
                }
            )

    summary_rows.sort(key=lambda row: (row["program"], row["pathway_class"], abs(float(row["avg_ci_true_minus_false"]))), reverse=True)
    if summary_rows:
        with OUT_SUMMARY.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary_rows[0]))
            writer.writeheader()
            writer.writerows(summary_rows)

    numeric_rows: list[dict[str, object]] = []
    for (program, cls), rows in sorted(groups.items()):
        if len(rows) < 4:
            continue
        for metric_name in NUMERIC_METRICS:
            pairs = [
                (float(row[metric_name]), float(row["ci"]))
                for row in rows
                if row.get(metric_name) is not None and number(row.get(metric_name)) is not None
            ]
            if len(pairs) < 3:
                continue
            xs = [pair[0] for pair in pairs]
            ys = [pair[1] for pair in pairs]
            numeric_rows.append(
                {
                    "program": program,
                    "pathway_class": cls,
                    "metric": metric_name,
                    "n": len(pairs),
                    "avg_metric": statistics.mean(xs),
                    "avg_ci": statistics.mean(ys),
                    "correlation_metric_to_ci": pearson(xs, ys),
                    "note": "positive means higher metric associated with higher CI; negative means higher metric associated with lower CI",
                }
            )
    numeric_rows.sort(key=lambda row: abs(float(row["correlation_metric_to_ci"] or 0)), reverse=True)
    if numeric_rows:
        with OUT_NUMERIC.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(numeric_rows[0]))
            writer.writeheader()
            writer.writerows(numeric_rows)

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Iowa LCFS CI vs Operating Permit Equipment\n\n")
        f.write(f"Source JSON: `{JSON_PATH}`\n\n")
        f.write("Scores are active/latest facility scores collapsed by program and pathway class. Lower CI is better. ")
        f.write("This is exploratory: small samples and correlated technology choices mean the results should be treated as relationship flags, not causal proof.\n\n")
        f.write(f"Facility-score rows: {len(facility_rows)}\n\n")

        f.write("## Strongest Average Differences\n\n")
        f.write("| Program | Class | Flag | N true | N false | Avg CI true | Avg CI false | True - false | Direction |\n")
        f.write("|---|---|---|---:|---:|---:|---:|---:|---|\n")
        for row in summary_rows[:30]:
            f.write(
                f"| {row['program']} | {row['pathway_class']} | {row['flag']} | "
                f"{row['n_flag_true']} | {row['n_flag_false']} | "
                f"{float(row['avg_ci_flag_true']):.2f} | {float(row['avg_ci_flag_false']):.2f} | "
                f"{float(row['avg_ci_true_minus_false']):+.2f} | {row['interpretation']} |\n"
            )

        f.write("\n## Notes\n\n")
        f.write("- `true - false` below zero means the flagged equipment group has lower average CI.\n")
        f.write("- CA/OR fiber pathways are naturally lower than starch pathways, so compare within `pathway_class`, not across classes.\n")
        f.write("- `white_fox_membrane` is treated as an energy-efficiency dehydration technology that can reduce molecular-sieve/steam load.\n")
        f.write("- Dryer and technology flags often come from the technology layer merged into `operating_permit`, not solely from permit text.\n")
        f.write("- Numeric MMBtu/hr and BTU/gal fields are permit/nameplate screening metrics, not verified annual fuel use.\n")
        f.write("- Many Iowa permits are still missing clean numeric thermal, DDGS, and storage inputs.\n")

        if numeric_rows:
            f.write("\n## Numeric Energy Metric Correlations\n\n")
            f.write("| Program | Class | Metric | N | Correlation to CI |\n")
            f.write("|---|---|---|---:|---:|\n")
            for row in numeric_rows[:20]:
                corr = row["correlation_metric_to_ci"]
                f.write(
                    f"| {row['program']} | {row['pathway_class']} | {row['metric']} | "
                    f"{row['n']} | {'' if corr is None else f'{float(corr):+.2f}'} |\n"
                )

    print(f"Facility-score rows: {len(facility_rows)}")
    print(f"Summary rows: {len(summary_rows)}")
    print(f"Rows CSV: {OUT_ROWS}")
    print(f"Summary CSV: {OUT_SUMMARY}")
    print(f"Numeric CSV: {OUT_NUMERIC}")
    print(f"Markdown report: {OUT_MD}")
    print("\nTop relationships:")
    for row in summary_rows[:12]:
        print(
            f"  {row['program']} {row['pathway_class']} {row['flag']}: "
            f"true {float(row['avg_ci_flag_true']):.2f}, false {float(row['avg_ci_flag_false']):.2f}, "
            f"diff {float(row['avg_ci_true_minus_false']):+.2f}"
        )


if __name__ == "__main__":
    main()
