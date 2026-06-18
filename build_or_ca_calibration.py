from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

import pandas as pd


JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
OUT_DIR = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\analysis"
)


def clean_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def norm_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).lower())


def plant_epm(plant: dict) -> str:
    fac = plant.get("fac_info") if isinstance(plant.get("fac_info"), dict) else {}
    for value in (
        plant.get("EPM_NUMBER"),
        plant.get("epm_number"),
        plant.get("epm"),
        plant.get("EPM"),
        plant.get("facility_id"),
        fac.get("epm"),
    ):
        text = clean_text(value)
        if text:
            return re.sub(r"\.0$", "", text)
    return ""


def plant_name(plant: dict) -> str:
    fac = plant.get("fac_info") if isinstance(plant.get("fac_info"), dict) else {}
    return clean_text(
        plant.get("plant_name")
        or plant.get("name")
        or plant.get("Name")
        or plant.get("Plant")
        or fac.get("plant_name")
    )


def plant_city(plant: dict) -> str:
    fac = plant.get("fac_info") if isinstance(plant.get("fac_info"), dict) else {}
    return clean_text(plant.get("city") or plant.get("City") or fac.get("city"))


def plant_state(plant: dict) -> str:
    fac = plant.get("fac_info") if isinstance(plant.get("fac_info"), dict) else {}
    return clean_text(plant.get("state") or plant.get("State") or fac.get("state"))


def status_active(row: dict) -> bool:
    status = clean_text(row.get("status") or row.get("Status")).lower()
    if status:
        return status == "active"
    active = clean_text(row.get("Active")).lower()
    if active:
        return active in {"1", "true", "yes", "active"}
    return True


def parse_date(value: object) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed if pd.notna(parsed) else pd.Timestamp.min


def feedstock_class_from_lcfs(row: dict) -> str:
    text = f"{row.get('feedstock') or ''} {row.get('pathway_type') or ''}".lower()
    if "fiber" in text or "cellulosic" in text:
        return "fiber/cellulosic"
    if "sorghum" in text:
        return "sorghum"
    if "wheat" in text:
        return "wheat starch"
    if "sugar" in text:
        return "sugar"
    if "corn" in text or "starch" in text:
        return "corn starch"
    return clean_text(row.get("pathway_type")).lower() or "unknown"


@dataclass
class Pathway:
    epm: str
    facility: str
    city: str
    state: str
    program: str
    code: str
    ci: float
    feedstock_class: str
    pathway_type: str
    feedstock: str
    coproduct: str
    date_value: pd.Timestamp
    raw: dict


def latest_active_or_latest(rows: list[dict]) -> list[dict]:
    active = [row for row in rows if status_active(row)]
    source = active if active else rows
    return sorted(source, key=lambda row: parse_date(row.get("detail_date")), reverse=True)


def load_pathways(data: list[dict]) -> tuple[list[Pathway], list[Pathway]]:
    ca_rows: list[Pathway] = []
    or_rows: list[Pathway] = []

    for plant in data:
        if not isinstance(plant, dict):
            continue
        epm = plant_epm(plant)
        facility = plant_name(plant)
        city = plant_city(plant)
        state = plant_state(plant)

        ca_source = plant.get("ca_detail") or plant.get("lcfs_detail", {}).get("ca_detail") or []
        for row in latest_active_or_latest(list(ca_source)):
            ci = pd.to_numeric(row.get("ci_score"), errors="coerce")
            if pd.isna(ci):
                continue
            ca_rows.append(
                Pathway(
                    epm=epm,
                    facility=facility,
                    city=city,
                    state=state,
                    program="CA",
                    code=clean_text(row.get("program")),
                    ci=float(ci),
                    feedstock_class=feedstock_class_from_lcfs(row),
                    pathway_type=clean_text(row.get("pathway_type")),
                    feedstock=clean_text(row.get("feedstock")),
                    coproduct=clean_text(row.get("coproduct_type")),
                    date_value=parse_date(row.get("detail_date")),
                    raw=row,
                )
            )

        or_source = plant.get("or_detail") or plant.get("lcfs_detail", {}).get("or_detail") or []
        for row in latest_active_or_latest(list(or_source)):
            ci = pd.to_numeric(row.get("ci_score"), errors="coerce")
            if pd.isna(ci):
                continue
            or_rows.append(
                Pathway(
                    epm=epm,
                    facility=facility,
                    city=city,
                    state=state,
                    program="OR",
                    code=clean_text(row.get("program")),
                    ci=float(ci),
                    feedstock_class=feedstock_class_from_lcfs(row),
                    pathway_type=clean_text(row.get("pathway_type")),
                    feedstock=clean_text(row.get("feedstock")),
                    coproduct=clean_text(row.get("coproduct_type")),
                    date_value=parse_date(row.get("detail_date")),
                    raw=row,
                )
            )

    return ca_rows, or_rows


def dedupe_pathways(rows: list[Pathway]) -> list[Pathway]:
    best: dict[tuple[str, str, str, str], Pathway] = {}
    for row in rows:
        key = (row.epm, row.program, row.feedstock_class, row.coproduct)
        current = best.get(key)
        if current is None or row.date_value > current.date_value:
            best[key] = row
    return list(best.values())


def match_or_to_ca(or_rows: list[Pathway], ca_rows: list[Pathway]) -> tuple[pd.DataFrame, pd.DataFrame]:
    ca_by_epm: dict[str, list[Pathway]] = {}
    ca_by_fuzzy: dict[tuple[str, str, str], list[Pathway]] = {}
    for ca in ca_rows:
        ca_by_epm.setdefault(ca.epm, []).append(ca)
        ca_by_fuzzy.setdefault((norm_key(ca.facility), norm_key(ca.city), norm_key(ca.state)), []).append(ca)

    matched = []
    unmatched = []

    for or_path in or_rows:
        candidates = ca_by_epm.get(or_path.epm, [])
        match_type = "exact"
        if not candidates:
            candidates = ca_by_fuzzy.get((norm_key(or_path.facility), norm_key(or_path.city), norm_key(or_path.state)), [])
            match_type = "fuzzy" if candidates else ""

        candidates = [ca for ca in candidates if ca.feedstock_class == or_path.feedstock_class]
        if or_path.coproduct:
            same_coproduct = [ca for ca in candidates if ca.coproduct == or_path.coproduct]
            if same_coproduct:
                candidates = same_coproduct

        if candidates:
            ca = sorted(candidates, key=lambda row: (row.date_value, -abs(row.ci - or_path.ci)), reverse=True)[0]
            matched.append(
                {
                    "match_type": match_type,
                    "EPM": or_path.epm,
                    "facility": or_path.facility,
                    "city": or_path.city,
                    "state": or_path.state,
                    "feedstock_class": or_path.feedstock_class,
                    "pathway_type": or_path.pathway_type,
                    "coproduct": or_path.coproduct,
                    "or_pathway_code": or_path.code,
                    "or_ci": or_path.ci,
                    "ca_pathway_code": ca.code,
                    "ca_pathway": ca.pathway_type,
                    "ca_feedstock": ca.feedstock,
                    "ca_coproduct": ca.coproduct,
                    "ca_ci": ca.ci,
                    "or_minus_ca_ci": or_path.ci - ca.ci,
                    "or_effective_date": or_path.raw.get("detail_date"),
                    "ca_effective_date": ca.raw.get("detail_date"),
                    "or_process_type": or_path.pathway_type,
                    "ca_process_type": ca.pathway_type,
                    "or_feedstock_description": or_path.feedstock,
                    "ca_feedstock_description": ca.feedstock,
                    "or_gas_source": or_path.raw.get("gas_supply"),
                    "ca_gas_source": ca.raw.get("gas_supply"),
                    "or_electricity_source": or_path.raw.get("electricity_type"),
                    "ca_electricity_source": ca.raw.get("electricity_type"),
                }
            )
        else:
            unmatched.append(
                {
                    "EPM": or_path.epm,
                    "facility": or_path.facility,
                    "city": or_path.city,
                    "state": or_path.state,
                    "feedstock_class": or_path.feedstock_class,
                    "pathway_type": or_path.pathway_type,
                    "coproduct": or_path.coproduct,
                    "or_pathway_code": or_path.code,
                    "or_ci": or_path.ci,
                }
            )

    return pd.DataFrame(matched), pd.DataFrame(unmatched)


def summary_table(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame()
    return (
        matches.groupby("feedstock_class", dropna=False)
        .agg(
            count=("or_pathway_code", "count"),
            average_or_ci=("or_ci", "mean"),
            average_ca_ci=("ca_ci", "mean"),
            average_or_minus_ca_difference=("or_minus_ca_ci", "mean"),
            median_difference=("or_minus_ca_ci", "median"),
            min_difference=("or_minus_ca_ci", "min"),
            max_difference=("or_minus_ca_ci", "max"),
        )
        .reset_index()
    )


def print_summary(summary: pd.DataFrame) -> None:
    print("\nCorrected OR -> CA Spread Summary")
    if summary.empty:
        print("No matches found.")
        return

    print(summary.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print("\nPractical proxy rules")
    for _, row in summary.iterrows():
        feed = clean_text(row["feedstock_class"])
        avg_diff = float(row["average_or_minus_ca_difference"])
        med_diff = float(row["median_difference"])
        spread = float(row["max_difference"]) - float(row["min_difference"])
        use_median = spread > 5.0 or abs(avg_diff - med_diff) > 1.0
        diff = med_diff if use_median else avg_diff
        sign = "-" if diff >= 0 else "+"
        print(
            f"- {feed}: CA proxy = OR CI {sign} {abs(diff):.2f} "
            f"({'median' if use_median else 'average'} OR-minus-CA adjustment)"
        )


def build_corn_diagnostics(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    corn = matches[matches["feedstock_class"].eq("corn starch")].copy()
    if corn.empty:
        return corn, corn, pd.DataFrame(), pd.DataFrame()

    corn["or_minus_ca_ci"] = pd.to_numeric(corn["or_minus_ca_ci"], errors="coerce")
    mean = corn["or_minus_ca_ci"].mean()
    std = corn["or_minus_ca_ci"].std(ddof=1)
    corn["mean_or_minus_ca"] = mean
    corn["stddev_or_minus_ca"] = std
    corn["z_score"] = (corn["or_minus_ca_ci"] - mean) / std if pd.notna(std) and std else pd.NA
    corn["outside_2_stddev"] = corn["z_score"].abs() > 2

    ordered_columns = [
        "facility",
        "city",
        "state",
        "or_pathway_code",
        "or_ci",
        "ca_pathway_code",
        "ca_ci",
        "or_minus_ca_ci",
        "or_effective_date",
        "ca_effective_date",
        "or_process_type",
        "ca_process_type",
        "coproduct",
        "ca_coproduct",
        "or_feedstock_description",
        "ca_feedstock_description",
        "or_gas_source",
        "ca_gas_source",
        "or_electricity_source",
        "ca_electricity_source",
        "match_type",
        "z_score",
        "outside_2_stddev",
    ]
    ordered_columns = [col for col in ordered_columns if col in corn.columns]
    corn = corn[ordered_columns].sort_values("or_minus_ca_ci")

    stats = pd.DataFrame(
        [
            {
                "feedstock_class": "corn starch",
                "count": len(corn),
                "average_or_minus_ca": mean,
                "median_or_minus_ca": corn["or_minus_ca_ci"].median(),
                "stddev_or_minus_ca": std,
                "min_or_minus_ca": corn["or_minus_ca_ci"].min(),
                "max_or_minus_ca": corn["or_minus_ca_ci"].max(),
                "outside_2_stddev_count": int(corn["outside_2_stddev"].sum()),
            }
        ]
    )

    company_summary = (
        corn.groupby("facility", dropna=False)
        .agg(
            matched_pathway_count=("or_pathway_code", "count"),
            average_or_ci=("or_ci", "mean"),
            average_ca_ci=("ca_ci", "mean"),
            average_or_minus_ca_spread=("or_minus_ca_ci", "mean"),
        )
        .reset_index()
        .sort_values("average_or_minus_ca_spread")
    )

    outliers = corn[corn["outside_2_stddev"]].copy()
    return corn, stats, company_summary, outliers


def build_poet_outlier_diagnostics(corn_detail: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if corn_detail.empty:
        return pd.DataFrame(), pd.DataFrame()

    poet = corn_detail[corn_detail["facility"].str.contains("poet", case=False, na=False)].copy()
    if poet.empty:
        return pd.DataFrame(), pd.DataFrame()

    outlier_names = {
        "poet biorefinning-corning llc",
        "poet biorefinning-jewell llc",
        "poet biorefinning-coon rapids",
    }

    poet["poet_group"] = poet["facility"].str.lower().map(
        lambda value: "outlier" if value in outlier_names else "normal_poet"
    )
    poet["pathway_version_dates"] = "not available in source detail"
    poet["transportation_description"] = "not available in source detail"
    poet["pathway_notes"] = "not available in source detail"
    poet["match_quality"] = poet.get("match_type", "exact")

    columns = [
        "poet_group",
        "facility",
        "state",
        "or_ci",
        "ca_ci",
        "or_minus_ca_ci",
        "or_pathway_code",
        "ca_pathway_code",
        "or_effective_date",
        "ca_effective_date",
        "pathway_version_dates",
        "or_feedstock_description",
        "ca_feedstock_description",
        "or_process_type",
        "ca_process_type",
        "coproduct",
        "ca_coproduct",
        "or_gas_source",
        "ca_gas_source",
        "or_electricity_source",
        "ca_electricity_source",
        "transportation_description",
        "pathway_notes",
        "match_quality",
    ]
    columns = [col for col in columns if col in poet.columns]
    poet = poet[columns].sort_values(["poet_group", "or_minus_ca_ci"])

    compare_fields = [
        "or_effective_date",
        "ca_effective_date",
        "or_feedstock_description",
        "ca_feedstock_description",
        "or_process_type",
        "ca_process_type",
        "coproduct",
        "ca_coproduct",
        "or_gas_source",
        "ca_gas_source",
        "or_electricity_source",
        "ca_electricity_source",
        "pathway_version_dates",
        "transportation_description",
        "pathway_notes",
        "match_quality",
    ]

    summary_rows = []
    for field in compare_fields:
        normal_values = sorted(set(clean_text(v) or "(blank)" for v in poet.loc[poet["poet_group"].eq("normal_poet"), field]))
        outlier_values = sorted(set(clean_text(v) or "(blank)" for v in poet.loc[poet["poet_group"].eq("outlier"), field]))
        summary_rows.append(
            {
                "field": field,
                "normal_poet_values": "; ".join(normal_values),
                "outlier_values": "; ".join(outlier_values),
                "differs": normal_values != outlier_values,
            }
        )

    return poet, pd.DataFrame(summary_rows)


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Expected dropdown JSON to be a list")

    ca_rows, or_rows = load_pathways(data)
    ca_rows = dedupe_pathways(ca_rows)
    or_rows = dedupe_pathways(or_rows)
    matches, unmatched = match_or_to_ca(or_rows, ca_rows)
    summary = summary_table(matches)
    corn_detail, corn_stats, company_summary, corn_outliers = build_corn_diagnostics(matches)
    poet_detail, poet_field_summary = build_poet_outlier_diagnostics(corn_detail)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    matches.to_csv(OUT_DIR / "or_with_ca_matches.csv", index=False)
    unmatched.to_csv(OUT_DIR / "or_without_ca_matches.csv", index=False)
    summary.to_csv(OUT_DIR / "or_ca_calibration_summary.csv", index=False)
    corn_detail.to_csv(OUT_DIR / "or_ca_corn_facility_comparison.csv", index=False)
    corn_detail.sort_values("or_minus_ca_ci", ascending=False).to_csv(
        OUT_DIR / "or_ca_corn_largest_positive_spreads.csv", index=False
    )
    corn_detail.sort_values("or_minus_ca_ci", ascending=True).to_csv(
        OUT_DIR / "or_ca_corn_largest_negative_spreads.csv", index=False
    )
    corn_stats.to_csv(OUT_DIR / "or_ca_corn_spread_stats.csv", index=False)
    company_summary.to_csv(OUT_DIR / "or_ca_corn_company_summary.csv", index=False)
    corn_outliers.to_csv(OUT_DIR / "or_ca_corn_outliers_2stddev.csv", index=False)
    poet_detail.to_csv(OUT_DIR / "or_ca_poet_outlier_comparison.csv", index=False)
    poet_field_summary.to_csv(OUT_DIR / "or_ca_poet_outlier_field_summary.csv", index=False)

    with pd.ExcelWriter(OUT_DIR / "or_ca_calibration.xlsx") as writer:
        matches.to_excel(writer, sheet_name="or_with_ca_matches", index=False)
        unmatched.to_excel(writer, sheet_name="or_without_ca_matches", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
        corn_detail.to_excel(writer, sheet_name="corn_facility_comparison", index=False)
        corn_detail.sort_values("or_minus_ca_ci", ascending=True).head(10).to_excel(
            writer, sheet_name="corn_top_negative", index=False
        )
        corn_detail.sort_values("or_minus_ca_ci", ascending=False).head(10).to_excel(
            writer, sheet_name="corn_top_positive", index=False
        )
        corn_stats.to_excel(writer, sheet_name="corn_stats", index=False)
        company_summary.to_excel(writer, sheet_name="corn_company_summary", index=False)
        corn_outliers.to_excel(writer, sheet_name="corn_outliers_2stddev", index=False)
        poet_detail.to_excel(writer, sheet_name="poet_outlier_comparison", index=False)
        poet_field_summary.to_excel(writer, sheet_name="poet_field_summary", index=False)

    print(f"CA pathways considered: {len(ca_rows)}")
    print(f"OR pathways considered: {len(or_rows)}")
    print(f"OR with CA matches: {len(matches)}")
    print(f"OR without CA matches: {len(unmatched)}")
    print(f"Output folder: {OUT_DIR}")
    print_summary(summary)
    if not corn_stats.empty:
        print("\nCorn Starch OR -> CA Diagnostic Stats")
        print(corn_stats.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    if not corn_outliers.empty:
        print("\nCorn Starch >2 StdDev Outliers")
        print(
            corn_outliers[
                ["facility", "city", "state", "or_ci", "ca_ci", "or_minus_ca_ci", "z_score"]
            ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
        )
    if not poet_field_summary.empty:
        print("\nPOET Outlier Field Difference Summary")
        print(poet_field_summary.to_string(index=False))


if __name__ == "__main__":
    main()
