from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import json
import math
import re

import pdfplumber


BACKEND_ROOT = Path(r"C:\Users\ehakm\Documents\ELHApp-backend")
PDF_DIR = BACKEND_ROOT / "airpermits" / "PDF"
SUMMARY_DIR = BACKEND_ROOT / "airpermits" / "summary"
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
COVERAGE_PATH = SUMMARY_DIR / "_air_permit_pdf_coverage.tsv"
MISSING_PATH = SUMMARY_DIR / "_iowa_facilities_missing_air_permit_summary.txt"
TARGET_STATES = {"IA", "MO"}

EXCLUDE_MISSING_NAMES = {"new energy blue"}
MANUAL_PDF_EPM_OVERRIDES = {
    "03-TV-029R2.pdf": "3609",
    "06-TV-006R1.pdf": "3581",
    "07-TV-001R3.pdf": "3669",
    "08-TV-004R2.pdf": "3558",
    "09-TV-002R2.pdf": "3608",
    "09-TV-005R2-M001.pdf": "3570",
    "10-TV-001R2.pdf": "3729",
    "10-TV-005R2.pdf": "3642",
    "10-TV-008R2.pdf": "3662",
    "13-TV-004R2.pdf": "3620",
    "13-TV-005R2.pdf": "3621",
    "13-TV-007R2.pdf": "3546",
    "14-TV-001R2.pdf": "3632",
    "14-TV-002R2.pdf": "3641",
    "14-TV-003R1-M001.pdf": "3754",
    "14-TV-006.pdf": "3663",
    "14-TV-010R2.pdf": "3571",
    "14-TV-011R2.pdf": "3714",
    "15-TV-003R1.pdf": "3692",
    "15-TV-006R1.pdf": "3686",
    "15-TV-009R2.pdf": "3726",
    "15-TV-010R2.pdf": "3671",
    "16-TV-004R1.pdf": "3728",
    "16-TV-005R1.pdf": "3727",
    "16-TV-006R1.pdf": "3721",
    "17-TV-002R1.pdf": "3559",
    "17-TV-003R1.pdf": "3582",
    "18-TV-004-M001.pdf": "3680",
    "19-TV-001R1.pdf": "3659",
    "19-TV-005R1.pdf": "3679",
    "20-TV-004.pdf": "3600",
    "21-TV-001R1.pdf": "3677",
    "9080_08-TV-007R2.pdf": "3557",
    "goldentriangle-craig2020opf.pdf": "3283",
    "midmoenergy-maltabend2016opb.pdf": "3649",
    "poet-biorefining-laddonia-op-application-complete-01-30-2026.pdf": "3681",
    "poet-macon-application-posted-online-may-2025.pdf": "3684",
    "show-me-ethanol-carrollton-op2022-019.pdf": "3704",
}
MANUAL_UNMATCHED_PDFS = {"25-TV-001.pdf"}  # Gevo NW Iowa RNG, not an ethanol plant.


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def norm(value: object) -> str:
    text = clean(value).lower().replace("\xa0", " ")
    text = text.replace("sothwest", "southwest")
    text = re.sub(r"\b(llc|inc|ltd|lllp|co|company|corp|corporation|ethanol|energy|renewable|renewables|biorefining|biorefinning|plant|corn|processing|processors|the)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def state_abbrev(value: object) -> str:
    text = clean(value).replace("\xa0", " ").strip()
    return text[:2].upper() if len(text) >= 2 else text.upper()


def num(value: object) -> float | None:
    text = clean(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "not available"
    if abs(value) >= 1000:
        return f"{value:,.{digits}f}"
    return f"{value:.{digits}f}"


def first_match(patterns: list[str], text: str, flags: int = re.I) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return re.sub(r"\s+", " ", clean(m.group(1)))
    return ""


def lines_with(text: str, terms: list[str], limit: int = 14) -> list[str]:
    out = []
    seen = set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        low = line.lower()
        if line and any(term in low for term in terms):
            if line not in seen:
                seen.add(line)
                out.append(line)
            if len(out) >= limit:
                break
    return out


def extract_pdf_text(path: Path, max_pages: int | None = None) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        for page in pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


@dataclass
class Facility:
    epm: str
    facility_id: str
    name: str
    ownership: str
    city: str
    state: str
    capacity_mgy: float | None
    year_built: float | None


def load_target_facilities() -> list[Facility]:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    plants = data if isinstance(data, list) else data.get("plants", [])
    rows = []
    for row in plants:
        fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
        if state_abbrev(fac.get("state")) not in TARGET_STATES:
            continue
        rows.append(
            Facility(
                epm=clean(fac.get("epm")),
                facility_id=clean(fac.get("facility_id")),
                name=clean(fac.get("plant_name")),
                ownership=clean(fac.get("ownership")),
                city=clean(fac.get("city")),
                state=state_abbrev(fac.get("state")),
                capacity_mgy=num(fac.get("ethanol_capacity_mgy")),
                year_built=num(fac.get("year_build")),
            )
        )
    return rows


def parse_identity(text: str, path: Path) -> dict:
    facility = first_match(
        [
            r"Name of Permitted Facility:\s*(.+)",
            r"Facility Name\s+City\s+Operating Permit No\.\s*\n[^\n]*?\s+([A-Za-z0-9&.,' \-]+?)\s+[A-Za-z .'-]+\s+\d{2}-TV",
            r"Facility Name:\s*(.+)",
        ],
        text,
    )
    facility = facility.replace(" LLC", " LLC").strip()
    location = first_match([r"Facility Location:\s*(.+)", r"Facility Location\s+(.+)"], text)
    permit_no = first_match([r"Air Quality Operating Permit Number:\s*([A-Za-z0-9\-]+)", r"Operating Permit No\.\s*\n.*?(\d{2}-TV[^\s]+)", r"Permit Number:\s*([A-Za-z0-9\-]+)"], text)
    expiration = first_match([r"Expiration Date:\s*(.+)", r"Ending on:\s*(.+)"], text)
    issue_date = first_match([r"\n([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})\s*\n_+", r"Commencing on:\s*(.+)"], text)
    city = ""
    state = ""
    loc_match = re.search(r",\s*([A-Za-z .'-]+),?\s+(IA|MO)\b", location)
    if loc_match:
        city = clean(loc_match.group(1))
        state = clean(loc_match.group(2)).upper()
    else:
        loc_match = re.search(r"\b([A-Za-z .'-]+),\s*(Iowa|Missouri)\b", location, flags=re.I)
        if loc_match:
            city = clean(loc_match.group(1))
            state = "MO" if clean(loc_match.group(2)).lower() == "missouri" else "IA"
    if not state:
        state = "MO" if re.search(r"\bMissouri\b|\bMO\b", text[:4000], flags=re.I) else "IA"
    return {
        "pdf_file": path.name,
        "facility_name_from_permit": facility,
        "location": location,
        "city_from_permit": city,
        "state_from_permit": state,
        "permit_number": permit_no or path.stem,
        "expiration_date": expiration,
        "issue_or_commence_date": issue_date,
    }


def match_facility(identity: dict, facilities: list[Facility], text: str) -> tuple[Facility | None, float, str]:
    if clean(identity.get("pdf_file")) in MANUAL_UNMATCHED_PDFS:
        return None, 1.0, "manual_non_ethanol_unmatched"

    override_epm = MANUAL_PDF_EPM_OVERRIDES.get(clean(identity.get("pdf_file")))
    if override_epm:
        for fac in facilities:
            if fac.epm == override_epm:
                return fac, 1.0, "manual_pdf_epm_override"

    permit_name = norm(identity.get("facility_name_from_permit"))
    permit_city = norm(identity.get("city_from_permit"))
    candidates = []
    for fac in facilities:
        name_score = max(
            SequenceMatcher(None, permit_name, norm(fac.name)).ratio(),
            SequenceMatcher(None, permit_name, norm(fac.ownership)).ratio(),
        )
        city_score = 1.0 if permit_city and permit_city == norm(fac.city) else 0.0
        bonus = 0.0
        full_text = text[:8000].lower()
        if fac.city and fac.city.lower() in full_text:
            bonus += 0.08
        if fac.name and fac.name.lower().split()[0] in full_text:
            bonus += 0.03
        score = name_score * 0.78 + city_score * 0.17 + bonus
        candidates.append((score, fac, f"name={name_score:.2f}; city={city_score:.2f}; bonus={bonus:.2f}"))
    candidates.sort(reverse=True, key=lambda item: item[0])
    if candidates and candidates[0][0] >= 0.52:
        return candidates[0][1], candidates[0][0], candidates[0][2]
    return None, candidates[0][0] if candidates else 0.0, candidates[0][2] if candidates else ""


def count_pattern(text: str, patterns: list[str]) -> int:
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, text, flags=re.I))
    return count


def best_limit_value(text: str, unit_terms: list[str], context_terms: list[str]) -> tuple[float | None, str]:
    candidates = []
    lines = normalized_lines(text)
    for idx, line in enumerate(lines):
        window = " ".join(lines[idx:idx + 3])
        low = window.lower()
        if any(term in low for term in unit_terms) and any(term in low for term in context_terms):
            units = infer_units(window)
            value = infer_constraint_value(window, units)
            if value is not None:
                annual_score = value
                if units == "MGY":
                    annual_score = value * 1_000_000
                elif units in {"gal/hr", "gal/min", "bu/hr", "tons/hr"} and "rolling" not in low and "per year" not in low:
                    annual_score = value * 0.001
                candidates.append((annual_score, value, re.sub(r"\s+", " ", window).strip()))
    if not candidates:
        return None, ""
    # Prefer large annual limits over page numbers and lb/hr rates.
    candidates = sorted(candidates, reverse=True, key=lambda item: item[0])
    return candidates[0][1], candidates[0][2]


def all_numbers(line: str) -> list[float]:
    values = []
    for match in re.findall(r"\d[\d,]*(?:\.\d+)?", line):
        try:
            values.append(float(match.replace(",", "")))
        except ValueError:
            continue
    return values


OPERATIONAL_CONTEXT_TERMS = [
    "ethanol", "alcohol", "corn", "grain", "bushel", "receiving", "loadout", "loading", "throughput",
    "production", "process", "processing", "feed rate", "feedrate", "feed", "storage", "tank", "silo",
    "bin", "ddgs", "dgs", "distillers", "wet cake", "wetcake", "syrup", "dryer", "boiler", "heater",
    "natural gas", "distillation", "beer", "centrifuge", "decanter", "tricanter", "evaporator",
    "corn oil", "fermenter", "fermentation", "hammermill", "elevator", "conveyor", "capacity",
]

OPERATIONAL_LIMIT_TERMS = [
    "limit", "limited", "shall not", "shall be less than", "less than", "not exceed", "no more than",
    "per rolling", "rolling 12", "12-month", "12 month", "annual", "per year", "tons/yr", "ton/yr",
    "tons/year", "gallons/year", "gallons per year", "bushels/year", "bushels per year",
]

DESIGN_CAPACITY_TERMS = [
    "rated capacity", "design rate", "design capacity", "maximum hourly design", "capacity=",
    "capacity =", "tons/hr", "ton/hr", "gal/min", "gpm", "gal/hr", "mmbtu/hr", "bu/hr",
    "bushels/hr", "gallons/hour", "gallons per hour",
]

EMISSION_TERMS = [
    "emission", "emissions", "voc", "hap", "nox", "so2", "pm10", "pm2.5", "particulate", "lb/hr",
    "lbs/hr", "pounds per hour", "opacity", "stack test",
]


def normalized_lines(text: str) -> list[str]:
    lines = []
    seen = set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" -\t")
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def is_emissions_only_line(line: str) -> bool:
    low = line.lower()
    if any(term in low for term in ["emission standard", "particulate matter", "emissions from", "shall not exceed the levels specified"]):
        return True
    if not any(term in low for term in EMISSION_TERMS):
        return False
    operational_hits = [term for term in OPERATIONAL_CONTEXT_TERMS if term in low]
    return len(operational_hits) <= 1 and not any(term in low for term in ["throughput", "production", "loadout", "storage", "capacity"])


def classify_constraint_category(line: str) -> str:
    low = line.lower()
    if "storage tank" in low and "material throughput" in low:
        return "Storage"
    if "truck" in low and any(term in low for term in ["loadout", "loading"]):
        return "Truck Loadout"
    if "rail" in low and any(term in low for term in ["loadout", "loading"]):
        return "Rail Loadout"
    if "ethanol" in low and any(term in low for term in ["loadout", "loading", "transfer"]):
        return "Ethanol Loadout"
    if "ethanol" in low or "alcohol" in low:
        return "Ethanol Production"
    if "grain" in low and "receiv" in low:
        return "Grain Receiving"
    if any(term in low for term in ["corn", "grain", "hammermill"]) and any(term in low for term in ["throughput", "process", "grind"]):
        return "Grain Processing"
    if any(term in low for term in ["corn elevator", "grain elevator", "conveyor"]):
        return "Grain Handling"
    if any(term in low for term in ["grain", "corn", "silo", "bin"]) and "stor" in low:
        return "Grain Storage"
    if any(term in low for term in ["ddgs", "dgs", "distillers"]):
        return "DDGS Production / Loadout"
    if "wet cake" in low or "wetcake" in low:
        return "Wetcake"
    if "syrup" in low or "cds" in low:
        return "Syrup"
    if "corn oil" in low:
        return "Corn Oil System"
    if "boiler" in low or "natural gas" in low or "heater" in low:
        return "Boiler / Natural Gas"
    if "dryer" in low:
        return "Dryer"
    if "distillation" in low or "beer feed" in low or "beer stripper" in low:
        return "Distillation / Beer Feed"
    if "beer well" in low:
        return "Beer Well"
    if any(term in low for term in ["centrifuge", "decanter", "tricanter"]):
        return "Centrifuge / Decanter"
    if "evaporator" in low:
        return "Evaporator"
    if "ferment" in low:
        return "Fermentation"
    if "stor" in low or "tank" in low:
        return "Storage"
    if "rto" in low or "thermal oxidizer" in low:
        return "RTO / Control Device"
    return "Operational Constraint"


def classify_limit_type(line: str) -> str:
    low = line.lower()
    if any(term in low for term in OPERATIONAL_LIMIT_TERMS):
        return "Permit Limit"
    if any(term in low for term in DESIGN_CAPACITY_TERMS):
        return "Design Capacity"
    return "Operational Constraint"


def infer_period(line: str) -> str:
    low = line.lower()
    if "rolling" in low and ("12-month" in low or "12 month" in low):
        return "rolling 12-month"
    if any(term in low for term in ["per year", "/yr", "annual", "yearly"]):
        return "annual"
    if any(term in low for term in ["per day", "/day", "daily"]):
        return "daily"
    if any(term in low for term in ["per hour", "/hr", "hourly", "gal/hr", "tons/hr", "mmbtu/hr"]):
        return "hourly"
    if any(term in low for term in ["per minute", "/min", "gpm", "gal/min"]):
        return "minute"
    return ""


def infer_units(line: str) -> str:
    low = line.lower()
    unit_patterns = [
        (r"mmbtu\s*/?\s*hr|mmbtu\s+per\s+hour", "MMBtu/hr"),
        (r"bushels?\s*/?\s*hr|bu\s*/?\s*hr|bushels?\s+per\s+hour", "bu/hr"),
        (r"bushels?\s*/?\s*year|bu\s*/?\s*year|bushels?\s+per\s+year|bushels?.*rolling\s+12", "bu/year"),
        (r"gallons?\s*/?\s*hour|gal\s*/?\s*hr|gallons?\s+per\s+hour", "gal/hr"),
        (r"gallons?\s*/?\s*min|gal\s*/?\s*min|gpm|gallons?\s+per\s+minute", "gal/min"),
        (r"\bmgy\b|million gallons.*rolling\s+12|million gallons per year|million gallons/year", "MGY"),
        (r"gallons?\s*/?\s*year|gal\s*/?\s*year|gallons?\s+per\s+year|gallons?.*rolling\s+12", "gal/year"),
        (r"tons?\s*/?\s*hr|tons?\s+per\s+hour", "tons/hr"),
        (r"tons?\s*/?\s*day|tons?\s+per\s+day", "tons/day"),
        (r"tons?\s*/?\s*yr|tons?\s*/?\s*year|tons?\s+per\s+year|tons?.*rolling\s+12", "tons/year"),
        (r"\bgallons?\b", "gal"),
        (r"\bbushels?\b|\bbu\b", "bu"),
        (r"\btons?\b", "tons"),
    ]
    for pattern, units in unit_patterns:
        if re.search(pattern, low):
            return units
    return ""


def infer_constraint_value(line: str, units: str) -> float | None:
    million_gal = re.search(r"([0-9][0-9,]*(?:\.\d+)?)\s+million\s+gallons?", line, flags=re.I)
    if million_gal:
        value = float(million_gal.group(1).replace(",", ""))
        return value if units == "MGY" else value * 1_000_000
    values = all_numbers(line)
    if not values:
        return None
    if units in {"gal/year", "bu/year", "tons/year", "gal", "bu", "tons"}:
        large = [value for value in values if value >= 1000]
        if large:
            return max(large)
    return values[0]


def should_capture_operational_constraint(line: str) -> bool:
    low = line.lower()
    noisy_terms = [
        "not limited to grain",
        "record the total amount",
        "calculate and record",
        "equipment operation and throughput",
        "performance tests with measured",
        "owner may submit",
        "annual capacity factor",
        "these measures may include",
    ]
    if any(term in low for term in noisy_terms):
        return False
    if is_emissions_only_line(line):
        return False
    has_context = any(term in low for term in OPERATIONAL_CONTEXT_TERMS)
    has_limit_or_capacity = any(term in low for term in OPERATIONAL_LIMIT_TERMS + DESIGN_CAPACITY_TERMS)
    has_rate_unit = bool(re.search(r"\b(?:mgy|gpm|gal/min|gal/hr|tons/hr|tons/yr|tons/year|bu/hr|bu/year|mmbtu/hr)\b", low))
    return has_context and (has_limit_or_capacity or has_rate_unit)


def add_constraint(
    constraints: list[dict],
    seen: set[tuple[str, str, str]],
    label: str,
    value: float | None,
    units: str,
    source_line: str,
    limit_type: str,
    period: str = "",
) -> None:
    if value is None and not source_line:
        return
    if label == "Operational Constraint":
        return
    if value is not None and not units:
        return
    if value is not None and units in {"gal/year", "bu/year", "tons/year"} and value < 1000:
        return
    dedupe_value = "" if value is None else f"{float(value):.6g}"
    key = (label.lower(), dedupe_value, units.lower(), (period or infer_period(source_line)).lower(), limit_type.lower())
    if key in seen:
        return
    seen.add(key)
    constraints.append(
        {
            "label": label,
            "value": value,
            "units": units,
            "period": period or infer_period(source_line),
            "limit_type": limit_type,
            "source_line": source_line,
        }
    )


def extract_operational_constraints(text: str, facts: dict | None = None) -> tuple[list[dict], list[str]]:
    constraints: list[dict] = []
    emission_lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    seen_emissions = set()

    lines = normalized_lines(text)
    for idx, base_line in enumerate(lines):
        low_base = base_line.lower()
        line = " ".join(lines[idx:idx + 3]) if any(term in low_base for term in ["shall not exceed", "not exceed", "maximum amount", "limited to"]) else base_line
        if is_emissions_only_line(line):
            low = line.lower()
            if low not in seen_emissions and any(term in low for term in EMISSION_TERMS):
                seen_emissions.add(low)
                emission_lines.append(line)
            continue
        if not should_capture_operational_constraint(line):
            continue
        units = infer_units(line)
        add_constraint(
            constraints,
            seen,
            classify_constraint_category(line),
            infer_constraint_value(line, units),
            units,
            line,
            classify_limit_type(line),
            infer_period(line),
        )

    if facts:
        known_fields = [
            ("Ethanol Production", "ethanol_capacity_mgy", "MGY", "ethanol_capacity_source", "Permit Limit"),
            ("Corn Throughput", "permitted_corn_throughput_bu_per_year", "bu/year", "permitted_corn_throughput_source", "Permit Limit"),
            ("Grain Storage", "grain_storage_bu", "bu", "grain_storage_source", "Design Capacity"),
            ("Grain Receiving", "grain_receiving_limit_bushels_per_year", "bu/year", "grain_receiving_limit_source", "Permit Limit"),
            ("Corn Elevator Capacity", "corn_elevator_tons_per_hour", "tons/hr", "corn_elevator_source", "Design Capacity"),
            ("Corn Bin Unloading Conveyor", "corn_bin_unloading_conveyor_tons_per_hour", "tons/hr", "corn_bin_unloading_conveyor_source", "Design Capacity"),
            ("Beer / Distillation Feed", "beer_feed_gpm", "gal/min", "beer_feed_source", "Design Capacity"),
            ("Evaporator Capacity", "evaporator_gal_per_hour", "gal/hr", "evaporator_gal_per_hour_source", "Design Capacity"),
            ("Centrifuge Flow Each", "centrifuge_gpm_each", "gal/min", "centrifuge_gpm_each_source", "Design Capacity"),
            ("Centrifuge Total Flow", "centrifuge_gpm_total", "gal/min", "centrifuge_gpm_total_source", "Design Capacity"),
            ("Centrifuge Annual Flow", "centrifuge_gpy_total", "gal/year", "centrifuge_gpy_total_source", "Design Capacity"),
            ("Wetcake Limit", "wetcake_limit_tons_per_year", "tons/year", "wetcake_limit_source", "Permit Limit"),
            ("Wetcake Production Rate", "wetcake_tons_per_hour", "tons/hr", "wetcake_tons_per_hour_source", "Design Capacity"),
            ("Syrup Limit", "syrup_limit_tons_per_year", "tons/year", "syrup_limit_source", "Permit Limit"),
            ("DDGS Production", "ddgs_limit_tons_per_year", "tons/year", "ddgs_limit_source", "Permit Limit"),
            ("Dryer Heat Input", "dryer_heat_mmbtu_hr", "MMBtu/hr", "dryer_heat_source", "Design Capacity"),
            ("Corn Oil System", "corn_oil_limit_value", "", "corn_oil_limit_source", "Operational Constraint"),
        ]
        for label, value_key, units, source_key, default_type in known_fields:
            source = clean(facts.get(source_key))
            add_constraint(
                constraints,
                seen,
                label,
                facts.get(value_key),
                units or infer_units(source),
                source,
                classify_limit_type(source) if source else default_type,
                infer_period(source),
            )

    priority = {"Permit Limit": 0, "Operational Constraint": 1, "Design Capacity": 2}
    constraints.sort(key=lambda item: (priority.get(item.get("limit_type"), 9), item.get("label", ""), item.get("period", "")))
    return constraints[:140], emission_lines[:80]


def best_large_line_value(text: str, include_terms: list[str], min_value: float = 1000) -> tuple[float | None, str]:
    candidates = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        low = line.lower()
        if all(term in low for term in include_terms):
            nums = [value for value in all_numbers(line) if value >= min_value]
            if nums:
                candidates.append((max(nums), line))
    if not candidates:
        return None, ""
    return max(candidates, key=lambda item: item[0])


def first_line_value(text: str, patterns: list[str]) -> tuple[float | None, str]:
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.I)
            if match:
                value = num(match.group(1))
                if value is not None:
                    return value, line
    return None, ""


def lines_with_any(text: str, terms: list[str], limit: int = 20) -> list[str]:
    return lines_with(text, terms, limit)


def word_or_digit_number(text_value: str) -> float | None:
    value = num(text_value)
    if value is not None:
        return value
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    return float(words.get(text_value.strip().lower())) if text_value else None


def parse_facts(text: str, identity: dict, facility: Facility | None) -> dict:
    lower = text.lower()
    section_start_match = re.search(r"i\.\s*facility description and equipment list\s*\n\s*facility name", text, flags=re.I)
    section_start = section_start_match.start() if section_start_match else lower.find("equipment list")
    if section_start < 0:
        section_start = 0
    section_end_candidates = [
        m.start() for m in re.finditer(r"ii\.\s*plant\s*[- ]?\s*wide conditions", text, flags=re.I)
        if m.start() > section_start
    ]
    section_end = section_end_candidates[0] if section_end_candidates else min(len(text), section_start + 18000)
    equipment = text[section_start:section_end]
    ethanol_limit, ethanol_line = best_limit_value(text, ["gallon", "mgy", "mgpy"], ["ethanol", "production", "denatured"])
    mo_ethanol_limit, mo_ethanol_line = best_large_line_value(text, ["produce less than", "ethanol", "gallon"], 1_000_000)
    if mo_ethanol_limit is not None:
        ethanol_limit, ethanol_line = mo_ethanol_limit, mo_ethanol_line
    corn_limit, corn_line = best_limit_value(text, ["bushel"], ["corn", "grain", "throughput", "received", "processed", "hammermill"])
    ddgs_limit, ddgs_line = best_limit_value(text, ["tons/yr", "tons per year", "ton/yr", "tons/year"], ["ddgs", "distillers", "dgs"])
    corn_oil_limit, corn_oil_line = best_limit_value(text, ["gallon", "lb", "pound", "tons"], ["corn oil"])

    grain_tpy, grain_tpy_line = first_line_value(text, [r"Truck and Rail Grain\s+([0-9,.]+)\s*tons of grain"])
    if corn_limit is None and grain_tpy is not None:
        corn_limit = grain_tpy * 2000 / 56
        corn_line = grain_tpy_line
    wetcake_tpy, wetcake_line = best_large_line_value(text, ["wet cake", "tons"], 1000)
    syrup_tpy, syrup_line = best_large_line_value(text, ["syrup", "tons"], 1000)
    grain_elevator_tph, grain_elevator_line = first_line_value(text, [r"Corn Elevator\s+[0-9]{4}\s+([0-9,.]+)\s*tons/hr"])
    grain_unloading_tph, grain_unloading_line = first_line_value(text, [r"Corn Bin Unloading Conveyor.*?\s([0-9,.]+)\s*tons/hr"])
    beer_feed_gpm, beer_feed_line = first_line_value(
        text,
        [
            r"bottlenecked maximum hourly design rate is\s+([0-9,.]+)\s*gal/min",
            r"production rate of\s+([0-9,.]+)\s*gal/min",
        ],
    )
    evaporator_gph, evaporator_gph_line = first_line_value(text, [r"Evaporator.*?\s([0-9,.]+)\s*gal/hr"])
    concentrate_tank_gal, concentrate_tank_line = first_line_value(text, [r"Concentrate Tank.*?\s([0-9,.]+)\s*gallons?"])
    thin_stillage_recycle_pct, thin_stillage_recycle_line = first_line_value(text, [r"Approximately\s+([0-9,.]+)%\s+of the thin stillage"])
    evaporation_stages = None
    evaporation_stage_line = ""
    m_stages = re.search(r"There are\s+([A-Za-z0-9,.]+)\s+stages of evaporation", text, flags=re.I)
    if m_stages:
        evaporation_stages = word_or_digit_number(m_stages.group(1))
        evaporation_stage_line = re.sub(r"\s+", " ", m_stages.group(0)).strip()
    centrifuge_count, centrifuge_count_line = first_line_value(
        text,
        [
            r"Emissions from\s*\(([0-9,.]+)\)\s*(?:whole stillage\s*)?centrifuges",
            r"Centrifuges\s*#1\s*through\s*#([0-9,.]+)",
        ],
    )
    centrifuge_gpm_each, centrifuge_gpm_each_line = first_line_value(
        text,
        [
            r"([0-9,.]+)\s*gpm\s*\(each centrifuge\)",
            r"([0-9,.]+)\s*gallons liquid per minute per individual centrifuges",
        ],
    )
    centrifuge_gpm_total, centrifuge_gpm_total_line = first_line_value(text, [r"([0-9,.]+)\s*gallons liquid per minute through all centrifuges"])
    centrifuge_gph_total, centrifuge_gph_total_line = first_line_value(text, [r"([0-9,.]+)\s*gallons liquid per hour through all centrifuges"])
    centrifuge_gpy_total, centrifuge_gpy_total_line = first_line_value(text, [r"([0-9,.]+)\s*gallons liquid per year through all centrifuges"])
    wetcake_tph, wetcake_tph_line = first_line_value(
        text,
        [
            r"Capacity=\s*([0-9,.]+)\s*tons/hr maximum wetcake production rate",
            r"Wet Cake Production\s+([0-9,.]+)\s*ton",
        ],
    )
    dryer_heat, dryer_heat_line = first_line_value(text, [r"Dryer Rated Capacity=\s*([0-9,.]+)\s*MMBTU/hr", r"dryer.*?([0-9,.]+)\s*MMBtu/hr"])
    corn_oil_centrifuge_stack = bool(re.search(r"corn oil centrifuge", text, flags=re.I))

    if ethanol_limit and ethanol_limit > 1000:
        # Convert gallons/year to MGY when the line is not already clearly MGY.
        ethanol_mgy = ethanol_limit / 1_000_000 if ethanol_limit > 10000 else ethanol_limit
    else:
        ethanol_mgy = facility.capacity_mgy if facility else None

    if corn_limit and corn_limit < 100000:
        corn_bpy = None
    else:
        corn_bpy = corn_limit

    dryer_count = len(set(re.findall(r"\b(?:DDGS\s+)?Dryer\s*(?:#?\s*[A-Z0-9]+|[A-Z])?", equipment, flags=re.I)))
    hammermill_count = count_pattern(equipment, [r"\bHammermill\b", r"\bHammermills\b"])
    boiler_count = count_pattern(equipment, [r"\bBoiler\b", r"\bProcess Heater\b", r"\bHeat Recovery Boiler\b"])
    rto_count = count_pattern(text, [r"\bRTO\b", r"Regenerative Thermal Oxidizer", r"Thermal Oxidizer"])
    tank_count = count_pattern(equipment, [r"Storage Tank", r"Ethanol Storage", r"Denaturant Storage"])
    fermenter_line = first_match([r"(\d+\s+Fermentation Process Vessels and Beer Well)", r"(Fermentation Process\s+Vessels.+?Beer Well)", r"(Ethanol Production/Fermentation)"], equipment)
    fermenter_count = num(first_match([r"(\d+)\s+Fermentation Process Vessels"], equipment))
    beer_well_present = bool(re.search(r"Beer Well", equipment, flags=re.I))
    total_ferm_volume = None
    beer_well_volume = None
    if beer_feed_gpm is None:
        beer_feed_gpm = None

    storage_value, storage_line = best_limit_value(text, ["bushel"], ["storage", "silo", "bin"])
    if storage_value and storage_value < 100000:
        storage_value = None

    facts = {
        "ethanol_capacity_mgy": ethanol_mgy,
        "ethanol_capacity_source": ethanol_line or ("dropdown facility capacity" if facility and facility.capacity_mgy else ""),
        "permitted_corn_throughput_bu_per_year": corn_bpy,
        "permitted_corn_throughput_source": corn_line,
        "grain_storage_bu": storage_value,
        "grain_storage_source": storage_line,
        "fermenter_count": fermenter_count,
        "fermentation_equipment": fermenter_line,
        "total_fermenter_volume_gal": total_ferm_volume,
        "beer_well_present": beer_well_present,
        "beer_well_volume_gal": beer_well_volume,
        "beer_feed_gpm": beer_feed_gpm,
        "beer_feed_source": beer_feed_line,
        "dryer_count_mentions": dryer_count,
        "dryer_heat_mmbtu_hr": dryer_heat,
        "dryer_heat_source": dryer_heat_line,
        "hammermill_mentions": hammermill_count,
        "boiler_or_heater_mentions": boiler_count,
        "rto_mentions": rto_count,
        "tank_mentions": tank_count,
        "grain_receiving_limit_tons_per_year": grain_tpy,
        "grain_receiving_limit_source": grain_tpy_line,
        "grain_receiving_limit_bushels_per_year": (grain_tpy * 2000 / 56) if grain_tpy is not None else None,
        "corn_elevator_tons_per_hour": grain_elevator_tph,
        "corn_elevator_source": grain_elevator_line,
        "corn_bin_unloading_conveyor_tons_per_hour": grain_unloading_tph,
        "corn_bin_unloading_conveyor_source": grain_unloading_line,
        "wetcake_limit_tons_per_year": wetcake_tpy,
        "wetcake_limit_source": wetcake_line,
        "syrup_limit_tons_per_year": syrup_tpy,
        "syrup_limit_source": syrup_line,
        "wetcake_tons_per_hour": wetcake_tph,
        "wetcake_tons_per_hour_source": wetcake_tph_line,
        "centrifuge_count": centrifuge_count,
        "centrifuge_count_source": centrifuge_count_line,
        "centrifuge_gpm_each": centrifuge_gpm_each,
        "centrifuge_gpm_each_source": centrifuge_gpm_each_line,
        "centrifuge_gpm_total": centrifuge_gpm_total,
        "centrifuge_gpm_total_source": centrifuge_gpm_total_line,
        "centrifuge_gph_total": centrifuge_gph_total,
        "centrifuge_gph_total_source": centrifuge_gph_total_line,
        "centrifuge_gpy_total": centrifuge_gpy_total,
        "centrifuge_gpy_total_source": centrifuge_gpy_total_line,
        "evaporator_gal_per_hour": evaporator_gph,
        "evaporator_gal_per_hour_source": evaporator_gph_line,
        "concentrate_tank_gal": concentrate_tank_gal,
        "concentrate_tank_source": concentrate_tank_line,
        "thin_stillage_recycle_percent": thin_stillage_recycle_pct,
        "thin_stillage_recycle_source": thin_stillage_recycle_line,
        "evaporation_stages": evaporation_stages,
        "evaporation_stages_source": evaporation_stage_line,
        "corn_oil_centrifuge_stack": corn_oil_centrifuge_stack,
        "ddgs_limit_tons_per_year": ddgs_limit if ddgs_limit and ddgs_limit > 1000 else None,
        "ddgs_limit_source": ddgs_line,
        "corn_oil_limit_value": corn_oil_limit,
        "corn_oil_limit_source": corn_oil_line,
        "grain_lines": lines_with(equipment + "\n" + text[:30000], ["grain", "corn receiving", "storage silo", "bushel"], 12),
        "dryer_lines": lines_with(equipment, ["dryer", "ddgs"], 12),
        "boiler_lines": lines_with(equipment + "\n" + text[:30000], ["boiler", "heater", "mmbtu"], 12),
        "rto_lines": lines_with(equipment + "\n" + text[:30000], ["rto", "thermal oxidizer", "regenerative thermal"], 12),
        "tank_lines": lines_with(equipment, ["storage tank", "ethanol storage", "denaturant", "corn oil tank"], 14),
        "ddgs_lines": lines_with(equipment + "\n" + text[:30000], ["ddgs", "dgs", "distillers"], 14),
        "corn_oil_lines": lines_with(equipment + "\n" + text[:30000], ["corn oil", "tricanter"], 10),
        "distillation_lines": lines_with_any(text, ["distillation column", "beer stripper", "rectifier", "side stripper", "molecular sieve", "demethyl", "industrial distillation"], 24),
        "evaporator_lines": lines_with_any(text, ["evaporator", "thin stillage", "concentrate tank", "syrup storage", "condensed distillers", "cds"], 24),
        "centrifuge_lines": lines_with_any(text, ["centrifuge", "tricanter", "decanter"], 16),
        "permit_constraint_lines": lines_with(text, ["emission limit", "operational limit", "throughput", "tons/yr", "gallons", "bushels", "hap", "voc"], 24),
    }
    operational_limits, emission_limit_lines = extract_operational_constraints(text, facts)
    facts["operational_limits"] = operational_limits
    facts["emission_limit_lines"] = emission_limit_lines
    return facts


def derived_metrics(facts: dict) -> dict:
    cap = facts.get("ethanol_capacity_mgy")
    corn = facts.get("permitted_corn_throughput_bu_per_year")
    storage = facts.get("grain_storage_bu")
    ddgs = facts.get("ddgs_limit_tons_per_year")
    ferm_vol = facts.get("total_fermenter_volume_gal")
    beer_well = facts.get("beer_well_volume_gal")
    beer_gpm = facts.get("beer_feed_gpm")
    daily_corn = corn / 365 if corn else None
    return {
        "ethanol_yield_gal_per_bu": (cap * 1_000_000 / corn) if cap and corn else None,
        "ddgs_yield_ton_per_bu": (ddgs / corn) if ddgs and corn else None,
        "ddgs_lb_per_bu": (ddgs * 2000 / corn) if ddgs and corn else None,
        "corn_oil_yield": None,
        "grain_throughput_bu_per_day": daily_corn,
        "grain_storage_days": (storage / daily_corn) if storage and daily_corn else None,
        "fermenter_volume_gal": ferm_vol,
        "beer_well_volume_gal": beer_well,
        "estimated_fermentation_time_hr": (ferm_vol / (beer_gpm * 60)) if ferm_vol and beer_gpm else None,
        "beer_well_hold_time_hr": (beer_well / (beer_gpm * 60)) if beer_well and beer_gpm else None,
        "ddgs_tons_per_day": (ddgs / 365) if ddgs else None,
    }


def confidence_for(value: object) -> str:
    return "medium" if value is not None else "missing input"


def bullet_lines(lines: list[str], fallback: str = "Not specifically identified in extracted permit text.") -> str:
    if not lines:
        return f"- {fallback}"
    return "\n".join(f"- {line}" for line in lines)


def write_summary(path: Path, identity: dict, facility: Facility | None, match_score: float, match_note: str, facts: dict, metrics: dict) -> None:
    epm = facility.epm if facility else "UNMATCHED"
    name = facility.name if facility else identity.get("facility_name_from_permit", "Unknown")
    city = facility.city if facility else identity.get("city_from_permit", "")
    state = facility.state if facility else clean(identity.get("state_from_permit")) or "IA"
    out = []
    out.append(f"EPM Number: {epm}")
    out.append(f"Plant Name: {name}")
    out.append(f"Permit Facility Name: {identity.get('facility_name_from_permit')}")
    out.append(f"Location: {city}, {state}")
    out.append(f"Source Permit File: {identity.get('pdf_file')}")
    out.append(f"Permit Number: {identity.get('permit_number')}")
    out.append(f"Permit Expiration Date: {identity.get('expiration_date')}")
    out.append(f"Match Confidence: {match_score:.2f} ({match_note})")
    out.append("")
    out.append("Facility Identity:")
    out.append(f"- Ownership: {facility.ownership if facility else 'not matched'}")
    out.append(f"- CA Facility ID: {facility.facility_id if facility else 'not matched'}")
    out.append(f"- Dropdown capacity: {fmt_num(facility.capacity_mgy, 1) if facility else 'not matched'} MGY")
    out.append(f"- Year built: {fmt_num(facility.year_built, 0) if facility else 'not matched'}")
    out.append("")
    out.append("Capacity / Throughput Limits:")
    out.append(f"- Ethanol capacity used: {fmt_num(facts.get('ethanol_capacity_mgy'), 2)} MGY")
    out.append(f"- Ethanol capacity source: {facts.get('ethanol_capacity_source') or 'not found in permit; dropdown capacity used if available'}")
    out.append(f"- Permitted corn/grain throughput: {fmt_num(facts.get('permitted_corn_throughput_bu_per_year'), 0)} bu/year")
    out.append(f"- Throughput source line: {facts.get('permitted_corn_throughput_source') or 'not identified'}")
    out.append("")
    out.append("Operational Limits / Design Capacities:")
    operational_limits = facts.get("operational_limits") or []
    if operational_limits:
        for item in operational_limits:
            value = fmt_num(item.get("value"), 2) if item.get("value") is not None else "not available"
            units = f" {item.get('units')}" if item.get("units") else ""
            period = f" | Period: {item.get('period')}" if item.get("period") else ""
            source = f" | Source: {item.get('source_line')}" if item.get("source_line") else ""
            out.append(f"- {item.get('label')}: {value}{units} | Type: {item.get('limit_type')}{period}{source}")
    else:
        out.append("- Not specifically identified in extracted permit text.")
    out.append("")
    out.append("Fermentation Equipment:")
    out.append(f"- Fermentation line: {facts.get('fermentation_equipment') or 'not specifically identified'}")
    out.append(f"- Fermenter count parsed: {fmt_num(facts.get('fermenter_count'), 0)}")
    out.append(f"- Beer well present: {'yes' if facts.get('beer_well_present') else 'not identified'}")
    out.append("")
    out.append("Grain Handling / Storage:")
    out.append(f"- Grain storage parsed: {fmt_num(facts.get('grain_storage_bu'), 0)} bu")
    out.append(bullet_lines(facts.get("grain_lines", [])))
    out.append("")
    out.append("Dryers:")
    out.append(f"- Dryer mentions parsed: {facts.get('dryer_count_mentions')}")
    out.append(f"- Dryer rated capacity: {fmt_num(facts.get('dryer_heat_mmbtu_hr'), 2)} MMBtu/hr")
    out.append(f"- Dryer rated capacity source: {facts.get('dryer_heat_source') or 'not identified'}")
    out.append(bullet_lines(facts.get("dryer_lines", [])))
    out.append("")
    out.append("Boilers / Process Heaters:")
    out.append(f"- Boiler/heater mentions parsed: {facts.get('boiler_or_heater_mentions')}")
    out.append(bullet_lines(facts.get("boiler_lines", [])))
    out.append("")
    out.append("Thermal Oxidizers / RTO:")
    out.append(f"- RTO/thermal oxidizer mentions parsed: {facts.get('rto_mentions')}")
    out.append(bullet_lines(facts.get("rto_lines", [])))
    out.append("")
    out.append("Tanks:")
    out.append(f"- Storage tank mentions parsed: {facts.get('tank_mentions')}")
    out.append(bullet_lines(facts.get("tank_lines", [])))
    out.append("")
    out.append("DDGS / Corn Oil Systems:")
    out.append(f"- DDGS limit parsed: {fmt_num(facts.get('ddgs_limit_tons_per_year'), 0)} tons/year")
    out.append(f"- DDGS source line: {facts.get('ddgs_limit_source') or 'not identified'}")
    out.append(f"- Wetcake production rate: {fmt_num(facts.get('wetcake_tons_per_hour'), 2)} tons/hr")
    out.append(f"- Wetcake production source: {facts.get('wetcake_tons_per_hour_source') or 'not identified'}")
    out.append(f"- Wetcake limit: {fmt_num(facts.get('wetcake_limit_tons_per_year'), 0)} tons/year")
    out.append(f"- Wetcake limit source: {facts.get('wetcake_limit_source') or 'not identified'}")
    out.append(f"- Syrup limit: {fmt_num(facts.get('syrup_limit_tons_per_year'), 0)} tons/year")
    out.append(f"- Syrup limit source: {facts.get('syrup_limit_source') or 'not identified'}")
    out.append(bullet_lines(facts.get("ddgs_lines", [])))
    out.append(f"- Corn oil source line: {facts.get('corn_oil_limit_source') or 'not identified'}")
    out.append(f"- Corn oil centrifuge stack: {'yes' if facts.get('corn_oil_centrifuge_stack') else 'not identified'}")
    out.append(bullet_lines(facts.get("corn_oil_lines", [])))
    out.append("")
    out.append("Missouri Structured Fields:")
    out.append(f"- Grain receiving limit: {fmt_num(facts.get('grain_receiving_limit_tons_per_year'), 0)} tons/year")
    out.append(f"- Grain receiving source: {facts.get('grain_receiving_limit_source') or 'not identified'}")
    out.append(f"- Grain receiving bushels equivalent: {fmt_num(facts.get('grain_receiving_limit_bushels_per_year'), 0)} bu/year")
    out.append(f"- Corn elevator capacity: {fmt_num(facts.get('corn_elevator_tons_per_hour'), 2)} tons/hr")
    out.append(f"- Corn elevator source: {facts.get('corn_elevator_source') or 'not identified'}")
    out.append(f"- Corn bin unloading conveyor capacity: {fmt_num(facts.get('corn_bin_unloading_conveyor_tons_per_hour'), 2)} tons/hr")
    out.append(f"- Corn bin unloading conveyor source: {facts.get('corn_bin_unloading_conveyor_source') or 'not identified'}")
    out.append(f"- Beer/distillation feed: {fmt_num(facts.get('beer_feed_gpm'), 2)} gal/min")
    out.append(f"- Beer/distillation feed source: {facts.get('beer_feed_source') or 'not identified'}")
    out.append(f"- Evaporator capacity: {fmt_num(facts.get('evaporator_gal_per_hour'), 2)} gal/hr")
    out.append(f"- Evaporator source: {facts.get('evaporator_gal_per_hour_source') or 'not identified'}")
    out.append(f"- Concentrate tank: {fmt_num(facts.get('concentrate_tank_gal'), 0)} gal")
    out.append(f"- Concentrate tank source: {facts.get('concentrate_tank_source') or 'not identified'}")
    out.append(f"- Thin stillage recycle: {fmt_num(facts.get('thin_stillage_recycle_percent'), 2)} percent")
    out.append(f"- Thin stillage recycle source: {facts.get('thin_stillage_recycle_source') or 'not identified'}")
    out.append(f"- Evaporation stages: {fmt_num(facts.get('evaporation_stages'), 0)}")
    out.append(f"- Evaporation stages source: {facts.get('evaporation_stages_source') or 'not identified'}")
    out.append(f"- Centrifuge count: {fmt_num(facts.get('centrifuge_count'), 0)}")
    out.append(f"- Centrifuge count source: {facts.get('centrifuge_count_source') or 'not identified'}")
    out.append(f"- Centrifuge flow each: {fmt_num(facts.get('centrifuge_gpm_each'), 2)} gal/min")
    out.append(f"- Centrifuge flow each source: {facts.get('centrifuge_gpm_each_source') or 'not identified'}")
    out.append(f"- Centrifuge total flow: {fmt_num(facts.get('centrifuge_gpm_total'), 2)} gal/min")
    out.append(f"- Centrifuge total flow source: {facts.get('centrifuge_gpm_total_source') or 'not identified'}")
    out.append(f"- Centrifuge total hourly flow: {fmt_num(facts.get('centrifuge_gph_total'), 0)} gal/hr")
    out.append(f"- Centrifuge total hourly flow source: {facts.get('centrifuge_gph_total_source') or 'not identified'}")
    out.append(f"- Centrifuge total annual flow: {fmt_num(facts.get('centrifuge_gpy_total'), 0)} gal/year")
    out.append(f"- Centrifuge total annual flow source: {facts.get('centrifuge_gpy_total_source') or 'not identified'}")
    out.append("- Distillation source lines:")
    out.append(bullet_lines(facts.get("distillation_lines", [])))
    out.append("- Evaporator source lines:")
    out.append(bullet_lines(facts.get("evaporator_lines", [])))
    out.append("- Centrifuge source lines:")
    out.append(bullet_lines(facts.get("centrifuge_lines", [])))
    out.append("")
    out.append("Emissions / Environmental Constraints:")
    out.append(bullet_lines(facts.get("emission_limit_lines", []) or facts.get("permit_constraint_lines", [])))
    out.append("")
    out.append("Derived Metrics:")
    out.append(f"- Ethanol yield: {fmt_num(metrics.get('ethanol_yield_gal_per_bu'), 3)} gal/bu | Formula: ethanol capacity gal/year / permitted corn bu/year | Confidence: {confidence_for(metrics.get('ethanol_yield_gal_per_bu'))} | Note: requires both capacity and corn throughput.")
    out.append(f"- DDGS yield: {fmt_num(metrics.get('ddgs_yield_ton_per_bu'), 5)} tons/bu | Formula: DDGS tons/year / permitted corn bu/year | Confidence: {confidence_for(metrics.get('ddgs_yield_ton_per_bu'))}.")
    out.append(f"- Corn oil yield: not available | Formula: corn oil production / corn throughput | Confidence: missing input | Note: permit text generally identifies system presence but not annual corn oil production.")
    out.append(f"- Grain throughput: {fmt_num(metrics.get('grain_throughput_bu_per_day'), 0)} bu/day | Formula: permitted corn bu/year / 365 | Confidence: {confidence_for(metrics.get('grain_throughput_bu_per_day'))}.")
    out.append(f"- Grain storage days: {fmt_num(metrics.get('grain_storage_days'), 2)} days | Formula: grain storage bu / grain throughput bu/day | Confidence: {confidence_for(metrics.get('grain_storage_days'))}.")
    out.append(f"- Fermenter volume: {fmt_num(metrics.get('fermenter_volume_gal'), 0)} gal | Formula: reported total or fermenter count x vessel volume | Confidence: {confidence_for(metrics.get('fermenter_volume_gal'))}.")
    out.append(f"- Beer well volume: {fmt_num(metrics.get('beer_well_volume_gal'), 0)} gal | Formula: reported beer well volume | Confidence: {confidence_for(metrics.get('beer_well_volume_gal'))}.")
    out.append(f"- Estimated fermentation time: {fmt_num(metrics.get('estimated_fermentation_time_hr'), 2)} hr | Formula: fermenter volume / (beer feed GPM x 60) | Confidence: {confidence_for(metrics.get('estimated_fermentation_time_hr'))}.")
    out.append(f"- DDGS tons/day: {fmt_num(metrics.get('ddgs_tons_per_day'), 2)} tons/day | Formula: DDGS tons/year / 365 | Confidence: {confidence_for(metrics.get('ddgs_tons_per_day'))}.")
    out.append(f"- DDGS lb/bu: {fmt_num(metrics.get('ddgs_lb_per_bu'), 2)} lb/bu | Formula: DDGS tons/year x 2,000 / permitted corn bu/year | Confidence: {confidence_for(metrics.get('ddgs_lb_per_bu'))}.")
    out.append("")
    out.append("Confidence Notes / Assumptions:")
    out.append("- Summary is generated from PDF text extraction and should be reviewed against the permit when numeric limits are material.")
    out.append("- Batch extraction reads the full PDF and scans all extracted permit text for operational limits, throughput rates, production constraints, loadout limits, storage limits, feed rates, and equipment design capacities.")
    out.append("- Dropdown EPM, capacity, and facility metadata are used for identity matching and fallback capacity when the permit text does not expose a clear MGY limit.")
    out.append("- Equipment counts are text-derived mentions from the equipment list, not engineering-verified counts.")
    out.append("- Missing derived metrics mean the required source inputs were not reliably found in the extracted permit text.")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def safe_filename(facility: Facility | None, identity: dict) -> str:
    epm = facility.epm if facility else "UNMATCHED"
    name = facility.name if facility else identity.get("facility_name_from_permit") or identity.get("pdf_file")
    name = re.sub(r"[^A-Za-z0-9]+", "_", clean(name)).strip("_")
    return f"{epm}_{name}.txt"


def match_summary_file_to_facility(path: Path, facilities: list[Facility]) -> Facility | None:
    if path.name.startswith("_"):
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    epm_match = re.search(r"^EPM Number:\s*(\d+)", text, flags=re.I | re.M)
    plant_match = re.search(r"^Plant Name:\s*(.+)", text, flags=re.I | re.M)
    permit_name = norm(plant_match.group(1)) if plant_match else norm(path.stem)

    if epm_match:
        epm = epm_match.group(1)
        epm_fac = next((fac for fac in facilities if fac.epm == epm), None)
        if epm_fac:
            epm_name_score = max(
                SequenceMatcher(None, permit_name, norm(epm_fac.name)).ratio(),
                SequenceMatcher(None, permit_name, norm(epm_fac.ownership)).ratio(),
            )
            # Trust generated EPM headers unless the name strongly contradicts the EPM.
            if epm_name_score >= 0.45:
                lines = text.splitlines()
                deduped = []
                seen_epm = False
                for line in lines:
                    if re.match(r"^EPM Number:", line, flags=re.I):
                        if seen_epm:
                            continue
                        deduped.append(f"EPM Number: {epm_fac.epm}")
                        seen_epm = True
                    else:
                        deduped.append(line)
                new_text = "\n".join(deduped) + ("\n" if text.endswith("\n") else "")
                if new_text != text:
                    path.write_text(new_text, encoding="utf-8")
                return epm_fac

    best = None
    best_score = 0.0
    for fac in facilities:
        score = max(
            SequenceMatcher(None, permit_name, norm(fac.name)).ratio(),
            SequenceMatcher(None, permit_name, norm(fac.ownership)).ratio(),
        )
        if score > best_score:
            best = fac
            best_score = score

    if best and best_score >= 0.72:
        # Ensure older hand-written summaries also carry the corrected EPM as the first line.
        lines = text.splitlines()
        if lines and re.match(r"^EPM Number:", lines[0], flags=re.I):
            deduped = [f"EPM Number: {best.epm}"]
            deduped.extend(line for line in lines[1:] if not re.match(r"^EPM Number:", line, flags=re.I))
            new_text = "\n".join(deduped) + ("\n" if text.endswith("\n") else "")
        else:
            body = "\n".join(line for line in lines if not re.match(r"^EPM Number:", line, flags=re.I))
            new_text = f"EPM Number: {best.epm}\n" + body + ("\n" if text.endswith("\n") else "")
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
        return best

    return None


def main() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    facilities = load_target_facilities()
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    coverage = []
    matched_epms = set()

    for pdf in pdfs:
        text = extract_pdf_text(pdf)
        identity = parse_identity(text, pdf)
        facility, score, note = match_facility(identity, facilities, text)
        if facility:
            matched_epms.add(facility.epm)
        facts = parse_facts(text, identity, facility)
        metrics = derived_metrics(facts)
        out_path = SUMMARY_DIR / safe_filename(facility, identity)
        write_summary(out_path, identity, facility, score, note, facts, metrics)
        coverage.append(
            {
                "pdf": pdf.name,
                "summary": out_path.name,
                "epm": facility.epm if facility else "",
                "facility": facility.name if facility else identity.get("facility_name_from_permit"),
                "city": facility.city if facility else identity.get("city_from_permit"),
                "match_score": f"{score:.3f}",
                "match_note": note,
            }
        )

    summary_epms = set(matched_epms)
    for summary_path in SUMMARY_DIR.glob("*.txt"):
        matched_summary_fac = match_summary_file_to_facility(summary_path, facilities)
        if matched_summary_fac:
            summary_epms.add(matched_summary_fac.epm)

    excluded_norms = {norm(name) for name in EXCLUDE_MISSING_NAMES}
    missing = [
        fac for fac in facilities
        if fac.epm not in summary_epms and norm(fac.name) not in excluded_norms and norm(fac.ownership) not in excluded_norms
    ]

    with COVERAGE_PATH.open("w", encoding="utf-8") as f:
        f.write("pdf\tsummary\tepm\tfacility\tcity\tmatch_score\tmatch_note\n")
        for row in coverage:
            f.write("\t".join(clean(row[k]) for k in ["pdf", "summary", "epm", "facility", "city", "match_score", "match_note"]) + "\n")

    with MISSING_PATH.open("w", encoding="utf-8") as f:
        f.write("Iowa ethanol facilities still missing an air permit PDF/summary\n")
        f.write("Excludes New Energy Blue because it is not running.\n\n")
        for fac in missing:
            f.write(f"EPM {fac.epm}: {fac.name} - {fac.city}, {fac.state} ({fmt_num(fac.capacity_mgy, 1)} MGY)\n")

    print(f"Processed PDFs: {len(pdfs)}")
    print(f"Matched summaries: {len([r for r in coverage if r['epm']])}")
    print(f"Summary folder: {SUMMARY_DIR}")
    print(f"Coverage file: {COVERAGE_PATH}")
    print(f"Missing file: {MISSING_PATH}")
    print("\nMatched PDF -> EPM")
    for row in coverage:
        print(f"{row['pdf']} -> EPM {row['epm'] or 'UNMATCHED'} {row['facility']} ({row['city']}) score={row['match_score']}")
    print("\nIowa facilities/EPMs still needing air permit PDF or summary:")
    for fac in missing:
        print(f"  EPM {fac.epm}: {fac.name} - {fac.city}, {fac.state}")


if __name__ == "__main__":
    main()
