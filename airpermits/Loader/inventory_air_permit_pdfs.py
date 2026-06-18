from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import csv
import json
import re

import pdfplumber


BACKEND_ROOT = Path(r"C:\Users\ehakm\Documents\ELHApp-backend")
PDF_DIR = BACKEND_ROOT / "airpermits" / "PDF"
SUMMARY_DIR = BACKEND_ROOT / "airpermits" / "summary"
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
OUT_CSV = SUMMARY_DIR / "_air_permit_pdf_inventory.csv"
OUT_TSV = SUMMARY_DIR / "_air_permit_pdf_inventory.tsv"
OUT_MISSING_REVIEW = SUMMARY_DIR / "_target_missing_iowa_pdf_review.txt"


TARGET_ALTERNATES = {
    "3591": ["corn lp", "central iowa renewable energy", "goldfield"],
    "3643": ["louis dreyfus", "ldc", "grand junction"],
    "3660": ["plymouth energy", "merrill"],
    "3696": ["quad county corn processors", "quad county", "galva"],
    "3705": ["siouxland energy cooperative", "siouxland energy", "sioux center"],
    "3734": ["verbio nevada", "verbio", "heartland corn products", "dupont cellulosic ethanol", "nevada"],
}

GENERAL_ALTERNATES = {
    "3557": ["vantage corn processors", "adm corn processing", "vcp corn processing"],
    "3558": ["adm corn processing", "adm cedar rapids"],
    "3570": ["big river resources west burlington", "big river west burlington"],
    "3571": ["big river united energy", "big river dyersville"],
    "3609": ["grain processing corporation", "gpc"],
    "3708": ["southwest iowa renewable energy", "southwest iowa renewable", "sire"],
}

MANUAL_FILE_EPM = {
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
}
MANUAL_UNMATCHED_FILES = {"25-TV-001.pdf"}


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def norm(value: object) -> str:
    text = clean(value).lower().replace("\xa0", " ")
    text = text.replace("sothwest", "southwest")
    text = re.sub(
        r"\b(llc|inc|ltd|lllp|co|company|corp|corporation|ethanol|energy|renewable|renewables|biorefining|biorefinning|plant|corn|processing|processors|cooperative|holdings|the)\b",
        " ",
        text,
    )
    return re.sub(r"[^a-z0-9]+", "", text)


def state_abbrev(value: object) -> str:
    text = clean(value).replace("\xa0", " ")
    return text[:2].upper() if text else ""


def first_match(patterns: list[str], text: str, flags: int = re.I) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return re.sub(r"\s+", " ", clean(match.group(1)))
    return ""


@dataclass
class Facility:
    epm: str
    facility_id: str
    facility_name: str
    ownership: str
    city: str
    state: str


def read_pdf_head(path: Path, max_pages: int = 6) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:max_pages]:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_pdf_identity(path: Path, text: str) -> dict[str, str]:
    facility_name = first_match([r"Name of Permitted Facility:\s*([^\n]+)", r"Facility Name:\s*([^\n]+)"], text)
    if facility_name and re.match(r"^(?:LLC|L\.?L\.?C\.?|Inc\.?|LTD|LLLP)\b", (text.split(facility_name, 1)[-1].lstrip().splitlines() or [""])[0], flags=re.I):
        facility_name = f"{facility_name} {(text.split(facility_name, 1)[-1].lstrip().splitlines() or [''])[0]}".strip()
    if not facility_name:
        facility_name = first_match(
            [
                r"Table 1\s*-\s*Facility Information.*?Facility Name\s+City\s+Operating Permit No\.\s*\n[^\n]*?\s+[^\n]*?\s+(.+?)\s+[A-Za-z .'-]+\s+\d{2}-TV",
                r"EIQ No\.\s+Plant No\.\s+Facility Name\s+City\s+Operating Permit No\.\s*\n[^\n]*?\s+[^\n]*?\s+(.+?)\s+[A-Za-z .'-]+\s+\d{2}-TV",
            ],
            text,
            flags=re.I | re.S,
        )
    facility_name = re.sub(r"\s+", " ", facility_name.replace("\n", " ")).strip()
    company_name = facility_name
    permit_number = first_match(
        [
            r"Air Quality Operating Permit Number:\s*([A-Za-z0-9_\-]+)",
            r"Operating Permit No\.\s*\n.*?(\d{2}-TV[^\s]+)",
            r"Permit Number:\s*([A-Za-z0-9_\-]+)",
            r"Final Title V Operating Permit #:\s*([A-Za-z0-9_\-]+)",
        ],
        text,
        flags=re.I | re.S,
    )
    plant_number = first_match(
        [
            r"EIQ No\.\s+Plant No\.\s+Facility Name\s+City\s+Operating Permit No\.\s*\n\s*\S+\s+(\S+)",
            r"Facility File Number:\s*([A-Za-z0-9_\-]+)",
            r"Plant No\.\s*([A-Za-z0-9_\-]+)",
        ],
        text,
        flags=re.I | re.S,
    )
    location = first_match([r"Facility Location:\s*(.+)", r"Facility Location\s+(.+)"], text)
    city = first_match(
        [
            r"Facility Location:[^\n]*,\s*([A-Za-z .'-]+),?\s+IA\b",
            r"Facility Location:[^\n]*(?:\n|\r\n)([A-Za-z .'-]+),\s*IA\b",
            r"Facility Name\s+City\s+Operating Permit No\.\s*\n.*?\s+([A-Za-z .'-]+)\s+\d{2}-TV",
        ],
        text,
        flags=re.I | re.S,
    )
    city = re.sub(r"\s+", " ", city).strip()
    return {
        "file_name": path.name,
        "permit_number": permit_number or path.stem,
        "facility_name": facility_name,
        "company_name": company_name,
        "city": city,
        "state": "IA" if " IA" in text[:2500] or "Iowa" in text[:2500] else "",
        "plant_number": plant_number,
        "location": location,
        "head_text": text,
    }


def load_iowa_facilities() -> list[Facility]:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    plants = data if isinstance(data, list) else data.get("plants", [])
    out = []
    for row in plants:
        fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
        if state_abbrev(fac.get("state")) != "IA":
            continue
        out.append(
            Facility(
                epm=clean(fac.get("epm")),
                facility_id=clean(fac.get("facility_id")),
                facility_name=clean(fac.get("plant_name")),
                ownership=clean(fac.get("ownership")),
                city=clean(fac.get("city")),
                state="IA",
            )
        )
    return out


def alternate_tokens(epm: str) -> list[str]:
    return GENERAL_ALTERNATES.get(epm, []) + TARGET_ALTERNATES.get(epm, [])


def score_facility(identity: dict[str, str], fac: Facility) -> tuple[float, str]:
    pdf_name = norm(identity["facility_name"])
    pdf_city = norm(identity["city"])
    haystack = norm(" ".join([identity["facility_name"], identity["company_name"], identity["city"], identity["location"], identity["head_text"][:2500]]))
    name_candidates = [fac.facility_name, fac.ownership, *alternate_tokens(fac.epm)]
    name_scores = [SequenceMatcher(None, pdf_name, norm(item)).ratio() for item in name_candidates if norm(item)]
    contains_scores = [1.0 for item in name_candidates if norm(item) and norm(item) in haystack]
    name_score = max(name_scores + contains_scores + [0.0])
    city_score = 1.0 if pdf_city and pdf_city == norm(fac.city) else (0.6 if norm(fac.city) and norm(fac.city) in haystack else 0.0)
    score = name_score * 0.78 + city_score * 0.22
    return score, f"name={name_score:.2f}; city={city_score:.2f}"


def match_pdf(identity: dict[str, str], facilities: list[Facility]) -> tuple[Facility | None, float, str]:
    if identity["file_name"] in MANUAL_UNMATCHED_FILES:
        return None, 1.0, "manual_non_ethanol_unmatched"
    override = MANUAL_FILE_EPM.get(identity["file_name"])
    if override:
        for fac in facilities:
            if fac.epm == override:
                return fac, 1.0, "manual_filename_epm_override"

    scores = []
    for fac in facilities:
        score, reason = score_facility(identity, fac)
        scores.append((score, fac, reason))
    scores.sort(reverse=True, key=lambda item: item[0])
    best_score, best_fac, best_reason = scores[0]
    if best_score >= 0.62:
        return best_fac, best_score, best_reason
    return None, best_score, best_reason


def main() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    facilities = load_iowa_facilities()
    rows = []
    by_epm = {fac.epm: fac for fac in facilities}

    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        text = read_pdf_head(pdf)
        identity = parse_pdf_identity(pdf, text)
        matched, score, reason = match_pdf(identity, facilities)
        rows.append(
            {
                "file_name": identity["file_name"],
                "permit_number": identity["permit_number"],
                "facility_name": identity["facility_name"],
                "company_name": identity["company_name"],
                "city": matched.city if matched else identity["city"],
                "state": "IA",
                "plant_number": identity["plant_number"],
                "matched_epm": matched.epm if matched else "",
                "matched_dropdown_name": matched.facility_name if matched else "",
                "match_score": f"{score:.3f}",
                "match_reason": reason,
            }
        )

    fields = [
        "file_name",
        "permit_number",
        "facility_name",
        "company_name",
        "city",
        "state",
        "plant_number",
        "matched_epm",
        "matched_dropdown_name",
        "match_score",
        "match_reason",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    present_epms = {row["matched_epm"] for row in rows if row["matched_epm"]}
    review_lines = []
    review_lines.append("Target missing Iowa plants PDF inventory review")
    review_lines.append("")
    for epm, aliases in TARGET_ALTERNATES.items():
        fac = by_epm.get(epm)
        hits = [row for row in rows if row["matched_epm"] == epm]
        if hits:
            review_lines.append(f"EPM {epm}: {fac.facility_name if fac else ''} - PRESENT")
            for hit in hits:
                review_lines.append(f"  {hit['file_name']} | permit {hit['permit_number']} | PDF facility: {hit['facility_name']}")
        else:
            # Also report near textual hits in unmatched or other-matched PDFs for manual review.
            near = []
            for row in rows:
                text = " ".join([row["facility_name"], row["company_name"], row["city"], row["file_name"]]).lower()
                if any(alias.lower() in text for alias in aliases if len(alias) > 4):
                    near.append(row)
            review_lines.append(f"EPM {epm}: {fac.facility_name if fac else ''} - STILL NEEDS PERMIT DOWNLOAD")
            if near:
                review_lines.append("  Possible textual hits, but not matched to this EPM:")
                for hit in near:
                    review_lines.append(f"  {hit['file_name']} -> EPM {hit['matched_epm'] or 'UNMATCHED'} | {hit['facility_name']}")
        review_lines.append("")

    OUT_MISSING_REVIEW.write_text("\n".join(review_lines) + "\n", encoding="utf-8")

    print(f"Inventory rows: {len(rows)}")
    print(f"Wrote: {OUT_CSV}")
    print(f"Wrote: {OUT_TSV}")
    print(f"Wrote: {OUT_MISSING_REVIEW}")
    print("")
    print("Inventory")
    for row in rows:
        print(
            f"{row['file_name']} | {row['permit_number']} | {row['facility_name']} | "
            f"{row['city']}, {row['state']} | plant {row['plant_number']} | EPM {row['matched_epm'] or 'UNMATCHED'}"
        )
    print("")
    print("\n".join(review_lines))


if __name__ == "__main__":
    main()
