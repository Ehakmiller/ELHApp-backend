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


def quarter_start(value: object) -> pd.Timestamp:
    match = re.match(r"Q([1-4])\s+(\d{4})", clean_text(value), flags=re.I)
    if not match:
        return pd.Timestamp.min
    quarter = int(match.group(1))
    year = int(match.group(2))
    return pd.Timestamp(year, (quarter - 1) * 3 + 1, 1)


def feedstock_class_from_ca(row: dict) -> str:
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


def feedstock_class_from_wa(row: dict) -> str:
    value = clean_text(row.get("feedstock_class")).lower()
    code = clean_text(row.get("Fuel Pathway Code")).upper()
    if "WA012" in code:
        return "fiber/cellulosic"
    if "WA010" in code:
        return "sorghum"
    if "WA009" in code:
        return "corn starch"
    if value:
        return value
    text = f"{row.get('Fuel Name') or ''} {code} {row.get('Pathway Description') or ''}".lower()
    if "fiber" in text or "cellulosic" in text or "wa012" in text:
        return "fiber/cellulosic"
    if "sorghum" in text or "wa010" in text:
        return "sorghum"
    if "corn" in text or "wa009" in text:
        return "corn starch"
    return "unknown"


def coproduct_from_text(value: object) -> str:
    text = clean_text(value)
    if re.search(r"\bWDGS\b|wet dgs|wet distillers", text, flags=re.I):
        return "WDGS"
    if re.search(r"\bDDGS\b|dry dgs|dry distillers", text, flags=re.I):
        return "DDGS"
    if re.search(r"modified wet", text, flags=re.I):
        return "MWDGS"
    return ""


@dataclass
class Pathway:
    epm: str
    company: str
    city: str
    state: str
    program: str
    code: str
    ci: float
    feedstock_class: str
    pathway_type: str
    coproduct: str
    date_value: pd.Timestamp
    raw: dict


def latest_active_or_latest(rows: list[dict], date_getter) -> list[dict]:
    active = [row for row in rows if status_active(row)]
    source = active if active else rows
    return sorted(source, key=date_getter, reverse=True)


def load_pathways(data: list[dict]) -> tuple[list[Pathway], list[Pathway]]:
    ca_rows: list[Pathway] = []
    wa_rows: list[Pathway] = []

    for plant in data:
        if not isinstance(plant, dict):
            continue
        epm = plant_epm(plant)
        company = plant_name(plant)
        city = plant_city(plant)
        state = plant_state(plant)

        ca_source = plant.get("ca_detail") or plant.get("lcfs_detail", {}).get("ca_detail") or []
        for row in latest_active_or_latest(list(ca_source), lambda r: parse_date(r.get("detail_date"))):
            ci = pd.to_numeric(row.get("ci_score"), errors="coerce")
            if pd.isna(ci):
                continue
            ca_rows.append(
                Pathway(
                    epm=epm,
                    company=company,
                    city=city,
                    state=state,
                    program="CA",
                    code=clean_text(row.get("program")),
                    ci=float(ci),
                    feedstock_class=feedstock_class_from_ca(row),
                    pathway_type=clean_text(row.get("pathway_type")),
                    coproduct=clean_text(row.get("coproduct_type")),
                    date_value=parse_date(row.get("detail_date")),
                    raw=row,
                )
            )

        wa_source = plant.get("wa_lcfs_ci_detail") or []
        for row in latest_active_or_latest(list(wa_source), lambda r: quarter_start(r.get("Eff. Start Qtr/Yr"))):
            ci = pd.to_numeric(row.get("CI"), errors="coerce")
            if pd.isna(ci):
                continue
            wa_rows.append(
                Pathway(
                    epm=epm,
                    company=company,
                    city=city,
                    state=state,
                    program="WA",
                    code=clean_text(row.get("Fuel Pathway Code")),
                    ci=float(ci),
                    feedstock_class=feedstock_class_from_wa(row),
                    pathway_type=clean_text(row.get("Fuel Name")),
                    coproduct=coproduct_from_text(row.get("Pathway Description")),
                    date_value=quarter_start(row.get("Eff. Start Qtr/Yr")),
                    raw=row,
                )
            )

    return ca_rows, wa_rows


def dedupe_pathways(rows: list[Pathway]) -> list[Pathway]:
    best: dict[tuple[str, str, str, str], Pathway] = {}
    for row in rows:
        key = (row.epm, row.program, row.feedstock_class, row.coproduct)
        current = best.get(key)
        if current is None or row.date_value > current.date_value:
            best[key] = row
    return list(best.values())


def match_wa_to_ca(wa_rows: list[Pathway], ca_rows: list[Pathway]) -> tuple[pd.DataFrame, pd.DataFrame]:
    ca_by_epm: dict[str, list[Pathway]] = {}
    ca_by_fuzzy: dict[tuple[str, str, str], list[Pathway]] = {}
    for ca in ca_rows:
        ca_by_epm.setdefault(ca.epm, []).append(ca)
        ca_by_fuzzy.setdefault((norm_key(ca.company), norm_key(ca.city), norm_key(ca.state)), []).append(ca)

    matched = []
    unmatched = []

    for wa in wa_rows:
        candidates = ca_by_epm.get(wa.epm, [])
        match_type = "exact"
        if not candidates:
            candidates = ca_by_fuzzy.get((norm_key(wa.company), norm_key(wa.city), norm_key(wa.state)), [])
            match_type = "fuzzy" if candidates else ""

        candidates = [ca for ca in candidates if ca.feedstock_class == wa.feedstock_class]
        if wa.coproduct:
            same_coproduct = [ca for ca in candidates if ca.coproduct == wa.coproduct]
            if same_coproduct:
                candidates = same_coproduct

        if candidates:
            ca = sorted(candidates, key=lambda row: (row.date_value, -abs(row.ci - wa.ci)), reverse=True)[0]
            matched.append(
                {
                    "match_type": match_type,
                    "EPM": wa.epm,
                    "facility": wa.company,
                    "city": wa.city,
                    "state": wa.state,
                    "feedstock_class": wa.feedstock_class,
                    "pathway_type": wa.pathway_type,
                    "coproduct": wa.coproduct,
                    "wa_code": wa.code,
                    "wa_ci": wa.ci,
                    "ca_pathway": ca.pathway_type,
                    "ca_feedstock": ca.raw.get("feedstock"),
                    "ca_coproduct": ca.coproduct,
                    "ca_ci": ca.ci,
                    "wa_minus_ca_ci": wa.ci - ca.ci,
                }
            )
        else:
            unmatched.append(
                {
                    "EPM": wa.epm,
                    "facility": wa.company,
                    "city": wa.city,
                    "state": wa.state,
                    "feedstock_class": wa.feedstock_class,
                    "pathway_type": wa.pathway_type,
                    "coproduct": wa.coproduct,
                    "wa_code": wa.code,
                    "wa_ci": wa.ci,
                }
            )

    return pd.DataFrame(matched), pd.DataFrame(unmatched)


def summary_table(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame()
    return (
        matches.groupby("feedstock_class", dropna=False)
        .agg(
            count=("wa_code", "count"),
            average_wa_ci=("wa_ci", "mean"),
            average_ca_ci=("ca_ci", "mean"),
            average_wa_minus_ca_difference=("wa_minus_ca_ci", "mean"),
            median_difference=("wa_minus_ca_ci", "median"),
            min_difference=("wa_minus_ca_ci", "min"),
            max_difference=("wa_minus_ca_ci", "max"),
        )
        .reset_index()
    )


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Expected dropdown JSON to be a list")

    ca_rows, wa_rows = load_pathways(data)
    ca_rows = dedupe_pathways(ca_rows)
    wa_rows = dedupe_pathways(wa_rows)
    matches, unmatched = match_wa_to_ca(wa_rows, ca_rows)
    summary = summary_table(matches)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    matches.to_csv(OUT_DIR / "wa_with_ca_matches.csv", index=False)
    unmatched.to_csv(OUT_DIR / "wa_without_ca_matches.csv", index=False)
    summary.to_csv(OUT_DIR / "wa_ca_calibration_summary.csv", index=False)

    with pd.ExcelWriter(OUT_DIR / "wa_ca_calibration.xlsx") as writer:
        matches.to_excel(writer, sheet_name="wa_with_ca_matches", index=False)
        unmatched.to_excel(writer, sheet_name="wa_without_ca_matches", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)

    print(f"CA pathways considered: {len(ca_rows)}")
    print(f"WA pathways considered: {len(wa_rows)}")
    print(f"WA with CA matches: {len(matches)}")
    print(f"WA without CA matches: {len(unmatched)}")
    print(f"Output folder: {OUT_DIR}")


if __name__ == "__main__":
    main()
