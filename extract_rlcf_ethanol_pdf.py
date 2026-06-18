from pathlib import Path
import re

import pandas as pd
import pdfplumber


PDF_PATH = Path(r"C:\Users\ehakm\Downloads\rlcf012_approved_carbon_intensities_current_nov2024_v3.pdf")
OUT_XLSX = Path(r"C:\Users\ehakm\Downloads\rlcf012_ethanol_locations.xlsx")
PDF_REVISION_DATE = pd.Timestamp("2024-11-27")


def clean_cell(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def main():
    rows = []
    samples = []
    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"pages={len(pdf.pages)}")
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            if page_num <= 3:
                text = page.extract_text() or ""
                samples.append((page_num, text[:1000], len(tables), [len(t) for t in tables[:3]]))
            for table_idx, table in enumerate(tables, start=1):
                for row_idx, row in enumerate(table, start=1):
                    cells = [clean_cell(c) for c in row]
                    if any(cells):
                        rows.append(
                            {
                                "page": page_num,
                                "table": table_idx,
                                "row": row_idx,
                                **{f"col_{i+1}": cell for i, cell in enumerate(cells)},
                                "row_text": " | ".join(c for c in cells if c),
                            }
                        )

    print("samples:")
    for page_num, text, table_count, table_lengths in samples:
        print(f"--- page {page_num} tables={table_count} lengths={table_lengths} ---")
        print(text[:1000])

    raw = pd.DataFrame(rows)
    if raw.empty:
        raise SystemExit("No tables extracted from PDF.")

    mask = raw["row_text"].str.contains(r"\bethanol\b", case=False, na=False)
    ethanol = raw.loc[mask].copy()

    ethanol_clean = pd.DataFrame(
        {
            "source_pdf": PDF_PATH.name,
            "source_page": ethanol["page"],
            "fuel_code": ethanol["col_1"],
            "fuel": ethanol["col_2"],
            "company": ethanol["col_3"],
            "carbon_intensity_gCO2e_per_MJ": pd.to_numeric(ethanol["col_4"], errors="coerce"),
            "effective_date": pd.to_datetime(ethanol["col_5"], errors="coerce"),
            "expiry_date": pd.to_datetime(ethanol["col_6"], errors="coerce"),
        }
    )
    ethanol_clean["current_as_of_pdf_revision"] = (
        (ethanol_clean["effective_date"].isna() | (ethanol_clean["effective_date"] <= PDF_REVISION_DATE))
        & (ethanol_clean["expiry_date"].isna() | (ethanol_clean["expiry_date"] >= PDF_REVISION_DATE))
    )
    ethanol_clean = ethanol_clean.sort_values(["company", "fuel_code", "effective_date"], na_position="last")

    current_clean = ethanol_clean.loc[ethanol_clean["current_as_of_pdf_revision"]].copy()
    print(f"table rows={len(raw)} ethanol rows={len(ethanol_clean)} current_as_of_revision={len(current_clean)}")

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        ethanol_clean.to_excel(writer, sheet_name="ethanol_clean", index=False)
        current_clean.to_excel(writer, sheet_name="current_asof_2024_11_27", index=False)
        ethanol.to_excel(writer, sheet_name="ethanol_raw_rows", index=False)
        raw.to_excel(writer, sheet_name="all_extracted_rows", index=False)

    print(f"wrote={OUT_XLSX}")


if __name__ == "__main__":
    main()
