from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
import json
import math
import re
import shutil


SUMMARY_DIR = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary")
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
GAP_REPORT_PATH = SUMMARY_DIR / "_operating_permit_gap_report.json"


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def norm_id(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        n = float(text.replace(",", ""))
        if n.is_integer():
            return str(int(n))
    except ValueError:
        pass
    return re.sub(r"\.0$", "", text)


def num(value: object) -> float | None:
    text = clean(value).replace(",", "")
    if not text or text.lower() in {"not available", "not matched", "none", "null"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def value_after(label: str, text: str) -> str:
    m = re.search(rf"^-+\s*{re.escape(label)}:\s*(.+)$", text, flags=re.I | re.M)
    if not m:
        m = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, flags=re.I | re.M)
    return clean(m.group(1)) if m else ""


def value_after_any(labels: list[str], text: str) -> str:
    for label in labels:
        value = value_after(label, text)
        if value:
            return value
    return ""


def first_line_matching(text: str, patterns: list[str]) -> str:
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        for pattern in patterns:
            if re.search(pattern, line, flags=re.I):
                return line
    return ""


def scaled_num(value: object, default_multiplier: float = 1.0) -> float | None:
    text = clean(value).replace(",", "")
    if not text or text.lower() in {"not available", "not matched", "none", "null"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    if re.search(r"\b(million|mm)\b", text, flags=re.I):
        return number * 1_000_000
    if re.search(r"\b(billion|bn)\b", text, flags=re.I):
        return number * 1_000_000_000
    return number * default_multiplier


def mgy_num(value: object) -> float | None:
    text = clean(value)
    if not text:
        return None
    value_num = scaled_num(text)
    if value_num is None:
        return None
    if re.search(r"\b(gallons?/year|gal/year|gpy)\b", text, flags=re.I) and not re.search(r"\bMGY\b", text, flags=re.I):
        return value_num / 1_000_000
    return value_num


def section(text: str, heading: str) -> str:
    pattern = rf"^{re.escape(heading)}:\s*$"
    m = re.search(pattern, text, flags=re.I | re.M)
    if not m:
        return ""
    start = m.end()
    next_heading = re.search(r"^[A-Z][A-Za-z0-9 /().-]+:\s*$", text[start:], flags=re.M)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def section_any(text: str, headings: list[str]) -> str:
    for heading in headings:
        found = section(text, heading)
        if found:
            return found
    return ""


def bullet_lines(text: str) -> list[str]:
    return [clean(m.group(1)) for m in re.finditer(r"^-\s*(.+)$", text, flags=re.M)]


def first_number_from_patterns(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return num(m.group(1))
    return None


def mmbtu_values(lines: list[str] | str, include_terms: list[str] | None = None) -> list[float]:
    if isinstance(lines, str):
        source_lines = lines.splitlines()
    else:
        source_lines = lines
    values: list[float] = []
    for line in source_lines:
        low = line.lower()
        if include_terms and not any(term in low for term in include_terms):
            continue
        for match in re.finditer(r"([0-9][0-9,.]*(?:\.\d+)?)\s*MMBtu\s*/?\s*hr", line, flags=re.I):
            try:
                values.append(float(match.group(1).replace(",", "")))
            except ValueError:
                pass
    return values


def heat_metric_from_lines(lines: list[str] | str, include_terms: list[str] | None = None) -> dict:
    values = mmbtu_values(lines, include_terms)
    return {
        "value": max(values) if values else None,
        "units": "MMBtu/hr",
        "method": "largest matching MMBtu/hr mention in extracted permit lines",
        "confidence": "low" if values else "missing_inputs",
        "all_values": values,
    }


def find_lines(text: str, terms: list[str], limit: int = 20) -> list[str]:
    out: list[str] = []
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


def has_text(value: object, pattern: str) -> bool:
    return bool(re.search(pattern, clean(value), flags=re.I))


def trueish(value: object) -> bool:
    text = clean(value)
    if not text:
        return False
    return text.lower() not in {"false", "no", "none", "null", "0", "unknown"}


def fiber_to_ethanol_label(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    if re.search(r"bpx|edeniq|soliton|proprietary", text, flags=re.I):
        return text
    return ""


def lcfs_fiber_to_ethanol_label(row: dict) -> tuple[str, str]:
    lcfs = row.get("lcfs_detail") if isinstance(row.get("lcfs_detail"), dict) else {}
    for source_name, key in (
        ("lcfs_detail.ca_detail.fiber_technology", "ca_detail"),
        ("lcfs_detail.or_detail.fiber_technology", "or_detail"),
    ):
        detail = lcfs.get(key) if isinstance(lcfs.get(key), list) else []
        for item in detail:
            if not isinstance(item, dict):
                continue
            label = fiber_to_ethanol_label(item.get("fiber_technology"))
            if label:
                return label, source_name

    wa_detail = row.get("wa_lcfs_ci_detail") if isinstance(row.get("wa_lcfs_ci_detail"), list) else []
    for item in wa_detail:
        if not isinstance(item, dict):
            continue
        desc = clean(item.get("Pathway Description"))
        for label in ("BPX", "Edeniq", "Soliton", "Proprietary"):
            if re.search(rf"\b{re.escape(label)}\b", desc, flags=re.I):
                return label, "wa_lcfs_ci_detail.Pathway Description"
    return "", ""


def metric(value: float | None, units: str, formula: str, confidence: str, notes: str) -> dict:
    return {
        "value": None if value is None or not math.isfinite(value) else value,
        "units": units,
        "formula": formula,
        "confidence": confidence,
        "notes": notes,
    }


def parse_derived_line(text: str, label: str) -> float | None:
    m = re.search(rf"^-\s*{re.escape(label)}:\s*([^|]+)", text, flags=re.I | re.M)
    return num(m.group(1)) if m else None


def first_scaled_from_patterns(text: str, patterns: list[str], multiplier: float = 1.0) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I | re.S)
        if m:
            return scaled_num(m.group(1), default_multiplier=multiplier)
    return None


def first_line_and_scaled(text: str, patterns: list[str], multiplier: float = 1.0) -> tuple[float | None, str]:
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        for pattern in patterns:
            m = re.search(pattern, line, flags=re.I)
            if m:
                return scaled_num(m.group(1), default_multiplier=multiplier), line
    return None, ""


def tons_to_bushels(tons: float | None) -> float | None:
    return tons * 2000 / 56 if tons is not None else None


def section_lines_by_terms(text: str, terms: list[str], limit: int = 24) -> list[str]:
    return find_lines(text, terms, limit)


def parse_summary(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    epm = norm_id(value_after("EPM Number", text))
    if not epm or epm.upper() == "UNMATCHED":
        return None

    source_file = value_after("Source Permit File", text) or value_after("Source Permit", text) or path.name
    permit_number = value_after("Permit Number", text)
    match_confidence = value_after("Match Confidence", text)

    fermentation = section_any(text, ["Fermentation Equipment", "Fermentation"])
    grain = section_any(text, ["Grain Handling / Storage", "Grain Handling"])
    grinding = section(text, "Grinding")
    dryers = section_any(text, ["Dryers", "DDGS System"])
    boilers = section_any(text, ["Boilers / Process Heaters", "Energy System"])
    oxidizers = section_any(text, ["Thermal Oxidizers / RTO", "Environmental Controls"])
    transportation = section(text, "Transportation")
    tanks = section(text, "Tanks")
    ddgs_oil = section_any(text, ["DDGS / Corn Oil Systems", "Corn Oil Recovery"])
    ddgs_system = section(text, "DDGS System")
    constraints = section_any(text, ["Emissions / Permit Constraints", "Permit Constraints"])
    derived_text = section(text, "Derived Metrics")
    notes_text = section(text, "Confidence Notes / Assumptions")

    ethanol_capacity_source = value_after_any(
        ["Ethanol capacity used", "Permitted Ethanol Capacity", "Permitted Ethanol Production/Loadout", "Ethanol Production Limit"],
        text,
    )
    corn_throughput_source = value_after_any(
        ["Permitted corn/grain throughput", "Permitted Grain Throughput", "Grain Throughput Limit"],
        text,
    )
    grain_storage_source = value_after_any(
        ["Grain storage parsed", "Total Storage Including Ground Pile", "Total Permanent Storage"],
        text,
    )
    ethanol_capacity_mgy = mgy_num(ethanol_capacity_source)
    corn_throughput_bpy = scaled_num(corn_throughput_source)
    grain_storage_bu = scaled_num(grain_storage_source)
    ddgs_tpy = num(value_after("DDGS limit parsed", text))
    mo_grain_tpy = num(value_after("Grain receiving limit", text))
    mo_grain_line = value_after("Grain receiving source", text) or ""
    if mo_grain_tpy is None:
        mo_grain_tpy, mo_grain_line = first_line_and_scaled(text, [r"Truck and Rail Grain\s+([0-9,.]+)\s*tons of grain"], 1.0)
    if corn_throughput_bpy is None and mo_grain_tpy is not None:
        corn_throughput_bpy = tons_to_bushels(mo_grain_tpy)
        corn_throughput_source = mo_grain_line
    wetcake_tpy = num(value_after("Wetcake limit", text))
    wetcake_limit_line = value_after("Wetcake limit source", text) or ""
    if wetcake_tpy is None:
        wetcake_tpy, wetcake_limit_line = first_line_and_scaled(text, [r"Produce less than\s+([0-9,.]+)\s*tons of wet\s*cake"], 1.0)
    syrup_tpy = num(value_after("Syrup limit", text))
    syrup_limit_line = value_after("Syrup limit source", text) or ""
    if syrup_tpy is None:
        syrup_tpy, syrup_limit_line = first_line_and_scaled(text, [r"Produce and loadout less than\s+([0-9,.]+)\s*tons of syrup"], 1.0)

    fermenter_count = first_number_from_patterns(
        fermentation + "\n" + text,
        [
            r"Fermenter count parsed:\s*([0-9,.]+)",
            r"(\d+)\s+Fermenters",
            r"(\d+)\s+Fermentation Process Vessels",
        ],
    )
    fermenter_each_gal = first_number_from_patterns(text, [r"([0-9,.]+)\s*gallons each"])
    total_fermenter_volume = parse_derived_line(derived_text, "Fermenter volume")
    if total_fermenter_volume is None:
        total_fermenter_volume = first_number_from_patterns(text, [r"Total fermentation volume:\s*([0-9,.]+)\s*million gallons"])
        if total_fermenter_volume is not None:
            total_fermenter_volume *= 1_000_000
    if total_fermenter_volume is None and fermenter_count and fermenter_each_gal:
        total_fermenter_volume = fermenter_count * fermenter_each_gal

    beer_well_volume = parse_derived_line(derived_text, "Beer well volume")
    if beer_well_volume is None:
        beer_well_volume = first_number_from_patterns(text, [r"Beer Well:\s*([0-9,.]+)\s*gallons"])

    dryer_count = num(value_after("Dryer mentions parsed", text))
    if dryer_count is None:
        dryer_count = first_number_from_patterns(text, [r"([0-9,.]+)\s+DDGS\s+Dryers?"])
    boiler_count = num(value_after("Boiler/heater mentions parsed", text))
    if boiler_count is None:
        boiler_numbers = {m.group(1) for m in re.finditer(r"\bBoiler\s*#?\s*([0-9]+)\b", text, flags=re.I)}
        boiler_count = float(len(boiler_numbers)) if boiler_numbers else None
    rto_count = num(value_after("RTO/thermal oxidizer mentions parsed", text))
    if rto_count is None:
        rto_count = first_number_from_patterns(text, [r"([0-9,.]+)\s+Regenerative\s+Thermal\s+Oxidizers?", r"([0-9,.]+)\s+RTOs?"])
    tank_count = num(value_after("Storage tank mentions parsed", text))
    grain_elevator_tph = num(value_after("Corn elevator capacity", text))
    if grain_elevator_tph is None:
        grain_elevator_tph = first_number_from_patterns(text, [r"Corn Elevator\s+[0-9]{4}\s+([0-9,.]+)\s*tons/hr"])
    grain_unloading_conveyor_tph = num(value_after("Corn bin unloading conveyor capacity", text))
    if grain_unloading_conveyor_tph is None:
        grain_unloading_conveyor_tph = first_number_from_patterns(text, [r"Corn Bin Unloading Conveyor.*?\s([0-9,.]+)\s*tons/hr"])
    hammermill_count = first_number_from_patterns(grinding, [r"([0-9,.]+)\s+Hammermills?"])
    hammermill_capacity_each_bu_hr = first_number_from_patterns(grinding, [r"([0-9,.]+)\s+bushels/hour\s+each"])
    total_grinding_capacity_bu_hr = first_number_from_patterns(grinding, [r"Total Grinding Capacity:\s*([0-9,.]+)\s*bu/hr"])
    theoretical_grind_capacity_bpy = scaled_num(value_after("Theoretical Grind Capacity @ 350 operating days", grinding))

    dryer_lines = bullet_lines(dryers)
    boiler_lines = bullet_lines(boilers)
    oxidizer_lines = bullet_lines(oxidizers)
    ddgs_lines = bullet_lines(ddgs_oil)
    all_text = text.lower()

    special_terms = {
        "high_protein_system": bool(
            re.search(
                r"high[- ]?pro|high protein|protein dryer|protein storage|protein loadout|protein receiving|msc dryer|fluid quip|fqpt",
                text,
                flags=re.I,
            )
        ),
        "corn_fiber_ethanol": bool(re.search(r"corn fiber|cellulosic|fiber ethanol|edeniq|d3\b", text, flags=re.I)),
        "corn_oil_recovery": "corn oil" in all_text or "tricanter" in all_text,
        "chp": bool(re.search(r"\bCHP\b|cogeneration|combined heat and power", text, flags=re.I)),
        "waste_heat_recovery": "waste heat" in all_text or "heat recovery boiler" in all_text,
        "membrane_dehydration": bool(re.search(r"white fox|membrane dehydration|membrane system", text, flags=re.I)),
        "rto_or_thermal_oxidizer": bool(rto_count) or bool(re.search(r"thermal oxidizer|\bRTO\b|regenerative thermal", text, flags=re.I)),
        "biogas_or_rng": bool(re.search(r"biogas|renewable natural gas|\bRNG\b|landfill gas|digester gas", text, flags=re.I)),
        "carbon_capture": bool(re.search(r"carbon capture|co2 capture|carbon dioxide capture|sequestration|ccs\b", text, flags=re.I)),
        "feedstock_flex": bool(re.search(r"sorghum|milo|feedstock flex|alternate feedstock|mixed feedstock", text, flags=re.I)),
        "renewable_electricity": bool(re.search(r"wind turbine|solar|renewable electricity|ppa|power purchase agreement", text, flags=re.I)),
        "fractionation": bool(re.search(r"fractionation|front[- ]end fractionation|germ separation", text, flags=re.I)),
        "icm": bool(re.search(r"\bICM\b", text)),
        "fluid_quip": "fluid quip" in all_text,
        "edeniq": "edeniq" in all_text,
        "white_fox": "white fox" in all_text,
        "bpx": "bpx" in all_text,
    }
    # Keep the old key temporarily so existing readers do not break while the
    # calculator migrates to high_protein_system.
    special_terms["high_protein"] = special_terms["high_protein_system"]

    technology_flags = {
        "white_fox_membrane": bool(re.search(r"white fox|membrane dehydration|membrane system", text, flags=re.I)),
        "molecular_sieve_only": bool(re.search(r"molecular sieve", text, flags=re.I))
        and not bool(re.search(r"white fox|membrane dehydration|membrane system", text, flags=re.I)),
        "chp": bool(re.search(r"\bCHP\b|cogeneration|combined heat and power", text, flags=re.I)),
        "waste_heat_recovery": "waste heat" in all_text or "heat recovery boiler" in all_text,
        "fiber_to_ethanol": bool(re.search(r"cellulosic ethanol|fiber ethanol|corn fiber ethanol|d3\b", text, flags=re.I)),
        "fiber_to_ethanol_technology": None,
        "fiber_to_ethanol_source": None,
        "d3_capable": bool(re.search(r"cellulosic ethanol|fiber ethanol|corn fiber ethanol|d3\b", text, flags=re.I)),
        "generic_fiber_separation": bool(
            re.search(r"\bFST\b|fiber separation technology|front[- ]end fiber separation|mechanical fiber separation", text, flags=re.I)
        ),
        "high_protein": special_terms["high_protein_system"],
        "corn_oil_extraction": "corn oil" in all_text or "tricanter" in all_text,
        "edeniq": "edeniq" in all_text,
        "fluid_quip": "fluid quip" in all_text or "fqpt" in all_text,
        "icm_selective_milling": bool(re.search(r"selective milling|icm\s+selective", text, flags=re.I)),
        "icm_fst": bool(re.search(r"\bFST\b|fiber separation technology", text, flags=re.I)),
        "co2_capture": bool(re.search(r"carbon capture|co2 capture|carbon dioxide capture|sequestration|ccs\b", text, flags=re.I)),
        "rng_biogas": bool(re.search(r"biogas|renewable natural gas|\bRNG\b|landfill gas|digester gas", text, flags=re.I)),
    }

    dryer_type_hits = []
    dryer_source_text = "\n".join(dryer_lines)
    if re.search(r"ring dryer", dryer_source_text, flags=re.I):
        dryer_type_hits.append("Ring Dryer")
    if re.search(r"rotary dryer", dryer_source_text, flags=re.I):
        dryer_type_hits.append("Rotary Dryer")
    if re.search(r"steam tube dryer", dryer_source_text, flags=re.I):
        dryer_type_hits.append("Steam Tube Dryer")
    if re.search(r"msc dryer", dryer_source_text, flags=re.I):
        dryer_type_hits.append("MSC Dryer")
    if re.search(r"indirect[- ]fired.*dryer|dryer.*indirect[- ]fired", dryer_source_text, flags=re.I):
        dryer_type_hits.append("Indirect-Fired Dryer")
    if re.search(r"\bddgs dryer\b|dryer #[0-9a-z]+|dryer [a-z]\b", dryer_source_text, flags=re.I):
        dryer_type_hits.append("DDGS Dryer")
    dryer_type = " + ".join(dict.fromkeys(dryer_type_hits)) if dryer_type_hits else None

    dryer_heat = heat_metric_from_lines(dryer_lines, ["dryer"])
    dryer_heat_summary = num(value_after("Dryer rated capacity", text))
    if dryer_heat_summary is not None:
        dryer_heat = {
            "value": dryer_heat_summary,
            "units": "MMBtu/hr",
            "method": "parsed from generated permit summary",
            "confidence": "medium",
            "source_line": value_after("Dryer rated capacity source", text),
        }
    dryer_heat_values = mmbtu_values(text, ["dryer"])
    if dryer_heat.get("value") is None and dryer_heat_values:
        dryer_heat = {
            "value": max(dryer_heat_values),
            "units": "MMBtu/hr",
            "method": "largest dryer MMBtu/hr mention in extracted permit text",
            "confidence": "low",
            "all_values": dryer_heat_values,
        }
    boiler_heat = heat_metric_from_lines(boiler_lines, ["boiler", "heater"])
    rto_heat = heat_metric_from_lines(oxidizer_lines, ["thermal oxidizer", "rto", "regenerative thermal"])
    if rto_heat.get("value") is None:
        rto_heat = heat_metric_from_lines(oxidizer_lines)
    waste_heat_boiler_heat = heat_metric_from_lines(boiler_lines + oxidizer_lines, ["waste heat", "heat recovery boiler"])

    ethanol_yield = parse_derived_line(derived_text, "Ethanol yield")
    grain_throughput_bpd = parse_derived_line(derived_text, "Grain throughput")
    grain_storage_days = parse_derived_line(derived_text, "Grain storage days")
    ddgs_lb_bu = parse_derived_line(derived_text, "DDGS lb/bu")
    ddgs_tpd = parse_derived_line(derived_text, "DDGS tons/day")
    fermentation_time = parse_derived_line(derived_text, "Estimated fermentation time")
    beer_well_hold = parse_derived_line(derived_text, "Beer well hold time")
    centrifuge_count = num(value_after("Centrifuge count", text))
    if centrifuge_count is None:
        centrifuge_count = first_number_from_patterns(text, [r"Emissions from\s*\(([0-9,.]+)\)\s*(?:whole stillage\s*)?centrifuges", r"Centrifuges\s*#1\s*through\s*#([0-9,.]+)"])
    centrifuge_gpm_each = num(value_after("Centrifuge flow each", text))
    if centrifuge_gpm_each is None:
        centrifuge_gpm_each = first_number_from_patterns(text, [r"([0-9,.]+)\s*gpm\s*\(each centrifuge\)", r"([0-9,.]+)\s*gallons liquid per minute per individual centrifuges"])
    centrifuge_gpm_total = num(value_after("Centrifuge total flow", text))
    if centrifuge_gpm_total is None:
        centrifuge_gpm_total = first_number_from_patterns(text, [r"([0-9,.]+)\s*gallons liquid per minute through all centrifuges"])
    centrifuge_gph_total = num(value_after("Centrifuge total hourly flow", text))
    if centrifuge_gph_total is None:
        centrifuge_gph_total = first_number_from_patterns(text, [r"([0-9,.]+)\s*gallons liquid per hour through all centrifuges"])
    centrifuge_gpy_total = num(value_after("Centrifuge total annual flow", text))
    if centrifuge_gpy_total is None:
        centrifuge_gpy_total = first_number_from_patterns(text, [r"([0-9,.]+)\s*gallons liquid per year through all centrifuges"])
    wetcake_tph = num(value_after("Wetcake production rate", text))
    if wetcake_tph is None:
        wetcake_tph = first_number_from_patterns(text, [r"Capacity=\s*([0-9,.]+)\s*tons/hr maximum wetcake production rate", r"Wet Cake Production\s+([0-9,.]+)\s*ton"])
    evaporator_gph = num(value_after("Evaporator capacity", text))
    if evaporator_gph is None:
        evaporator_gph = first_number_from_patterns(text, [r"Evaporator.*?\s([0-9,.]+)\s*gal/hr"])
    concentrate_tank_gal = num(value_after("Concentrate tank", text))
    if concentrate_tank_gal is None:
        concentrate_tank_gal = first_number_from_patterns(text, [r"Concentrate Tank.*?\s([0-9,.]+)\s*gallons?"])
    thin_stillage_recycle_pct = num(value_after("Thin stillage recycle", text))
    if thin_stillage_recycle_pct is None:
        thin_stillage_recycle_pct = first_number_from_patterns(text, [r"Approximately\s+([0-9,.]+)%\s+of the thin stillage"])
    evaporation_stages = num(value_after("Evaporation stages", text))
    if evaporation_stages is None:
        evaporation_stages = first_number_from_patterns(text, [r"There are\s+([0-9,.]+)\s+stages of evaporation"])
    beer_feed_gpm = num(value_after("Beer/distillation feed", text))
    if beer_feed_gpm is None:
        beer_feed_gpm = first_number_from_patterns(text, [r"bottlenecked maximum hourly design rate is\s+([0-9,.]+)\s*gal/min", r"production rate of\s+([0-9,.]+)\s*gal/min"])

    if ethanol_yield is None and corn_throughput_bpy and ethanol_capacity_mgy:
        ethanol_yield = ethanol_capacity_mgy * 1_000_000 / corn_throughput_bpy
    corn_grind_per_gal = (corn_throughput_bpy / (ethanol_capacity_mgy * 1_000_000)) if corn_throughput_bpy and ethanol_capacity_mgy else None
    daily_grain_source = ""
    daily_grain_bu = grain_throughput_bpd
    if daily_grain_bu is None and corn_throughput_bpy:
        daily_grain_bu = corn_throughput_bpy / 365
        daily_grain_source = "permitted_corn_grind"
    elif daily_grain_bu is not None:
        daily_grain_source = "summary_grain_throughput"
    elif ethanol_capacity_mgy:
        daily_grain_bu = (ethanol_capacity_mgy * 1_000_000 / 3.0) / 365
        daily_grain_source = "ethanol_capacity_divided_by_3_gal_per_bu"

    calculated_grain_storage_days = None
    grain_storage_confidence = "missing_inputs"
    grain_storage_notes = "Requires total corn/grain storage bushels and daily grain use."
    if grain_storage_bu and daily_grain_bu:
        calculated_grain_storage_days = grain_storage_bu / daily_grain_bu
        grain_storage_confidence = "medium" if daily_grain_source in {"permitted_corn_grind", "summary_grain_throughput"} else "low"
        grain_storage_notes = (
            f"Total corn storage = {grain_storage_bu:,.0f} bu; daily grain source = {daily_grain_source}. "
            "Fallback assumes ethanol capacity / 3.0 gal per bushel when permit corn grind is unavailable."
        )
    elif grain_storage_days is not None:
        calculated_grain_storage_days = grain_storage_days
        grain_storage_confidence = "medium"
        grain_storage_notes = "Read from generated permit summary."

    equipment = {
        "grain_handling": {
            "source_lines": bullet_lines(grain),
            "total_storage_bu": grain_storage_bu,
            "grain_receiving_limit_tons_per_year": mo_grain_tpy,
            "grain_receiving_limit_bushels_per_year": tons_to_bushels(mo_grain_tpy),
            "corn_elevator_tons_per_hour": grain_elevator_tph,
            "corn_bin_unloading_conveyor_tons_per_hour": grain_unloading_conveyor_tph,
        },
        "grinding": {
            "hammermill_count": hammermill_count,
            "hammermill_capacity_each_bu_hr": hammermill_capacity_each_bu_hr,
            "total_grinding_capacity_bu_hr": total_grinding_capacity_bu_hr,
            "theoretical_grind_capacity_bu_per_year": theoretical_grind_capacity_bpy,
            "source_lines": bullet_lines(grinding),
        },
        "fermenters": {
            "count": fermenter_count,
            "size_gal_each": fermenter_each_gal,
            "total_volume_gal": total_fermenter_volume,
            "beer_well_volume_gal": beer_well_volume,
            "source_lines": bullet_lines(fermentation),
        },
        "distillation": {
            "beer_feed_gpm": beer_feed_gpm,
            "source_lines": section_lines_by_terms(text, ["distillation column", "beer stripper", "rectifier", "side stripper", "molecular sieve", "demethyl", "industrial distillation"], 24),
        },
        "evaporators": {
            "evaporator_gal_per_hour": evaporator_gph,
            "concentrate_tank_gal": concentrate_tank_gal,
            "thin_stillage_recycle_percent": thin_stillage_recycle_pct,
            "evaporation_stages": evaporation_stages,
            "source_lines": section_lines_by_terms(text, ["evaporator", "thin stillage", "concentrate tank", "syrup storage", "condensed distillers", "cds"], 24),
        },
        "decanters_centrifuges": {
            "count": centrifuge_count or (len(re.findall(r"centrifuge|tricanter|decanter", text, flags=re.I)) or None),
            "gpm_each": centrifuge_gpm_each,
            "gpm_total": centrifuge_gpm_total,
            "gph_total": centrifuge_gph_total,
            "gpy_total": centrifuge_gpy_total,
            "source_lines": find_lines(text, ["centrifuge", "tricanter", "decanter"], 12),
        },
        "dryers": {
            "count": dryer_count,
            "type": dryer_type,
            "capacity": None,
            "heat_input": dryer_heat.get("value"),
            "heat_input_mmbtu_hr": dryer_heat,
            "source_lines": dryer_lines,
        },
        "boilers_process_heaters": {
            "count": boiler_count,
            "fuel": "Natural Gas" if "natural gas" in all_text else None,
            "heat_input": boiler_heat.get("value"),
            "heat_input_mmbtu_hr": boiler_heat,
            "source_lines": boiler_lines,
        },
        "thermal_oxidizers_rtos": {
            "count": rto_count,
            "heat_input_mmbtu_hr": rto_heat,
            "source_lines": oxidizer_lines,
        },
        "waste_heat_boilers": {
            "heat_input_mmbtu_hr": waste_heat_boiler_heat,
            "source_lines": find_lines(text, ["waste heat", "heat recovery boiler"], 12),
        },
        "scrubbers": {"count": len(re.findall(r"scrubber", text, flags=re.I)) or None, "source_lines": find_lines(text, ["scrubber"], 12)},
        "baghouses": {"count": len(re.findall(r"baghouse", text, flags=re.I)) or None, "source_lines": find_lines(text, ["baghouse"], 12)},
        "environmental_controls": {"source_lines": bullet_lines(oxidizers)},
        "ddgs_system": {
            "wetcake_tons_per_hour": wetcake_tph,
            "wetcake_limit_tons_per_year": wetcake_tpy,
            "syrup_limit_tons_per_year": syrup_tpy,
            "source_lines": bullet_lines(ddgs_system or dryers),
        },
        "corn_oil_systems": {
            "present": "corn oil" in all_text or "corn oil centrifuge" in all_text,
            "corn_oil_centrifuge_stack": bool(re.search(r"corn oil centrifuge", text, flags=re.I)),
            "source_lines": find_lines(text, ["corn oil", "tricanter"], 12),
        },
        "transportation": {"source_lines": bullet_lines(transportation)},
        "tanks": {"count": tank_count, "source_lines": bullet_lines(tanks)},
        "special_equipment": special_terms,
        "technology_flags": technology_flags,
    }

    limits = {
        "corn_grind": {
            "value": corn_throughput_bpy,
            "units": "bu/year",
            "source_line": value_after("Throughput source line", text)
            or first_line_matching(text, [r"Permitted Grain Throughput", r"Grain Throughput Limit"]),
        },
        "ethanol_production": {
            "value": ethanol_capacity_mgy,
            "units": "MGY",
            "source_line": value_after("Ethanol capacity source", text)
            or first_line_matching(text, [r"Permitted Ethanol Capacity", r"Permitted Ethanol Production/Loadout", r"Ethanol Production Limit"]),
        },
        "beer_well": {"value": beer_well_volume, "units": "gal", "source_line": "parsed from summary text"},
        "dryer_ddgs": {"value": ddgs_tpy, "units": "tons/year", "source_line": value_after("DDGS source line", text)},
        "wetcake": {"value": wetcake_tpy, "units": "tons/year", "source_line": wetcake_limit_line},
        "syrup": {"value": syrup_tpy, "units": "tons/year", "source_line": syrup_limit_line},
        "natural_gas_boiler": {
            "value": boiler_heat.get("value"),
            "units": "MMBtu/hr",
            "source_lines": boiler_lines,
        },
        "key_emissions": {"source_lines": bullet_lines(constraints)},
    }

    derivatives = {
        "ethanol_yield": metric(
            ethanol_yield,
            "gal/bu",
            "ethanol_capacity_gal_per_year / permitted_corn_bu_per_year",
            "medium" if ethanol_yield is not None else "missing_inputs",
            "From generated summary where permit capacity and corn throughput were available.",
        ),
        "corn_grind_per_gallon": metric(
            corn_grind_per_gal,
            "bu/gal",
            "permitted_corn_bu_per_year / ethanol_capacity_gal_per_year",
            "medium" if corn_grind_per_gal is not None else "missing_inputs",
            "Inverse of ethanol yield.",
        ),
        "ddgs_lb_per_bu": metric(ddgs_lb_bu, "lb/bu", "DDGS tons/year * 2,000 / permitted_corn_bu_per_year", "medium" if ddgs_lb_bu is not None else "missing_inputs", ""),
        "corn_oil_lb_per_bu": metric(None, "lb/bu", "corn_oil_lb_per_year / permitted_corn_bu_per_year", "missing_inputs", "Annual corn oil production was not reliably extracted from these permit summaries."),
        "thermal_btu_per_gal": metric(None, "BTU/gal", "annual thermal BTU / annual ethanol gallons", "missing_inputs", "Requires annual fuel use or reliable heat input/utilization assumptions."),
        "dryer_btu_per_gal": metric(None, "BTU/gal", "dryer annual BTU / annual ethanol gallons", "missing_inputs", "Requires dryer heat input and operating hours or annual fuel use."),
        "estimated_fermentation_time": metric(fermentation_time, "hours", "total_fermenter_volume_gal / (beer_feed_gpm * 60)", "medium" if fermentation_time is not None else "missing_inputs", ""),
        "beer_feed_gpm": metric(beer_feed_gpm, "gal/min", "permit-reported beer/distillation feed rate", "medium" if beer_feed_gpm is not None else "missing_inputs", "Use cautiously; may be a tested or bottlenecked rate, not always annual average."),
        "centrifuge_total_flow_gpm": metric(centrifuge_gpm_total, "gal/min", "sum of centrifuge liquid flow rates", "medium" if centrifuge_gpm_total is not None else "missing_inputs", "Whole-stillage/thin-stillage process flow, not ethanol product rate."),
        "centrifuge_total_flow_gal_per_year": metric(centrifuge_gpy_total, "gal/year", "permit-reported annual centrifuge liquid flow", "medium" if centrifuge_gpy_total is not None else "missing_inputs", "Whole-stillage/thin-stillage process flow, not ethanol product rate."),
        "beer_well_hold_time": metric(beer_well_hold, "hours", "beer_well_volume_gal / (beer_feed_gpm * 60)", "medium" if beer_well_hold is not None else "missing_inputs", ""),
        "total_corn_storage": metric(
            grain_storage_bu,
            "bu",
            "sum of identified grain/corn storage bins, silos, or piles",
            "medium" if grain_storage_bu is not None else "missing_inputs",
            "Parsed from generated operating permit summary.",
        ),
        "grain_throughput_per_day": metric(
            daily_grain_bu,
            "bu/day",
            "permitted_corn_bu_per_year / 365; fallback = ethanol_capacity_gal_per_year / 3.0 / 365",
            "medium" if daily_grain_source in {"permitted_corn_grind", "summary_grain_throughput"} else ("low" if daily_grain_bu is not None else "missing_inputs"),
            f"daily_grain_source = {daily_grain_source or 'not_available'}",
        ),
        "grain_storage_days": metric(
            calculated_grain_storage_days,
            "days",
            "total_corn_storage_bu / daily_grain_bu; daily_grain_bu = permitted_corn_bu_per_year / 365, fallback = ethanol_capacity_gal_per_year / 3.0 / 365",
            grain_storage_confidence,
            grain_storage_notes,
        ),
        "ddgs_tons_per_day": metric(ddgs_tpd, "tons/day", "DDGS tons/year / 365", "medium" if ddgs_tpd is not None else "missing_inputs", ""),
        "utilization_against_permitted_capacity": metric(None, "percent", "actual_capacity / permitted_capacity", "missing_inputs", "Requires actual production or separate current operating rate."),
    }

    return {
        "source_file": source_file,
        "summary_file": path.name,
        "permit_number": permit_number,
        "permit_type": "Iowa Title V operating permit",
        "confidence": match_confidence or "summary-derived",
        "notes": bullet_lines(notes_text),
        "equipment": equipment,
        "limits": limits,
        "derivatives": derivatives,
    }


def plant_epm(row: dict) -> str:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    for value in (row.get("EPM_NUMBER"), row.get("epm_number"), row.get("epm"), row.get("EPM"), fac.get("epm")):
        epm = norm_id(value)
        if epm:
            return epm
    return ""


def is_iowa(row: dict) -> bool:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    state = clean(row.get("state") or row.get("State") or fac.get("state")).replace("\xa0", " ")
    return state.strip().upper() == "IA"


def plant_label(row: dict) -> str:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    return clean(fac.get("plant_name") or row.get("plant_name") or row.get("Name"))


def enrich_permit_from_tech_flags(row: dict, permit: dict) -> dict:
    tech = row.get("tech_flags") if isinstance(row.get("tech_flags"), dict) else {}
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    equipment = permit.setdefault("equipment", {})
    special = equipment.setdefault("special_equipment", {})
    technology_flags = equipment.setdefault("technology_flags", {})
    dryers = equipment.setdefault("dryers", {})

    dryer_types = clean(tech.get("dryer_types"))
    if dryer_types:
        if not clean(dryers.get("type")):
            dryers["type"] = dryer_types
        dryers["type_from_technology_flags"] = dryer_types
        special["dryer_type_classified"] = True

    special["high_protein_system"] = bool(special.get("high_protein_system")) or trueish(tech.get("high_pro"))
    special["high_protein"] = special["high_protein_system"]
    special["corn_fiber_ethanol"] = bool(special.get("corn_fiber_ethanol")) or trueish(tech.get("fiber_technology"))
    special["corn_oil_recovery"] = bool(special.get("corn_oil_recovery")) or trueish(tech.get("dco_enhancement")) or bool(equipment.get("corn_oil_systems", {}).get("present"))
    special["chp"] = bool(special.get("chp")) or trueish(tech.get("chp"))
    special["waste_heat_recovery"] = bool(special.get("waste_heat_recovery")) or trueish(tech.get("waste_heat"))
    special["membrane_dehydration"] = bool(special.get("membrane_dehydration")) or trueish(tech.get("white_fox"))
    special["white_fox"] = bool(special.get("white_fox")) or trueish(tech.get("white_fox"))
    special["edeniq"] = bool(special.get("edeniq")) or has_text(tech.get("fiber_technology"), r"edeniq")
    special["biogas_or_rng"] = bool(special.get("biogas_or_rng")) or has_text(tech.get("gas_supply"), r"biogas|renewable natural gas|\bRNG\b|landfill gas|digester gas")
    special["renewable_electricity"] = bool(special.get("renewable_electricity")) or has_text(tech.get("electricity_type"), r"wind|solar|renewable|ppa") or trueish(tech.get("wind_turbine"))
    special["feedstock_flex"] = bool(special.get("feedstock_flex")) or has_text(tech.get("reg_pathway"), r"sorghum|milo|feedstock")
    special["icm"] = bool(special.get("icm")) or has_text(tech.get("technology"), r"\bICM\b") or trueish(tech.get("icm_p10"))
    special["technology_flag_source"] = "permit_summary_plus_dropdown_tech_flags"

    technology_flags["white_fox_membrane"] = bool(technology_flags.get("white_fox_membrane")) or trueish(tech.get("white_fox"))
    technology_flags["molecular_sieve_only"] = bool(technology_flags.get("molecular_sieve_only")) and not bool(technology_flags.get("white_fox_membrane"))
    technology_flags["chp"] = bool(technology_flags.get("chp")) or trueish(tech.get("chp"))
    technology_flags["waste_heat_recovery"] = bool(technology_flags.get("waste_heat_recovery")) or trueish(tech.get("waste_heat"))
    fiber_label = fiber_to_ethanol_label(tech.get("fiber_technology"))
    fiber_source = "tech_flags.fiber_technology" if fiber_label else ""
    if not fiber_label:
        fiber_label, fiber_source = lcfs_fiber_to_ethanol_label(row)
    technology_flags["fiber_to_ethanol"] = bool(technology_flags.get("fiber_to_ethanol")) or bool(fiber_label)
    if fiber_label:
        technology_flags["fiber_to_ethanol_technology"] = fiber_label
        technology_flags["fiber_to_ethanol_source"] = fiber_source
    else:
        technology_flags.setdefault("fiber_to_ethanol_technology", None)
        technology_flags.setdefault("fiber_to_ethanol_source", None)
    technology_flags["d3_capable"] = bool(technology_flags.get("d3_capable")) or bool(fiber_label) or has_text(tech.get("reg_pathway"), r"D3|EP3")
    technology_flags["generic_fiber_separation"] = bool(technology_flags.get("generic_fiber_separation")) or has_text(
        tech.get("fiber_technology"),
        r"\bFST\b|fiber separation technology|front[- ]end fiber separation|mechanical fiber separation",
    )
    technology_flags.pop("fiber_separation", None)
    technology_flags["high_protein"] = bool(technology_flags.get("high_protein")) or trueish(tech.get("high_pro"))
    technology_flags["corn_oil_extraction"] = bool(technology_flags.get("corn_oil_extraction")) or trueish(tech.get("dco_enhancement")) or bool(equipment.get("corn_oil_systems", {}).get("present"))
    technology_flags["edeniq"] = bool(technology_flags.get("edeniq")) or has_text(tech.get("fiber_technology"), r"edeniq")
    technology_flags["fluid_quip"] = bool(technology_flags.get("fluid_quip")) or has_text(tech.get("dco_enhancement"), r"fluid quip|fqpt|hi pro")
    technology_flags["icm_selective_milling"] = bool(technology_flags.get("icm_selective_milling")) or has_text(tech.get("special_tech"), r"selective milling")
    technology_flags["icm_fst"] = bool(technology_flags.get("icm_fst")) or has_text(tech.get("fiber_technology"), r"\bFST\b|fiber separation technology")
    technology_flags["co2_capture"] = bool(technology_flags.get("co2_capture")) or has_text(tech.get("special_tech"), r"co2|carbon capture|ccs|sequestration")
    technology_flags["rng_biogas"] = bool(technology_flags.get("rng_biogas")) or has_text(tech.get("gas_supply"), r"biogas|renewable natural gas|\bRNG\b|landfill gas|digester gas")
    technology_flags["source"] = "permit_summary_plus_dropdown_tech_flags"

    derivatives = permit.setdefault("derivatives", {})
    limits = permit.setdefault("limits", {})
    corn_grind = num((limits.get("corn_grind") or {}).get("value") if isinstance(limits.get("corn_grind"), dict) else None)
    facility_capacity_mgy = num(fac.get("ethanol_capacity_mgy"))
    total_storage = num((derivatives.get("total_corn_storage") or {}).get("value") if isinstance(derivatives.get("total_corn_storage"), dict) else None)

    def energy_value(*path: str) -> float | None:
        current: object = permit
        for part in path:
            current = current.get(part) if isinstance(current, dict) else None
        return num(current)

    dryer_mmbtu = energy_value("equipment", "dryers", "heat_input_mmbtu_hr", "value")
    boiler_mmbtu = energy_value("equipment", "boilers_process_heaters", "heat_input_mmbtu_hr", "value")
    rto_mmbtu = energy_value("equipment", "thermal_oxidizers_rtos", "heat_input_mmbtu_hr", "value")
    waste_heat_mmbtu = energy_value("equipment", "waste_heat_boilers", "heat_input_mmbtu_hr", "value")
    thermal_components = [value for value in (dryer_mmbtu, boiler_mmbtu, rto_mmbtu) if value is not None]
    total_thermal_mmbtu_hr = sum(thermal_components) if thermal_components else None

    derivatives["dryer_mmbtu_hr"] = metric(
        dryer_mmbtu,
        "MMBtu/hr",
        "largest dryer MMBtu/hr permit mention",
        "low" if dryer_mmbtu is not None else "missing_inputs",
        "Permit heat input is a nameplate/limit style value, not annual fuel consumption.",
    )
    derivatives["boiler_mmbtu_hr"] = metric(
        boiler_mmbtu,
        "MMBtu/hr",
        "largest boiler/process-heater MMBtu/hr permit mention",
        "low" if boiler_mmbtu is not None else "missing_inputs",
        "Permit heat input is a nameplate/limit style value, not annual fuel consumption.",
    )
    derivatives["rto_thermal_oxidizer_mmbtu_hr"] = metric(
        rto_mmbtu,
        "MMBtu/hr",
        "largest RTO/thermal oxidizer MMBtu/hr permit mention",
        "low" if rto_mmbtu is not None else "missing_inputs",
        "Can overlap with dryer controls and should not be treated as additive without review.",
    )
    derivatives["waste_heat_boiler_mmbtu_hr"] = metric(
        waste_heat_mmbtu,
        "MMBtu/hr",
        "largest waste-heat/heat-recovery boiler MMBtu/hr permit mention",
        "low" if waste_heat_mmbtu is not None else "missing_inputs",
        "Represents recovered-heat equipment capacity where found, not necessarily additional fuel input.",
    )
    derivatives["total_thermal_mmbtu_hr"] = metric(
        total_thermal_mmbtu_hr,
        "MMBtu/hr",
        "dryer_mmbtu_hr + boiler_mmbtu_hr + rto_thermal_oxidizer_mmbtu_hr where available",
        "low" if total_thermal_mmbtu_hr is not None else "missing_inputs",
        "Screening metric only; categories may overlap and permit heat input is not annual fuel use.",
    )
    if total_thermal_mmbtu_hr and facility_capacity_mgy:
        derivatives["total_thermal_mmbtu_hr_per_mgy"] = metric(
            total_thermal_mmbtu_hr / facility_capacity_mgy,
            "MMBtu/hr/MGY",
            "total_thermal_mmbtu_hr / fac_info.ethanol_capacity_mgy",
            "low",
            "Screening metric based on permit heat input and nameplate capacity.",
        )
        derivatives["estimated_btu_per_gal_from_heat_input"] = metric(
            total_thermal_mmbtu_hr * 1_000_000 * 8760 / (facility_capacity_mgy * 1_000_000),
            "BTU/gal",
            "total_thermal_mmbtu_hr * 1,000,000 * 8,760 / annual_nameplate_gallons",
            "low",
            "Assumes full-year operation at permitted/nameplate heat input; use only as an upper-bound screening proxy.",
        )
    if dryer_mmbtu and facility_capacity_mgy:
        derivatives["dryer_btu_per_gal"] = metric(
            dryer_mmbtu * 1_000_000 * 8760 / (facility_capacity_mgy * 1_000_000),
            "BTU/gal",
            "dryer_mmbtu_hr * 1,000,000 * 8,760 / annual_nameplate_gallons",
            "low",
            "Assumes full-year operation at the largest dryer heat-input mention; screening proxy only.",
        )

    daily_grain = None
    daily_confidence = "missing_inputs"
    daily_source = "not_available"
    if corn_grind:
        daily_grain = corn_grind / 365
        daily_confidence = "medium"
        daily_source = "permitted_corn_grind"
    elif facility_capacity_mgy:
        daily_grain = (facility_capacity_mgy * 1_000_000 / 3.0) / 365
        daily_confidence = "low"
        daily_source = "dropdown_facility_capacity_divided_by_3_gal_per_bu"

    if daily_grain:
        derivatives["grain_throughput_per_day"] = metric(
            daily_grain,
            "bu/day",
            "permitted_corn_bu_per_year / 365; fallback = fac_info.ethanol_capacity_mgy * 1,000,000 / 3.0 / 365",
            daily_confidence,
            f"daily_grain_source = {daily_source}",
        )
    if total_storage and daily_grain:
        derivatives["grain_storage_days"] = metric(
            total_storage / daily_grain,
            "days",
            "total_corn_storage_bu / daily_grain_bu; daily_grain_bu = permitted_corn_bu_per_year / 365, fallback = fac_info.ethanol_capacity_mgy * 1,000,000 / 3.0 / 365",
            "medium" if daily_source == "permitted_corn_grind" else "low",
            (
                f"Total corn storage = {total_storage:,.0f} bu; daily grain source = {daily_source}. "
                "Fallback assumes ethanol capacity / 3.0 gal per bushel when permit corn grind is unavailable."
            ),
        )

    return permit


def lcfs_only_technology_backfill(row: dict) -> dict | None:
    fiber_label, fiber_source = lcfs_fiber_to_ethanol_label(row)
    if not fiber_label:
        return None
    technology_flags = {
        "white_fox_membrane": False,
        "molecular_sieve_only": False,
        "chp": False,
        "waste_heat_recovery": False,
        "fiber_to_ethanol": True,
        "fiber_to_ethanol_technology": fiber_label,
        "fiber_to_ethanol_source": fiber_source,
        "d3_capable": True,
        "generic_fiber_separation": False,
        "high_protein": False,
        "corn_oil_extraction": False,
        "edeniq": fiber_label.lower() == "edeniq",
        "fluid_quip": False,
        "icm_selective_milling": False,
        "icm_fst": False,
        "co2_capture": False,
        "rng_biogas": False,
        "source": "lcfs_detail_backfill_no_operating_permit",
    }
    return {
        "source_file": None,
        "summary_file": None,
        "permit_number": None,
        "permit_type": "not available - LCFS technology backfill only",
        "permit_missing": True,
        "confidence": "lcfs_detail_technology_backfill",
        "notes": [
            "No operating permit summary is currently matched for this plant.",
            "This block only backfills fiber-to-ethanol technology from LCFS pathway detail so the technology provider is not lost.",
        ],
        "equipment": {"technology_flags": technology_flags},
        "limits": {},
        "derivatives": {},
    }


def field_present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return any(field_present(v) for v in value.values())
    return bool(clean(value))


def gap_report(data: list[dict]) -> dict:
    missing_permits = []
    missing_equipment = []
    missing_limits = []
    missing_derivative_inputs = []

    equipment_fields = [
        ("fermenter_count", ("equipment", "fermenters", "count")),
        ("dryer_count", ("equipment", "dryers", "count")),
        ("boiler_count", ("equipment", "boilers_process_heaters", "count")),
        ("rto_count", ("equipment", "thermal_oxidizers_rtos", "count")),
        ("corn_oil_system", ("equipment", "corn_oil_systems", "present")),
    ]
    limit_fields = [
        ("corn_grind_limit", ("limits", "corn_grind", "value")),
        ("ethanol_production_limit", ("limits", "ethanol_production", "value")),
        ("dryer_ddgs_limit", ("limits", "dryer_ddgs", "value")),
        ("emissions_limits", ("limits", "key_emissions", "source_lines")),
    ]
    derivative_fields = [
        ("ethanol_yield", ("derivatives", "ethanol_yield", "value")),
        ("ddgs_lb_per_bu", ("derivatives", "ddgs_lb_per_bu", "value")),
        ("thermal_btu_per_gal", ("derivatives", "thermal_btu_per_gal", "value")),
        ("fermentation_time", ("derivatives", "estimated_fermentation_time", "value")),
        ("grain_storage_days", ("derivatives", "grain_storage_days", "value")),
    ]

    for row in data:
        if not isinstance(row, dict) or not is_iowa(row):
            continue
        name = plant_label(row)
        if "new energy blue" in name.lower():
            continue
        epm = plant_epm(row)
        permit = row.get("operating_permit") if isinstance(row.get("operating_permit"), dict) else None
        item = {"epm": epm, "plant": name}
        if not permit or permit.get("permit_missing"):
            missing_permits.append(item)
            continue
        for group, fields, out in (
            ("equipment", equipment_fields, missing_equipment),
            ("limits", limit_fields, missing_limits),
            ("derivative_inputs", derivative_fields, missing_derivative_inputs),
        ):
            missing = []
            for label, path in fields:
                current = permit
                for part in path:
                    current = current.get(part) if isinstance(current, dict) else None
                if not field_present(current):
                    missing.append(label)
            if missing:
                out.append({**item, "missing": missing})

    return {
        "missing_permits": missing_permits,
        "missing_equipment_fields": missing_equipment,
        "missing_limits": missing_limits,
        "missing_derivative_inputs": missing_derivative_inputs,
    }


def load_permits() -> dict[str, dict]:
    permits: dict[str, dict] = {}
    for path in sorted(SUMMARY_DIR.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        parsed = parse_summary(path)
        if not parsed:
            continue
        epm = norm_id(value_after("EPM Number", path.read_text(encoding="utf-8", errors="replace")))
        # Prefer generated EPM-prefixed summaries over older hand-written notes.
        existing = permits.get(epm)
        if existing is None or re.match(r"^\d+_", path.name):
            permits[epm] = parsed
    return permits


def main() -> None:
    permits_by_epm = load_permits()

    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected top-level JSON list, got {type(data).__name__}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = JSON_PATH.with_name(f"{JSON_PATH.stem}.backup_{timestamp}{JSON_PATH.suffix}")
    shutil.copy2(JSON_PATH, backup_path)

    matched = []
    for row in data:
        if not isinstance(row, dict):
            continue
        row.pop("air_permit_description", None)
        epm = plant_epm(row)
        permit = permits_by_epm.get(epm)
        if permit:
            permit = enrich_permit_from_tech_flags(row, copy.deepcopy(permit))
            row["operating_permit"] = permit
            matched.append({"epm": epm, "plant": plant_label(row), "source_file": permit.get("source_file")})
        else:
            backfill = lcfs_only_technology_backfill(row)
            if backfill:
                row["operating_permit"] = backfill
            else:
                row.pop("operating_permit", None)

    report = gap_report(data)
    GAP_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GAP_REPORT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with JSON_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Updated LCFS dropdown JSON with operating_permit blocks")
    print(f"JSON path: {JSON_PATH}")
    print(f"Backup path: {backup_path}")
    print(f"Summary folder: {SUMMARY_DIR}")
    print(f"Parsed permit summaries: {len(permits_by_epm)}")
    print(f"Matched JSON plants: {len(matched)}")
    print(f"Gap report path: {GAP_REPORT_PATH}")

    print("\nMissing Iowa permits:")
    for item in report["missing_permits"]:
        print(f"  EPM {item['epm']}: {item['plant']}")

    print("\nIowa permits missing equipment fields:")
    for item in report["missing_equipment_fields"][:80]:
        print(f"  EPM {item['epm']}: {item['plant']} -> {', '.join(item['missing'])}")

    print("\nIowa permits missing limits:")
    for item in report["missing_limits"][:80]:
        print(f"  EPM {item['epm']}: {item['plant']} -> {', '.join(item['missing'])}")

    print("\nIowa permits missing derivative inputs:")
    for item in report["missing_derivative_inputs"][:80]:
        print(f"  EPM {item['epm']}: {item['plant']} -> {', '.join(item['missing'])}")


if __name__ == "__main__":
    main()
