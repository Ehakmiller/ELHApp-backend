from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


DB_PATH = Path(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db")
JSON_PATH = Path(r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json")
OUT_DIR = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\decycle_bio_screening")

FERMENTATION_CO2_MT_PER_MGY = 2_900
FORCE_LOW_OWNER_OR_NAME_TERMS = ("adm", "valero", "vcp", "big river", "icm biofuels", "crysalis")
SCS_SUMMIT_TERMS = ("summit", "summit carbon", "summit carbon solutions", "scs")

MAJOR_MARKETS = [
    ("Chicago industrial corridor", 41.8781, -87.6298),
    ("Omaha / Council Bluffs", 41.2565, -95.9345),
    ("Kansas City", 39.0997, -94.5786),
    ("St. Louis / Metro East", 38.6270, -90.1994),
    ("Minneapolis / St. Paul", 44.9778, -93.2650),
    ("Des Moines / Ames", 41.5868, -93.6250),
    ("Cedar Rapids / Iowa City", 41.9779, -91.6656),
    ("Sioux City", 42.4963, -96.4049),
    ("Quad Cities", 41.5067, -90.5151),
    ("Indianapolis", 39.7684, -86.1581),
    ("Detroit / Toledo", 42.3314, -83.0458),
    ("Cincinnati", 39.1031, -84.5120),
    ("Louisville", 38.2527, -85.7585),
    ("Memphis", 35.1495, -90.0490),
    ("Houston chemical corridor", 29.7604, -95.3698),
    ("Baton Rouge / New Orleans chemical corridor", 30.4515, -91.1871),
    ("Dallas / Fort Worth", 32.7767, -96.7970),
    ("Denver", 39.7392, -104.9903),
    ("Phoenix", 33.4484, -112.0740),
    ("Los Angeles / Inland Empire", 34.0522, -118.2437),
    ("San Francisco Bay Area", 37.7749, -122.4194),
    ("Portland", 45.5152, -122.6784),
    ("Seattle / Tacoma", 47.6062, -122.3321),
    ("Salt Lake City", 40.7608, -111.8910),
]


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(str(value).replace(",", ""))
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def truthy_text(value: Any) -> bool:
    text = clean(value).lower()
    return bool(text) and text not in {"false", "no", "none", "null", "0", "unknown", "nan"}


def get_path(obj: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = obj
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
    return current if current is not None else default


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def nearest_market(lat: float | None, lon: float | None) -> tuple[str, float | None, str, int]:
    if lat is None or lon is None:
        return "", None, "unknown", 5
    distances = [(name, haversine_miles(lat, lon, mlat, mlon)) for name, mlat, mlon in MAJOR_MARKETS]
    name, dist = min(distances, key=lambda item: item[1])
    if dist <= 50:
        return name, dist, "very near major urban/industrial market", 15
    if dist <= 100:
        return name, dist, "near major urban/industrial market", 12
    if dist <= 150:
        return name, dist, "reasonable regional market access", 9
    if dist <= 250:
        return name, dist, "moderate market access", 6
    if dist <= 400:
        return name, dist, "distant but possible market access", 3
    return name, dist, "remote from listed major markets", 0


def load_db_fields() -> dict[str, dict[str, Any]]:
    if not DB_PATH.exists():
        return {}
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            """
            SELECT
                [EPM], [Air Permit Current], [Ethanol Capacity], [Ethanol Production],
                [Status], [Corn Grind], [Grain Storage], [Days Storage], [Announced Pipeline],
                [C02 Pipeline -Direct], [C02 Pipeline -3rd Party], [Sponsor],
                [CCS Gal (Mln)], [CCS Tons (Mln)], [Rail Connect CO2],
                [Tag_Industrial_Capability], [Tag_Integrated_Chemical]
            FROM corn_processors
            WHERE [EPM] IS NOT NULL
            """,
            con,
        )
    finally:
        con.close()
    df["EPM"] = df["EPM"].astype(str).str.replace(r"\.0$", "", regex=True)
    df = df.drop_duplicates("EPM", keep="last")
    return df.set_index("EPM").to_dict(orient="index")


def active_ci_values(plant: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for value in (get_path(plant, "ci_summary.ci_lcfs_delivered_g_per_mj"), get_path(plant, "ci_summary.ci_by_feedstock.ci_corn_g_per_mj")):
        n = num(value)
        if n is not None:
            values.append(n)
    for key in ("ca_detail", "or_detail"):
        for item in get_path(plant, f"lcfs_detail.{key}", []) or []:
            if not isinstance(item, dict):
                continue
            n = num(item.get("Current certified CI") or item.get("Current Certified CI"))
            if n is not None:
                values.append(n)
    for item in plant.get("wa_lcfs_ci_detail") or []:
        if isinstance(item, dict):
            n = num(item.get("CI"))
            if n is not None:
                values.append(n)
    fed = plant.get("canadian_fed_ci")
    if isinstance(fed, dict):
        n = num(fed.get("approved_ci") or fed.get("Approved CI (gCO2e/MJ)") or fed.get("ci"))
        if n is not None:
            values.append(n)
    return values


def latest_ci_text(plant: dict[str, Any]) -> str:
    parts = []
    corn = num(get_path(plant, "ci_summary.ci_by_feedstock.ci_corn_g_per_mj"))
    fiber = num(get_path(plant, "ci_summary.ci_by_feedstock.ci_fiber_g_per_mj"))
    main = num(get_path(plant, "ci_summary.ci_lcfs_delivered_g_per_mj"))
    if main is not None:
        parts.append(f"CA/latest {main:.2f}")
    if corn is not None:
        parts.append(f"corn {corn:.2f}")
    if fiber is not None:
        parts.append(f"fiber {fiber:.2f}")
    wa_values = [num(x.get("CI")) for x in (plant.get("wa_lcfs_ci_detail") or []) if isinstance(x, dict)]
    wa_values = [x for x in wa_values if x is not None]
    if wa_values:
        parts.append(f"WA min {min(wa_values):.2f}")
    return "; ".join(parts)


def technology_flags(plant: dict[str, Any]) -> dict[str, bool]:
    tech = plant.get("tech_flags") if isinstance(plant.get("tech_flags"), dict) else {}
    op_flags = get_path(plant, "operating_permit.equipment.technology_flags", {}) or {}
    co2 = plant.get("co2_info") if isinstance(plant.get("co2_info"), dict) else {}
    return {
        "ccs_or_pipeline": truthy_text(co2.get("co2_pipeline_direct")) or truthy_text(co2.get("co2_pipeline_3rd_party")) or truthy_text(co2.get("co2_sponsor")),
        "fiber_to_ethanol": truthy_text(tech.get("fiber_technology")) or bool(op_flags.get("fiber_to_ethanol")),
        "d3_capable": bool(op_flags.get("d3_capable")) or truthy_text(tech.get("reg_pathway")) and "d3" in clean(tech.get("reg_pathway")).lower(),
        "white_fox": truthy_text(tech.get("white_fox")) or bool(op_flags.get("white_fox_membrane")),
        "chp": truthy_text(tech.get("chp")) or bool(op_flags.get("chp")),
        "waste_heat": truthy_text(tech.get("waste_heat")) or bool(op_flags.get("waste_heat_recovery")),
        "high_protein": truthy_text(tech.get("high_pro")) or bool(op_flags.get("high_protein")),
        "corn_oil": truthy_text(tech.get("dco_enhancement")) or bool(op_flags.get("corn_oil_extraction")),
        "co2_capture": bool(op_flags.get("co2_capture")),
        "rng_biogas": bool(op_flags.get("rng_biogas")),
    }


def tech_flag_text(flags: dict[str, bool]) -> str:
    labels = {
        "fiber_to_ethanol": "fiber/D3",
        "white_fox": "White Fox",
        "chp": "CHP",
        "waste_heat": "waste heat",
        "high_protein": "high protein",
        "corn_oil": "corn oil",
        "co2_capture": "CO2 capture",
        "rng_biogas": "RNG/biogas",
    }
    active = [label for key, label in labels.items() if flags.get(key)]
    return ", ".join(active) if active else "limited public low-carbon tech flags"


def pipeline_status(plant: dict[str, Any], db_row: dict[str, Any]) -> tuple[str, bool, bool, bool]:
    co2 = plant.get("co2_info") if isinstance(plant.get("co2_info"), dict) else {}
    direct = [clean(co2.get("co2_pipeline_direct")), clean(db_row.get("C02 Pipeline -Direct"))]
    third_party = [clean(co2.get("co2_pipeline_3rd_party")), clean(db_row.get("C02 Pipeline -3rd Party"))]
    sponsors = [clean(co2.get("co2_sponsor")), clean(db_row.get("Sponsor"))]
    announced = [clean(db_row.get("Announced Pipeline"))]
    all_values = [x for x in [*direct, *third_party, *sponsors, *announced] if truthy_text(x)]

    def is_yes(value: str) -> bool:
        return value.lower() in {"y", "yes", "true", "direct"}

    def is_possible(value: str) -> bool:
        return value.lower() in {"likely", "possible", "announced", "proposed"}

    def is_negative(value: str) -> bool:
        return value.lower() in {"unlikely", "no", "false", "n"}

    named_sponsors = [
        value for value in [*third_party, *sponsors]
        if truthy_text(value) and not is_possible(value) and not is_negative(value)
    ]
    summit_evidence = [
        value for value in all_values
        if any(term in value.lower() for term in SCS_SUMMIT_TERMS)
    ]
    committed = any(is_yes(value) for value in direct + third_party) or bool(named_sponsors) or bool(summit_evidence)
    possible = any(is_possible(value) for value in all_values)

    if committed:
        evidence = "; ".join(dict.fromkeys([*named_sponsors, *summit_evidence, *[v for v in direct + third_party if is_yes(v)]]))
        return evidence or "Direct or sponsored pipeline/CCS access indicated", True, True, False
    if possible:
        return "Possible future pipeline optionality", False, True, True
    return "No clear public pipeline/CCS access in available data", False, False, False


def ci_peer_percentiles(plants: list[dict[str, Any]]) -> dict[str, float]:
    rows = []
    for plant in plants:
        epm = clean(get_path(plant, "fac_info.epm"))
        ci = num(get_path(plant, "ci_summary.ci_by_feedstock.ci_corn_g_per_mj")) or num(get_path(plant, "ci_summary.ci_lcfs_delivered_g_per_mj"))
        if epm and ci is not None:
            rows.append((epm, ci))
    values = sorted(ci for _, ci in rows)
    out = {}
    for epm, ci in rows:
        rank = sum(1 for v in values if v <= ci)
        out[epm] = rank / len(values) if values else 0.5
    return out


def score_plant(plant: dict[str, Any], db_row: dict[str, Any], ci_pct: float | None) -> dict[str, Any]:
    fac = plant.get("fac_info") if isinstance(plant.get("fac_info"), dict) else {}
    epm = clean(fac.get("epm"))
    raw_capacity = num(fac.get("ethanol_capacity_mgy")) or num(db_row.get("Ethanol Capacity")) or 0
    status = clean(db_row.get("Status")) or "Unknown"
    invalid_capacity = raw_capacity > 500
    active_status = status.lower() == "active" or status == "Unknown"
    capacity = 0 if invalid_capacity or not active_status else raw_capacity
    est_co2 = capacity * FERMENTATION_CO2_MT_PER_MGY
    lat = num(fac.get("latitude"))
    lon = num(fac.get("longitude"))
    market, distance, market_note, market_score = nearest_market(lat, lon)
    pipeline_text, ccs_committed, pipeline_any, pipeline_possible = pipeline_status(plant, db_row)
    flags = technology_flags(plant)

    if capacity >= 150:
        volume_score = 20
    elif capacity >= 100:
        volume_score = 16
    elif capacity >= 60:
        volume_score = 12
    elif capacity >= 30:
        volume_score = 8
    else:
        volume_score = 4

    pipeline_score = 25 if not pipeline_any else (0 if ccs_committed else 12)
    ci_score = 10 if ci_pct is None else round(ci_pct * 20, 1)

    tech_gap_score = 20
    reductions = {
        "fiber_to_ethanol": 4,
        "d3_capable": 3,
        "white_fox": 4,
        "chp": 4,
        "waste_heat": 3,
        "high_protein": 3,
        "corn_oil": 1,
        "co2_capture": 15,
        "rng_biogas": 8,
    }
    for key, penalty in reductions.items():
        if flags.get(key):
            tech_gap_score -= penalty
    tech_gap_score = max(0, tech_gap_score)

    total = round(volume_score + pipeline_score + ci_score + tech_gap_score + market_score, 1)
    latest_ci = num(get_path(plant, "ci_summary.ci_lcfs_delivered_g_per_mj"))
    if not active_status or invalid_capacity or ccs_committed or flags.get("co2_capture") or (latest_ci is not None and latest_ci <= 35) or capacity < 30:
        tier = "Low"
    elif total >= 65:
        tier = "High"
    elif total >= 45:
        tier = "Medium"
    else:
        tier = "Low"
    if tier == "High" and pipeline_possible:
        tier = "Medium"
    forced_low = any(
        term in " ".join([clean(fac.get("ownership")), clean(fac.get("plant_name")), clean(db_row.get("Name"))]).lower()
        for term in FORCE_LOW_OWNER_OR_NAME_TERMS
    )
    if forced_low:
        tier = "Low"

    rationale_bits = []
    if invalid_capacity:
        rationale_bits.append(f"Capacity field appears invalid/outlier ({raw_capacity:,.1f} MGY), so capacity was not credited in scoring.")
    elif not active_status:
        rationale_bits.append(f"Plant status is {status}, so capacity was not credited as a near-term operating CO2 source.")
    else:
        rationale_bits.append(f"{capacity:.1f} MGY implies roughly {est_co2:,.0f} metric tons/year of fermentation CO2.")
    rationale_bits.append(pipeline_text)
    rationale_bits.append(f"CI position score {ci_score}/20 based on available corn/latest CI percentile." if ci_pct is not None else "CI position is unclear in available LCFS data.")
    rationale_bits.append(f"Technology screen: {tech_flag_text(flags)}.")
    if distance is not None:
        rationale_bits.append(f"Nearest listed market is {market} at about {distance:.0f} miles ({market_note}).")

    return {
        "priority_tier": tier,
        "total_score": total,
        "volume_score": volume_score,
        "pipeline_need_score": pipeline_score,
        "ci_need_score": ci_score,
        "technology_gap_score": tech_gap_score,
        "market_access_score": market_score,
        "epm": epm,
        "plant_name": clean(fac.get("plant_name")),
        "owner": clean(fac.get("ownership")),
        "city": clean(fac.get("city")),
        "state": clean(fac.get("state")),
        "status": status,
        "capacity_mgy": raw_capacity if not invalid_capacity else None,
        "capacity_mgy_used_for_scoring": capacity,
        "estimated_fermentation_co2_mt_per_year": round(est_co2),
        "latest_available_ci_scores": latest_ci_text(plant),
        "pipeline_ccs_status": pipeline_text,
        "ccs_committed_flag": ccs_committed,
        "technology_flags": tech_flag_text(flags),
        "nearest_market": market,
        "nearest_market_miles": round(distance, 1) if distance is not None else None,
        "market_access_note": market_note,
        "rationale": " ".join(rationale_bits),
        "tier_reason": (
            "Forced Low priority by screening override for ADM, Valero, VCP, Big River, ICM Biofuels, and Crysalis facilities."
            if forced_low
            else tier_reason(tier, capacity, pipeline_any, ccs_committed, ci_score, tech_gap_score, market_score, status, invalid_capacity, pipeline_possible)
        ),
    }


def tier_reason(tier: str, capacity: float, pipeline_any: bool, ccs_committed: bool, ci_score: float, tech_gap: int, market_score: int, status: str, invalid_capacity: bool, pipeline_possible: bool) -> str:
    if status.lower() not in {"active", "unknown"}:
        return f"Lower priority because plant status is {status}, not an active operating plant in the source table."
    if invalid_capacity:
        return "Lower priority because the source capacity field is invalid/outlier and needs manual review."
    if tier == "High":
        return "Large/meaningful CO2 source with no clear CCS route, average-to-weaker CI position, limited carbon tech, and/or useful market access."
    if tier == "Medium":
        return "Some Decycle strategic need, but one or more factors are weaker: smaller CO2 volume, partial technology adoption, less market access, or possible pipeline optionality."
    if ccs_committed:
        return "Lower priority because available data indicates pipeline/CCS/sequestration commitment or sponsor."
    if pipeline_possible:
        return "Medium priority because the plant has possible future pipeline optionality, even if a non-pipeline strategy may still be useful."
    if capacity < 30:
        return "Lower priority because the facility is small relative to likely partner-screening economics."
    if ci_score <= 5 or tech_gap <= 6:
        return "Lower priority because the plant already appears relatively optimized on CI or low-carbon technology."
    return "Lower priority based on combined volume, CI need, technology gap, and market access score."


def build_markdown(df: pd.DataFrame) -> str:
    lines = [
        "# Decycle Bio Ethanol Partner-Screening Report",
        "",
        "Purpose: identify ethanol plants that may need a non-pipeline carbon strategy and could be candidates for a CO2-to-chemicals partnership.",
        "",
        "Scoring uses existing local SQLite and LCFS dropdown JSON fields. Higher scores favor meaningful fermentation CO2 volume, lack of clear pipeline/CCS access, weaker CI position, fewer public low-carbon technology flags, and proximity to major urban/industrial markets.",
        "",
        "ADM, Valero, VCP, Big River, ICM Biofuels, and Crysalis facilities were forced to Low priority by screening override. Named SCS/Summit Carbon Solutions evidence is treated as pipeline/CCS commitment for this screening run.",
        "",
        "## Group Capacity / CO2 Volume",
        "",
        markdown_table(group_summary(df), ["priority_tier", "plant_count", "capacity_mgy_used_for_scoring", "estimated_fermentation_co2_mt_per_year"]),
        "",
        "## Top 10 Potential Partners",
        "",
    ]
    top_cols = [
        "priority_tier",
        "total_score",
        "plant_name",
        "epm",
        "owner",
        "city",
        "state",
        "status",
        "capacity_mgy",
        "capacity_mgy_used_for_scoring",
        "latest_available_ci_scores",
        "pipeline_ccs_status",
        "technology_flags",
        "nearest_market",
        "nearest_market_miles",
    ]
    lines.append(markdown_table(df.head(10), top_cols))
    lines.extend(["", "## Top 10 Rationale", ""])
    for _, row in df.head(10).iterrows():
        lines.append(f"### {row['plant_name']} ({row['epm']})")
        lines.append(f"- Tier / score: {row['priority_tier']} / {row['total_score']}")
        lines.append(f"- Score components: volume {row['volume_score']}, pipeline need {row['pipeline_need_score']}, CI need {row['ci_need_score']}, technology gap {row['technology_gap_score']}, market access {row['market_access_score']}")
        lines.append(f"- Rationale: {row['rationale']}")
        lines.append("")
    for tier in ["High", "Medium", "Low"]:
        lines.extend([f"## {tier} Priority Plants", ""])
        tier_df = df[df["priority_tier"] == tier]
        cols = ["total_score", "plant_name", "epm", "owner", "city", "state", "status", "capacity_mgy", "pipeline_ccs_status", "tier_reason"]
        lines.append(markdown_table(tier_df, cols) if not tier_df.empty else "_None_")
        lines.append("")
    return "\n".join(lines)


def build_html(df: pd.DataFrame) -> str:
    top_cols = [
        "priority_tier",
        "total_score",
        "plant_name",
        "epm",
        "owner",
        "city",
        "state",
        "status",
        "capacity_mgy",
        "latest_available_ci_scores",
        "pipeline_ccs_status",
        "technology_flags",
        "nearest_market",
        "nearest_market_miles",
    ]
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Decycle Bio Partner Screening</title>",
        "<style>body{font-family:Arial,sans-serif;margin:24px;color:#1f2937}table{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0 24px}th,td{border:1px solid #d1d5db;padding:6px;vertical-align:top}th{background:#f3f4f6;text-align:left}h1,h2,h3{color:#111827}.rationale{margin-bottom:18px}.muted{color:#6b7280}</style>",
        "</head><body>",
        "<h1>Decycle Bio Ethanol Partner-Screening Report</h1>",
        "<p>Purpose: identify ethanol plants that may need a non-pipeline carbon strategy and could be candidates for a CO2-to-chemicals partnership.</p>",
        "<p class='muted'>Scoring favors meaningful fermentation CO2 volume, lack of clear pipeline/CCS access, weaker CI position, fewer public low-carbon technology flags, and proximity to major urban/industrial markets.</p>",
        "<p class='muted'>ADM, Valero, VCP, Big River, ICM Biofuels, and Crysalis facilities were forced to Low priority by screening override. Named SCS/Summit Carbon Solutions evidence is treated as pipeline/CCS commitment for this screening run.</p>",
        "<h2>Group Capacity / CO2 Volume</h2>",
        group_summary(df).to_html(index=False, escape=True),
        "<h2>Top 10 Potential Partners</h2>",
        df.head(10)[top_cols].to_html(index=False, escape=True),
        "<h2>Top 10 Rationale</h2>",
    ]
    for _, row in df.head(10).iterrows():
        parts.append("<div class='rationale'>")
        parts.append(f"<h3>{clean(row['plant_name'])} ({clean(row['epm'])})</h3>")
        parts.append(f"<p><b>Tier / score:</b> {row['priority_tier']} / {row['total_score']}</p>")
        parts.append(
            f"<p><b>Score components:</b> volume {row['volume_score']}, pipeline need {row['pipeline_need_score']}, "
            f"CI need {row['ci_need_score']}, technology gap {row['technology_gap_score']}, market access {row['market_access_score']}</p>"
        )
        parts.append(f"<p>{clean(row['rationale'])}</p>")
        parts.append("</div>")
    for tier in ["High", "Medium", "Low"]:
        tier_df = df[df["priority_tier"] == tier]
        cols = ["total_score", "plant_name", "epm", "owner", "city", "state", "status", "capacity_mgy", "pipeline_ccs_status", "tier_reason"]
        parts.append(f"<h2>{tier} Priority Plants</h2>")
        parts.append(tier_df[cols].to_html(index=False, escape=True) if not tier_df.empty else "<p>None</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    use = df[columns].copy()

    def cell(value: Any) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        text = str(value).replace("\n", " ").replace("|", "\\|")
        return text

    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(cell(row[col]) for col in columns) + " |" for _, row in use.iterrows()]
    return "\n".join([header, sep, *rows])


def group_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("priority_tier", dropna=False)
        .agg(
            plant_count=("epm", "count"),
            capacity_mgy_used_for_scoring=("capacity_mgy_used_for_scoring", "sum"),
            estimated_fermentation_co2_mt_per_year=("estimated_fermentation_co2_mt_per_year", "sum"),
        )
        .reset_index()
    )
    order = {"High": 0, "Medium": 1, "Low": 2}
    summary["_sort"] = summary["priority_tier"].map(order).fillna(9)
    summary = summary.sort_values("_sort").drop(columns="_sort")
    summary["capacity_mgy_used_for_scoring"] = summary["capacity_mgy_used_for_scoring"].round(1)
    summary["estimated_fermentation_co2_mt_per_year"] = summary["estimated_fermentation_co2_mt_per_year"].round(0).astype(int)
    return summary


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plants = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    db_fields = load_db_fields()
    ci_pcts = ci_peer_percentiles(plants)
    rows = []
    for plant in plants:
        epm = clean(get_path(plant, "fac_info.epm"))
        if not epm:
            continue
        rows.append(score_plant(plant, db_fields.get(epm, {}), ci_pcts.get(epm)))
    df = pd.DataFrame(rows)
    tier_order = pd.CategoricalDtype(["High", "Medium", "Low"], ordered=True)
    df["priority_tier_sort"] = df["priority_tier"].astype(tier_order)
    df = df.sort_values(["priority_tier_sort", "total_score", "capacity_mgy_used_for_scoring"], ascending=[True, False, False]).drop(columns=["priority_tier_sort"])

    csv_path = OUT_DIR / "decycle_bio_partner_screening_all_plants.csv"
    xlsx_path = OUT_DIR / "decycle_bio_partner_screening.xlsx"
    md_path = OUT_DIR / "decycle_bio_partner_screening_report.md"
    html_path = OUT_DIR / "decycle_bio_partner_screening_report.html"
    df.to_csv(csv_path, index=False)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.head(10).to_excel(writer, index=False, sheet_name="Top 10")
        group_summary(df).to_excel(writer, index=False, sheet_name="Group Summary")
        for tier in ["High", "Medium", "Low"]:
            df[df["priority_tier"] == tier].to_excel(writer, index=False, sheet_name=f"{tier} Priority")
        df.to_excel(writer, index=False, sheet_name="All Reviewed")
    markdown = build_markdown(df)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(build_html(df), encoding="utf-8")

    print("Decycle Bio partner-screening report complete")
    print(f"Reviewed plants: {len(df)}")
    print(df["priority_tier"].value_counts().reindex(["High", "Medium", "Low"]).fillna(0).astype(int).to_string())
    print("\nGroup capacity / CO2 volume:")
    print(group_summary(df).to_string(index=False))
    print(f"CSV: {csv_path}")
    print(f"Excel: {xlsx_path}")
    print(f"Markdown: {md_path}")
    print(f"HTML: {html_path}")
    print("\nTop 10:")
    print(df.head(10)[["priority_tier", "total_score", "plant_name", "epm", "owner", "city", "state", "status", "capacity_mgy"]].to_string(index=False))


if __name__ == "__main__":
    main()
