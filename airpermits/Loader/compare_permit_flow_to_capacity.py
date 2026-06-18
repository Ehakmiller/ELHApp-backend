from __future__ import annotations

from pathlib import Path
import csv
import json
import re

import pdfplumber


PDF_DIR = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\PDF")
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
INVENTORY_PATH = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_air_permit_pdf_inventory.csv")
OUT_CSV = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_permit_flow_capacity_comparison.csv")
OUT_MD = Path(r"C:\Users\ehakm\Documents\ELHApp-backend\airpermits\summary\_permit_flow_capacity_comparison.md")

GPM_TO_MGY = 60 * 24 * 365 / 1_000_000


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def norm_epm(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return re.sub(r"\.0$", "", text)


def classify_stream(line: str) -> str:
    low = line.lower()
    if "beer" in low:
        return "beer"
    if "thin stillage" in low or "stillaqe" in low:
        return "thin_stillage"
    if "whole stillage" in low:
        return "whole_stillage"
    if "syrup" in low or "sugar" in low:
        return "syrup"
    if "ethanol" in low:
        return "ethanol_or_process"
    return "unknown"


def flow_gpm(line: str) -> float | None:
    patterns = [
        r"([0-9][0-9,.]*)\s*gallons\s*/\s*minute",
        r"([0-9][0-9,.]*)\s*gal\s*/\s*min",
        r"([0-9][0-9,.]*)\s*gpm\b",
        r"([0-9][0-9,.]*)\s*gallons/minute",
    ]
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.I)
        if match:
            return float(match.group(1).replace(",", ""))

    hourly = re.search(r"([0-9][0-9,.]*)\s*gal(?:lon)?s?\s*/\s*hr", line, flags=re.I)
    if hourly:
        return float(hourly.group(1).replace(",", "")) / 60
    return None


def implied_capacity_mgy(gpm: float, beer_pct: float) -> float:
    return gpm * GPM_TO_MGY * beer_pct


def load_inventory() -> dict[str, str]:
    if not INVENTORY_PATH.exists():
        return {}
    out: dict[str, str] = {}
    with INVENTORY_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            epm = norm_epm(row.get("matched EPM") or row.get("matched_epm"))
            if epm:
                out[clean(row.get("file_name"))] = epm
    return out


def load_capacity() -> dict[str, dict[str, object]]:
    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    out: dict[str, dict[str, object]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
        epm = norm_epm(row.get("EPM_NUMBER") or row.get("epm_number") or fac.get("epm"))
        if not epm:
            continue
        out[epm] = {
            "plant": clean(fac.get("plant_name") or row.get("plant_name")),
            "city": clean(fac.get("city") or row.get("city")),
            "state": clean(fac.get("state") or row.get("state")),
            "capacity_mgy": float(fac.get("ethanol_capacity_mgy")) if fac.get("ethanol_capacity_mgy") is not None else None,
        }
    return out


def extract_lines(pdf_path: Path) -> list[tuple[int, str]]:
    pattern = re.compile(
        r"evaporator|evaporation|\bMVR\b|mechanical vapor|vapor recompression|syrup concentr|thin stillage|whole stillage|beer|gpm|gallons/minute|gal/min|gal/hr",
        flags=re.I,
    )
    hits: list[tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages[:35], start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = re.sub(r"\s+", " ", raw).strip()
                if pattern.search(line) and flow_gpm(line) is not None:
                    hits.append((page_num, line))
    return hits


def main() -> None:
    file_to_epm = load_inventory()
    capacity_by_epm = load_capacity()
    rows: list[dict[str, object]] = []

    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        epm = file_to_epm.get(pdf_path.name)
        if not epm:
            continue
        facility = capacity_by_epm.get(epm, {})
        capacity = facility.get("capacity_mgy")
        for page_num, line in extract_lines(pdf_path):
            gpm = flow_gpm(line)
            if gpm is None:
                continue
            stream = classify_stream(line)
            cap_14 = implied_capacity_mgy(gpm, 0.14) if stream == "beer" else None
            cap_15 = implied_capacity_mgy(gpm, 0.15) if stream == "beer" else None
            cap_16 = implied_capacity_mgy(gpm, 0.16) if stream == "beer" else None
            pct_diff_15 = ((cap_15 - capacity) / capacity * 100) if cap_15 is not None and capacity else None
            rows.append(
                {
                    "EPM": epm,
                    "Plant": facility.get("plant", ""),
                    "City": facility.get("city", ""),
                    "State": facility.get("state", ""),
                    "file_name": pdf_path.name,
                    "page": page_num,
                    "stream_class": stream,
                    "flow_gpm": gpm,
                    "dropdown_capacity_mgy": capacity,
                    "implied_mgy_14pct_beer": cap_14,
                    "implied_mgy_15pct_beer": cap_15,
                    "implied_mgy_16pct_beer": cap_16,
                    "pct_diff_vs_capacity_at_15pct": pct_diff_15,
                    "source_line": line,
                }
            )

    rows.sort(key=lambda row: (clean(row["State"]), clean(row["Plant"]), clean(row["stream_class"]), -float(row["flow_gpm"])))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    beer_rows = [row for row in rows if row["stream_class"] == "beer"]
    with OUT_MD.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Permit Flow To Ethanol Capacity Comparison\n\n")
        f.write("Beer stream formula: `beer_gpm * 60 * 24 * 365 * beer_abv / 1,000,000`.\n\n")
        f.write("## Beer Feed Comparisons\n\n")
        f.write("| EPM | Plant | City | Flow | Capacity | Implied @14% | Implied @15% | Implied @16% | Diff @15% | Source |\n")
        f.write("|---:|---|---|---:|---:|---:|---:|---:|---:|---|\n")
        for row in beer_rows:
            source = clean(row["source_line"]).replace("|", "/")
            if len(source) > 150:
                source = source[:147] + "..."
            diff = row["pct_diff_vs_capacity_at_15pct"]
            f.write(
                f"| {row['EPM']} | {clean(row['Plant']).replace('|', '/')} | {row['City']} | "
                f"{float(row['flow_gpm']):,.0f} gpm | {float(row['dropdown_capacity_mgy'] or 0):,.1f} | "
                f"{float(row['implied_mgy_14pct_beer'] or 0):,.1f} | "
                f"{float(row['implied_mgy_15pct_beer'] or 0):,.1f} | "
                f"{float(row['implied_mgy_16pct_beer'] or 0):,.1f} | "
                f"{'' if diff is None else f'{diff:,.1f}%'} | {source} |\n"
            )

    print(f"Wrote {len(rows)} flow rows")
    print(f"Beer flow comparison rows: {len(beer_rows)}")
    print(f"CSV: {OUT_CSV}")
    print(f"Markdown: {OUT_MD}")
    print("\nBeer feed comparisons:")
    for row in beer_rows:
        print(
            f"  EPM {row['EPM']} {row['Plant']}: {float(row['flow_gpm']):,.0f} gpm beer -> "
            f"{float(row['implied_mgy_15pct_beer']):,.1f} MGY @15% vs "
            f"{float(row['dropdown_capacity_mgy'] or 0):,.1f} MGY"
        )


if __name__ == "__main__":
    main()
