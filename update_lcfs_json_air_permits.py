from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import json
import math
import re
import shutil


AIR_PERMIT_DIR = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits")
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
REVIEW_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\analysis\air_permit_unmatched_review.json"
)
SUMMARY_SUFFIXES = {".txt", ".md", ".json"}


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def norm_id(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        number = float(text.replace(",", ""))
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return re.sub(r"\.0$", "", text)


def norm_name(value: object) -> str:
    text = clean(value).lower()
    text = text.replace("â€“", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(llc|inc|ltd|lllp|co|company|biorefining|biorefinning|ethanol|renewable|energy|the)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def parse_float(text: object) -> float | None:
    value = clean(text)
    if not value:
        return None
    value = value.replace(",", "")
    match = re.search(r"[-+]?\d*\.?\d+", value)
    if not match:
        return None
    return float(match.group(0))


def state_abbrev(value: object) -> str:
    text = clean(value).lower().replace("\xa0", " ")
    states = {
        "iowa": "IA",
        "illinois": "IL",
        "indiana": "IN",
        "minnesota": "MN",
        "missouri": "MO",
        "nebraska": "NE",
        "north dakota": "ND",
        "ohio": "OH",
        "south dakota": "SD",
        "wisconsin": "WI",
    }
    if len(text) == 2:
        return text.upper()
    return states.get(text, clean(value).upper())


def first_match(patterns: list[str], text: str, flags: int = re.I) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return clean(match.group(1))
    return ""


def all_numbers_for_line(label_pattern: str, text: str) -> list[float]:
    match = re.search(label_pattern, text, flags=re.I)
    if not match:
        return []
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", match.group(0))]


def parse_permit(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    plant_name = first_match([r"Plant Name:\s*(.+)"], text)
    location = first_match([r"Location:\s*(.+)"], text)
    city = ""
    state = ""
    if location:
        parts = [p.strip() for p in location.split(",")]
        city = parts[0] if parts else ""
        state = state_abbrev(parts[1]) if len(parts) > 1 else ""

    epm = first_match([r"EPM Number:\s*([A-Za-z0-9.\-]+)"], text)
    ca_facility_id = first_match(
        [
            r"CA Facility ID:\s*([A-Za-z0-9.\-]+)",
            r"Facility ID \(CA\):\s*([A-Za-z0-9.\-]+)",
            r"Facility ID:\s*([A-Za-z0-9.\-]+)",
        ],
        text,
    )

    capacity = parse_float(
        first_match(
            [
                r"Nameplate Capacity:\s*~?([0-9,.]+)\s*MGY",
                r"Permitted Ethanol Capacity:\s*~?([0-9,.]+)\s*MGY",
                r"Permitted Ethanol Production/Loadout:\s*~?([0-9,.]+)\s*million gallons/year",
            ],
            text,
        )
    )

    permitted_corn = parse_float(
        first_match(
            [
                r"Permitted Grain Throughput:\s*-\s*([0-9,.]+)\s*million bushels(?:/year| per year)",
                r"Grain Throughput Limit:\s*([0-9,.]+)\s*MMbu/year",
            ],
            text,
        )
    )
    if permitted_corn is not None:
        permitted_corn *= 1_000_000

    storage = parse_float(
        first_match(
            [
                r"Total Storage Capacity [^\n]*?([0-9,.]+)\s*million bushels",
                r"Total Grain Storage Capacity:\s*approximately\s*([0-9,.]+)\s*million bushels",
                r"Total Storage Including Ground Pile:\s*~?([0-9,.]+)\s*million bushels",
                r"Total Permanent Storage:\s*~?([0-9,.]+)\s*million bushels",
            ],
            text,
        )
    )
    if storage is not None:
        storage *= 1_000_000

    fermenters = parse_float(first_match([r"-\s*(\d+)\s+Fermenters", r"Number of Fermenters:\s*(\d+)"], text))
    fermenter_each = parse_float(first_match([r"-\s*\d+\s+Fermenters\s*\n-\s*([0-9,.]+)\s*gallons each"], text))
    total_ferm = parse_float(first_match([r"Total fermentation volume:\s*([0-9,.]+)\s*million gallons"], text))
    if total_ferm is not None:
        total_ferm *= 1_000_000
    elif fermenters is not None and fermenter_each is not None:
        total_ferm = fermenters * fermenter_each

    beer_well = parse_float(first_match([r"Beer Well:\s*([0-9,.]+)\s*gallons"], text))
    beer_feed_gpm = parse_float(first_match([r"Beer feed rate:\s*([0-9,.]+)\s*GPM", r"Mash feed rate:\s*([0-9,.]+)\s*GPM"], text))
    ddgs_tons_year = parse_float(first_match([r"DDGS Loadout Limit:\s*([0-9,.]+)\s*tons/year"], text))
    ddgs_loadout_tph = parse_float(first_match([r"DDGS Loadout Capacity:\s*([0-9,.]+)\s*tph"], text))

    facts = {
        "source_file": str(path),
        "source_file_name": path.name,
        "plant_name": plant_name,
        "location": location,
        "city": city,
        "state": state,
        "epm_number": norm_id(epm),
        "ca_facility_id": norm_id(ca_facility_id),
        "ownership": first_match([r"Ownership:\s*(.+)"], text),
        "year_built": parse_float(first_match([r"Year Built:\s*~?([0-9]{4})"], text)),
        "ethanol_capacity_mgy": capacity,
        "process_type": first_match([r"Process Type:\s*\n(.+)"], text),
        "permitted_corn_throughput_bu_per_year": permitted_corn,
        "total_grain_storage_bu": storage,
        "fermenter_count": fermenters,
        "fermenter_volume_each_gal": fermenter_each,
        "total_fermenter_volume_gal": total_ferm,
        "beer_well_volume_gal": beer_well,
        "beer_feed_gpm": beer_feed_gpm,
        "ddgs_loadout_limit_tons_per_year": ddgs_tons_year,
        "ddgs_loadout_capacity_tph": ddgs_loadout_tph,
        "natural_gas": bool(re.search(r"Natural Gas", text, flags=re.I)),
        "rail_served": bool(re.search(r"\brail\b", text, flags=re.I)),
        "truck_served": bool(re.search(r"\btruck\b", text, flags=re.I)),
        "d3_capable": bool(re.search(r"D3[- ]capable|D3", text, flags=re.I)),
        "bpx_fiber_technology": bool(re.search(r"BPX", text, flags=re.I)),
        "source_text": text,
    }
    return facts


def metric(value: float | None, units: str, formula: str, confidence: str, note: str) -> dict:
    return {
        "value": None if value is None or not math.isfinite(value) else value,
        "units": units,
        "formula": formula,
        "confidence": confidence,
        "note": note,
    }


def derive(facts: dict) -> dict:
    capacity_mgy = facts.get("ethanol_capacity_mgy")
    corn_bpy = facts.get("permitted_corn_throughput_bu_per_year")
    storage_bu = facts.get("total_grain_storage_bu")
    total_ferm = facts.get("total_fermenter_volume_gal")
    beer_well = facts.get("beer_well_volume_gal")
    beer_gpm = facts.get("beer_feed_gpm")
    ddgs_tpy = facts.get("ddgs_loadout_limit_tons_per_year")
    ddgs_tph = facts.get("ddgs_loadout_capacity_tph")

    daily_corn = corn_bpy / 365 if corn_bpy else None
    derived = {
        "ethanol_yield": metric(
            (capacity_mgy * 1_000_000 / corn_bpy) if capacity_mgy and corn_bpy else None,
            "gal ethanol/bu corn",
            "ethanol_capacity_mgy * 1,000,000 / permitted_corn_throughput_bu_per_year",
            "high" if capacity_mgy and corn_bpy else "missing_inputs",
            "Uses permitted/nameplate ethanol capacity and permitted annual corn throughput.",
        ),
        "grain_throughput_per_day": metric(
            daily_corn,
            "bu/day",
            "permitted_corn_throughput_bu_per_year / 365",
            "medium" if corn_bpy else "missing_inputs",
            "Calendar-day estimate; actual operating-day throughput would be higher if the plant runs fewer than 365 days.",
        ),
        "grain_storage_days": metric(
            (storage_bu / daily_corn) if storage_bu and daily_corn else None,
            "days",
            "total_grain_storage_bu / grain_throughput_per_day",
            "medium" if storage_bu and daily_corn else "missing_inputs",
            "Uses total storage reported in the permit summary and calendar-day permitted grind.",
        ),
        "total_fermenter_volume": metric(
            total_ferm,
            "gal",
            "fermenter_count * fermenter_volume_each_gal, or reported total fermentation volume",
            "high" if total_ferm else "missing_inputs",
            "Uses reported total when present; otherwise count times individual fermenter volume.",
        ),
        "estimated_fermentation_residence_time": metric(
            (total_ferm / (beer_gpm * 60)) if total_ferm and beer_gpm else None,
            "hours",
            "total_fermenter_volume_gal / (beer_feed_gpm * 60)",
            "medium" if total_ferm and beer_gpm else "missing_inputs",
            "Approximation from beer/mash feed rate; assumes the reported GPM is continuous flow through fermentation.",
        ),
        "beer_well_hold_time": metric(
            (beer_well / (beer_gpm * 60)) if beer_well and beer_gpm else None,
            "hours",
            "beer_well_volume_gal / (beer_feed_gpm * 60)",
            "medium" if beer_well and beer_gpm else "missing_inputs",
            "Approximation from beer/mash feed rate.",
        ),
        "ddgs_tons_per_day": metric(
            (ddgs_tpy / 365) if ddgs_tpy else ((ddgs_tph * 24) if ddgs_tph else None),
            "tons/day",
            "ddgs_loadout_limit_tons_per_year / 365, else ddgs_loadout_capacity_tph * 24",
            "medium" if ddgs_tpy else ("low" if ddgs_tph else "missing_inputs"),
            "Annual permit limit preferred. TPH loadout capacity is equipment capacity, not necessarily production.",
        ),
        "ddgs_lb_per_bu": metric(
            (ddgs_tpy * 2000 / corn_bpy) if ddgs_tpy and corn_bpy else None,
            "lb DDGS/bu corn",
            "ddgs_loadout_limit_tons_per_year * 2,000 / permitted_corn_throughput_bu_per_year",
            "medium" if ddgs_tpy and corn_bpy else "missing_inputs",
            "Only calculated when annual DDGS limit and permitted corn throughput are both available.",
        ),
    }

    for beer_pct in (0.14, 0.15, 0.16):
        pct_label = f"{int(beer_pct * 100)}pct"
        derived[f"beer_feed_implied_ethanol_capacity_{pct_label}"] = metric(
            (beer_gpm * 1440 * 365 * beer_pct / 1_000_000) if beer_gpm else None,
            "MGY",
            f"beer_feed_gpm * 1,440 min/day * 365 * {beer_pct:.2f} / 1,000,000",
            "low" if beer_gpm else "missing_inputs",
            "Volumetric beer-feed estimate; does not adjust for recovery losses, density, downtime, denaturant, or actual beer strength.",
        )
    return derived


def plant_epm(row: dict) -> str:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    for value in (row.get("EPM_NUMBER"), row.get("epm_number"), row.get("epm"), row.get("EPM"), fac.get("epm")):
        out = norm_id(value)
        if out:
            return out
    return ""


def plant_ca_facility_id(row: dict) -> str:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    for value in (
        row.get("ca_facility_id"),
        row.get("facility_id"),
        row.get("Facility ID"),
        fac.get("facility_id"),
        fac.get("ca_facility_id"),
    ):
        out = norm_id(value)
        if out:
            return out
    return ""


def plant_name_state_key(row: dict) -> tuple[str, str]:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    name = row.get("plant_name") or row.get("name") or row.get("Name") or fac.get("plant_name")
    state = row.get("state") or row.get("State") or fac.get("state")
    return (norm_name(name), state_abbrev(state))


def plant_state(row: dict) -> str:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    return state_abbrev(row.get("state") or row.get("State") or fac.get("state"))


def compatible_match(facts: dict, plant: dict) -> bool:
    permit_state = state_abbrev(facts.get("state"))
    if permit_state and plant_state(plant) and permit_state != plant_state(plant):
        return False

    permit_name = norm_name(facts.get("plant_name"))
    plant_name = plant_name_state_key(plant)[0]
    if permit_name and plant_name:
        if permit_name in plant_name or plant_name in permit_name:
            return True
        return SequenceMatcher(None, permit_name, plant_name).ratio() >= 0.88
    return True


def build_indexes(data: list[dict]) -> tuple[dict[str, dict], dict[str, dict], dict[tuple[str, str], dict]]:
    by_epm: dict[str, dict] = {}
    by_ca: dict[str, dict] = {}
    by_name_state: dict[tuple[str, str], dict] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        epm = plant_epm(row)
        ca = plant_ca_facility_id(row)
        key = plant_name_state_key(row)
        if epm:
            by_epm[epm] = row
        if ca:
            by_ca[ca] = row
        if key[0] and key[1]:
            by_name_state[key] = row
    return by_epm, by_ca, by_name_state


def match_permit(facts: dict, indexes: tuple[dict[str, dict], dict[str, dict], dict[tuple[str, str], dict]]) -> tuple[dict | None, str]:
    by_epm, by_ca, by_name_state = indexes
    epm = norm_id(facts.get("epm_number"))
    if epm and epm in by_epm:
        plant = by_epm[epm]
        if compatible_match(facts, plant):
            return plant, "epm_number"
    ca = norm_id(facts.get("ca_facility_id"))
    if ca and ca in by_ca:
        plant = by_ca[ca]
        if compatible_match(facts, plant):
            return plant, "ca_facility_id"
    key = (norm_name(facts.get("plant_name")), state_abbrev(facts.get("state")))
    if key in by_name_state:
        return by_name_state[key], "normalized_plant_name_state"
    permit_name, permit_state = key
    if permit_name and permit_state:
        candidates = []
        for (plant_name, state), row in by_name_state.items():
            if state != permit_state:
                continue
            ratio = SequenceMatcher(None, permit_name, plant_name).ratio()
            if plant_name in permit_name or permit_name in plant_name or ratio >= 0.88:
                candidates.append((ratio, plant_name, row))
        candidates = sorted(candidates, reverse=True, key=lambda item: item[0])
        exactish = [
            (plant_name, row)
            for (plant_name, state), row in by_name_state.items()
            if state == permit_state and (plant_name in permit_name or permit_name in plant_name)
        ]
        if len(exactish) == 1:
            return exactish[0][1], "normalized_plant_name_state_fuzzy"
        if candidates and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.05):
            return candidates[0][2], "normalized_plant_name_state_fuzzy"
    return None, ""


def main() -> None:
    permit_files = sorted(AIR_PERMIT_DIR.glob("*"))
    permit_files = [path for path in permit_files if path.is_file() and path.suffix.lower() in SUMMARY_SUFFIXES]
    if not permit_files:
        raise RuntimeError(f"No air permit summary files found in {AIR_PERMIT_DIR}")

    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected top-level JSON list, got {type(data).__name__}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = JSON_PATH.with_name(f"{JSON_PATH.stem}.backup_{timestamp}{JSON_PATH.suffix}")
    shutil.copy2(JSON_PATH, backup_path)

    indexes = build_indexes(data)
    matched = []
    unmatched = []
    current_source_files = {path.name for path in permit_files}

    for row in data:
        if not isinstance(row, dict):
            continue
        existing = row.get("air_permit_description")
        if not isinstance(existing, dict):
            continue
        raw = existing.get("raw") if isinstance(existing.get("raw"), dict) else {}
        if raw.get("source_file_name") in current_source_files:
            row.pop("air_permit_description", None)

    for path in permit_files:
        facts = parse_permit(path)
        plant, method = match_permit(facts, indexes)
        record = {
            "raw": facts,
            "derived": derive(facts),
            "match": {
                "method": method or None,
                "matched_at": datetime.now().isoformat(timespec="seconds"),
                "source_file": str(path),
            },
        }
        if plant is None:
            unmatched.append(record)
            continue
        plant["air_permit_description"] = record
        fac = plant.get("fac_info") if isinstance(plant.get("fac_info"), dict) else {}
        matched.append(
            {
                "source_file": path.name,
                "method": method,
                "permit_plant_name": facts.get("plant_name"),
                "matched_epm": plant_epm(plant),
                "matched_ca_facility_id": plant_ca_facility_id(plant),
                "matched_plant_name": fac.get("plant_name") or plant.get("plant_name"),
            }
        )

    with JSON_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(unmatched, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Updated LCFS dropdown JSON with air permit summaries")
    print(f"JSON path: {JSON_PATH}")
    print(f"Backup path: {backup_path}")
    print(f"Air permit source folder: {AIR_PERMIT_DIR}")
    print(f"Permit files read: {len(permit_files)}")
    print(f"Matched permits: {len(matched)}")
    for item in matched:
        print(
            f"  {item['source_file']} -> EPM {item['matched_epm']} / CA {item['matched_ca_facility_id']} "
            f"({item['matched_plant_name']}) via {item['method']}"
        )
    print(f"Unmatched permits: {len(unmatched)}")
    print(f"Unmatched review path: {REVIEW_PATH}")


if __name__ == "__main__":
    main()
