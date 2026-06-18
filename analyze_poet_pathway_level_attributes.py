from __future__ import annotations

from pathlib import Path
import math
import re
import sqlite3

import numpy as np
import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
ANALYSIS_DIR = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\analysis"
)
SOURCE_MATCH_PATH = ANALYSIS_DIR / "poet_or_ca_iluc_residual_analysis.csv"

OUT_DETAIL = ANALYSIS_DIR / "poet_or_ca_pathway_attribute_comparison.csv"
OUT_FIELD_DIFFS = ANALYSIS_DIR / "poet_or_ca_pathway_attribute_field_differences.csv"
OUT_OVERRIDE = ANALYSIS_DIR / "poet_or_ca_known_outlier_override_table.csv"
OUT_REPORT = ANALYSIS_DIR / "poet_or_ca_pathway_attribute_report.md"

EXPECTED_SPREAD = 12.25
OUTLIER_CITIES = {"coonrapids", "jewell", "corning"}


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def as_float(value: object) -> float | None:
    out = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(out) else float(out)


def first(*values: object) -> object:
    for value in values:
        text = clean(value)
        if text:
            return value
    return None


def md_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.2f}"
    return str(value).replace("|", "\\|")


def md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(md_value(row[c]) for c in df.columns) + " |")
    return "\n".join(lines)


def load_source_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(DB_PATH) as con:
        ca = pd.read_sql_query('SELECT * FROM "LCFS_Detail"', con)
        ore = pd.read_sql_query('SELECT * FROM "OR_LCFS_Detail"', con)
        plants = pd.read_sql_query('SELECT * FROM "corn_processors"', con)
    return ca, ore, plants


def plant_lookup(plants: pd.DataFrame) -> dict[tuple[str, str, str], dict]:
    out: dict[tuple[str, str, str], dict] = {}
    for _, row in plants.iterrows():
        key = (norm(row.get("Name")), norm(row.get("City")), norm(row.get("State")))
        out[key] = row.to_dict()
    return out


def best_plant_row(lookup: dict[tuple[str, str, str], dict], facility: object, city: object, state: object) -> dict:
    exact = lookup.get((norm(facility), norm(city), norm(state)))
    if exact:
        return exact
    city_state = (norm(city), norm(state))
    for (name_key, city_key, state_key), row in lookup.items():
        if (city_key, state_key) == city_state and ("poet" in name_key or "poet" in norm(facility)):
            return row
    return {}


def match_ca_row(ca: pd.DataFrame, facility_id: str, source: pd.Series) -> dict:
    subset = ca.copy()
    subset["_facility_id"] = subset["Facility ID"].map(lambda v: re.sub(r"\.0$", "", clean(v)))
    subset = subset[subset["_facility_id"].eq(facility_id)]
    subset = subset[subset["Pathway Type"].map(norm).eq("starch")]
    coproduct = norm(source.get("coproduct"))
    if coproduct:
        same = subset[subset["Coproduct Type"].map(norm).eq(coproduct)]
        if not same.empty:
            subset = same
    ci = as_float(source.get("ca_ci"))
    if ci is not None:
        same_ci = subset[(pd.to_numeric(subset["Current certified CI"], errors="coerce") - ci).abs() < 0.005]
        if not same_ci.empty:
            subset = same_ci
    date = clean(source.get("ca_effective_date"))
    if date and "Date" in subset.columns:
        same_date = subset[subset["Date"].map(clean).eq(date)]
        if not same_date.empty:
            subset = same_date
    if subset.empty:
        return {}
    subset = subset.assign(_date=pd.to_datetime(subset.get("Date"), errors="coerce"))
    return subset.sort_values("_date", na_position="first").iloc[-1].drop(labels=["_facility_id", "_date"], errors="ignore").to_dict()


def match_or_row(ore: pd.DataFrame, facility_id: str, source: pd.Series) -> dict:
    subset = ore.copy()
    subset["_facility_id"] = subset["Facility ID"].map(lambda v: re.sub(r"\.0$", "", clean(v)))
    subset = subset[subset["_facility_id"].eq(facility_id)]
    subset = subset[subset["Pathway Type"].map(norm).eq("starch")]
    coproduct = norm(source.get("coproduct"))
    if coproduct:
        same = subset[subset["Co-Product Type"].map(norm).eq(coproduct)]
        if not same.empty:
            subset = same
    ci = as_float(source.get("or_ci"))
    if ci is not None:
        same_ci = subset[(pd.to_numeric(subset["Current Certified CI"], errors="coerce") - ci).abs() < 0.005]
        if not same_ci.empty:
            subset = same_ci
    date = clean(source.get("or_effective_date"))
    if date:
        same_date = subset[subset["Version Date"].map(clean).eq(date)]
        if not same_date.empty:
            subset = same_date
    if subset.empty:
        return {}
    subset = subset.assign(_date=pd.to_datetime(subset.get("Version Date"), errors="coerce"))
    return subset.sort_values("_date", na_position="first").iloc[-1].drop(labels=["_facility_id", "_date"], errors="ignore").to_dict()


def extract_destination(text: object, program: str) -> str:
    desc = clean(text)
    low = desc.lower()
    if "transported by rail into oregon" in low:
        return "Oregon; rail"
    if "transported by truck and rail to washington" in low:
        return "Washington; truck/rail"
    if "blended in california" in low:
        return "California"
    return program if desc else ""


def source_ref(row: dict, program: str) -> str:
    if not row:
        return ""
    if program == "CA":
        return "LCFS_Detail"
    return "OR_LCFS_Detail"


def unique_material_diffs(detail: pd.DataFrame) -> pd.DataFrame:
    compare_cols = [
        "ca_version_date",
        "ca_effective_date",
        "ca_expiration_date",
        "ca_pathway_status",
        "ca_feedstock_text",
        "ca_process_text",
        "ca_coproduct_text",
        "ca_transport_description",
        "ca_destination_market",
        "ca_electricity_text",
        "ca_gas_text",
        "ca_source_page_or_note",
        "or_version_date",
        "or_effective_date",
        "or_expiration_date",
        "or_pathway_status",
        "or_feedstock_text",
        "or_process_text",
        "or_coproduct_text",
        "or_transport_description",
        "or_destination_market",
        "or_electricity_text",
        "or_gas_text",
        "or_source_page_or_note",
        "facility_id",
        "fuel_code",
    ]
    rows = []
    outliers = detail[detail["poet_group"].eq("outlier")]
    normal = detail[detail["poet_group"].eq("normal_poet")]
    for col in compare_cols:
        if col not in detail.columns:
            continue
        out_vals = sorted({clean(v) for v in outliers[col].dropna() if clean(v)})
        norm_vals = sorted({clean(v) for v in normal[col].dropna() if clean(v)})
        out_set = set(out_vals)
        norm_set = set(norm_vals)
        rows.append(
            {
                "field": col,
                "outlier_values": "; ".join(out_vals),
                "normal_values": "; ".join(norm_vals),
                "outlier_unique_values": "; ".join(sorted(out_set - norm_set)),
                "normal_unique_values": "; ".join(sorted(norm_set - out_set)),
                "distinguishes_outliers": bool(out_set and out_set.isdisjoint(norm_set)),
                "comment": (
                    "materially different"
                    if out_set and norm_set and out_set.isdisjoint(norm_set)
                    else "overlaps/no clear distinction"
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ca, ore, plants = load_source_tables()
    lookup = plant_lookup(plants)
    source = pd.read_csv(SOURCE_MATCH_PATH)

    rows = []
    for _, src in source.iterrows():
        plant = best_plant_row(lookup, src.get("facility"), src.get("city"), src.get("state"))
        facility_id = re.sub(r"\.0$", "", clean(first(plant.get("CA Facility ID"), plant.get("CA Facility ID "), plant.get("Facility Id"))))
        if not facility_id:
            facility_id = re.sub(r"\.0$", "", clean(first(plant.get("CA Facility ID"), plant.get("Facility Id"))))

        ca_row = match_ca_row(ca, facility_id, src)
        or_row = match_or_row(ore, facility_id, src)

        or_desc = first(or_row.get("Pathway Description"), src.get("or_pathway_description"))
        ca_desc = first(ca_row.get("Pathway Description"), src.get("ca_pathway_description"))
        city_norm = norm(src.get("city"))
        group = "outlier" if city_norm in OUTLIER_CITIES else "normal_poet"

        rows.append(
            {
                "poet_group": group,
                "facility": clean(src.get("facility")),
                "city": clean(src.get("city")),
                "state": clean(src.get("state")),
                "facility_id": facility_id,
                "fuel_code": "",
                "or_pathway_id_or_code": clean(first(src.get("or_pathway_code"), or_row.get("Fuel Type"))),
                "ca_pathway_id_or_code": clean(first(src.get("ca_pathway_code"), ca_row.get("Fuel Type"))),
                "or_ci": as_float(src.get("or_ci")),
                "ca_ci": as_float(src.get("ca_ci")),
                "or_minus_ca_spread": as_float(src.get("or_minus_ca_spread")),
                "expected_iluc_spread": EXPECTED_SPREAD,
                "iluc_adjusted_residual": as_float(src.get("residual_ci")),
                "or_approval_or_effective_date": clean(first(or_row.get("Version Date"), src.get("or_effective_date"))),
                "ca_approval_or_effective_date": clean(first(ca_row.get("Date"), src.get("ca_effective_date"))),
                "or_version_date": clean(or_row.get("Version Date")),
                "ca_version_date": clean(ca_row.get("Version Date")),
                "or_expiration_date": clean(first(or_row.get("Eff. End Qtr/Yr"), or_row.get("Expiration Date"))),
                "ca_expiration_date": clean(ca_row.get("Expiration Date")),
                "or_pathway_status": clean(or_row.get("Status")),
                "ca_pathway_status": clean(ca_row.get("Status")),
                "or_feedstock_text": clean(first(or_row.get("Feedstock"), src.get("or_feedstock_description"))),
                "ca_feedstock_text": clean(first(ca_row.get("Feedstock"), src.get("ca_feedstock_description"))),
                "or_process_text": clean(first(or_row.get("Process Type"), src.get("or_process_type"))),
                "ca_process_text": clean(first(ca_row.get("Process Type"), src.get("ca_process_type"))),
                "or_pathway_type": clean(first(or_row.get("Pathway Type"), src.get("or_process_type"))),
                "ca_pathway_type": clean(first(ca_row.get("Pathway Type"), src.get("ca_process_type"))),
                "or_coproduct_text": clean(first(or_row.get("Co-Product Type"), src.get("coproduct"))),
                "ca_coproduct_text": clean(first(ca_row.get("Coproduct Type"), src.get("coproduct"))),
                "or_transport_description": clean(or_desc),
                "ca_transport_description": clean(ca_desc),
                "or_destination_market": extract_destination(or_desc, "Oregon"),
                "ca_destination_market": extract_destination(ca_desc, "California"),
                "or_electricity_text": clean(first(or_row.get("Electricity Type"), src.get("or_electricity_source"))),
                "ca_electricity_text": clean(first(ca_row.get("Electricity Type"), src.get("ca_electricity_source"))),
                "or_gas_text": clean(first(or_row.get("Gas Supply"), src.get("or_gas_source"))),
                "ca_gas_text": clean(first(ca_row.get("Gas Supply"), src.get("ca_gas_source"))),
                "or_source_page_or_note": source_ref(or_row, "OR"),
                "ca_source_page_or_note": source_ref(ca_row, "CA"),
                "or_pathway_description_raw": clean(or_desc),
                "ca_pathway_description_raw": clean(ca_desc),
                "or_raw_column_values": " | ".join(f"{k}={clean(v)}" for k, v in or_row.items() if clean(v)),
                "ca_raw_column_values": " | ".join(f"{k}={clean(v)}" for k, v in ca_row.items() if clean(v)),
            }
        )

    detail = pd.DataFrame(rows)
    field_diffs = unique_material_diffs(detail)

    override = detail[detail["poet_group"].eq("outlier")][
        [
            "facility",
            "city",
            "state",
            "facility_id",
            "or_ci",
            "ca_ci",
            "or_minus_ca_spread",
            "expected_iluc_spread",
            "iluc_adjusted_residual",
            "or_coproduct_text",
            "ca_coproduct_text",
        ]
    ].copy()
    override["override_reason"] = "known POET Iowa OR-to-CA corn residual outlier"
    override["recommended_rule"] = "do not infer this facility from the general OR corn +12.25 rule without review"

    detail.to_csv(OUT_DETAIL, index=False)
    field_diffs.to_csv(OUT_FIELD_DIFFS, index=False)
    override.to_csv(OUT_OVERRIDE, index=False)

    short_cols = [
        "poet_group",
        "facility",
        "city",
        "state",
        "or_ci",
        "ca_ci",
        "or_minus_ca_spread",
        "expected_iluc_spread",
        "iluc_adjusted_residual",
        "or_version_date",
        "ca_version_date",
        "or_expiration_date",
        "or_feedstock_text",
        "ca_feedstock_text",
        "or_process_text",
        "ca_process_text",
        "or_coproduct_text",
        "ca_coproduct_text",
        "or_destination_market",
        "ca_destination_market",
        "or_gas_text",
        "ca_gas_text",
        "or_source_page_or_note",
        "ca_source_page_or_note",
    ]

    specific_fields = [
        "ca_version_date",
        "or_version_date",
        "or_feedstock_text",
        "ca_feedstock_text",
        "or_transport_description",
        "or_destination_market",
        "or_coproduct_text",
        "ca_coproduct_text",
        "or_source_page_or_note",
        "ca_source_page_or_note",
    ]
    specific = field_diffs[field_diffs["field"].isin(specific_fields)].copy()
    distinguishing = field_diffs[field_diffs["distinguishes_outliers"].eq(True)].copy()

    report = []
    report.append("# POET OR-to-CA Pathway-Level Attribute Review\n")
    report.append(
        "This compares each matched POET corn-starch Oregon pathway to its matched California pathway and adds the ILUC-adjusted residual: `(OR CI + 12.25) - CA CI`.\n"
    )
    report.append(f"Rows reviewed: {len(detail)}; outlier rows: {int(detail['poet_group'].eq('outlier').sum())}.\n")
    report.append("## Ranked Comparison\n")
    report.append(md_table(detail.sort_values("iluc_adjusted_residual", ascending=False)[short_cols]))
    report.append("\n\n## Specific Field Tests\n")
    report.append(md_table(specific[["field", "outlier_values", "normal_values", "comment"]]))
    report.append("\n\n## Fields That Fully Distinguish Outliers\n")
    if distinguishing.empty:
        report.append("No available pathway-level attribute fully distinguishes Coon Rapids, Jewell, and Corning from the normal POET group.\n")
    else:
        report.append(md_table(distinguishing[["field", "outlier_values", "normal_values", "comment"]]))
    report.append("\n## Conclusion\n")
    report.append(
        "The three Iowa POET outliers remain residual outliers after the 12.25 CI ILUC adjustment, but the available source-level fields do not identify a clean pathway attribute that explains them. "
        "CA pathway vintage, Oregon version date, feedstock description, Oregon destination/transport language, coproduct labels, and source table references overlap with the normal POET group. "
        "The source does not provide separate pathway IDs, fuel codes, source pages, explicit status, or California expiration dates for these CA/OR rows. "
        "Flag the cause as unexplained pathway-level variance, keep the general OR corn calibration rule, and maintain an override table for known POET Iowa outlier facilities.\n"
    )
    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")

    print("POET pathway-level attribute review")
    print(f"Rows: {len(detail)}")
    print("\nRanked comparison")
    print(detail.sort_values("iluc_adjusted_residual", ascending=False)[short_cols].to_string(index=False))
    print("\nSpecific field tests")
    print(specific[["field", "outlier_values", "normal_values", "comment"]].to_string(index=False))
    print("\nDistinguishing fields")
    print(
        "None"
        if distinguishing.empty
        else distinguishing[["field", "outlier_values", "normal_values", "comment"]].to_string(index=False)
    )
    print(f"\nWrote: {OUT_DETAIL}")
    print(f"Wrote: {OUT_FIELD_DIFFS}")
    print(f"Wrote: {OUT_OVERRIDE}")
    print(f"Wrote: {OUT_REPORT}")


if __name__ == "__main__":
    main()
