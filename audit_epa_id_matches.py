from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
OUT_XLSX = Path(__file__).with_name("EPA_ID_Match_Audit.xlsx")

CORN_TABLE = "corn_processors"
EPA_TABLE = "EPA_Greenhouse_Gas_Reporting"


def norm_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    stop_words = {
        "LLC",
        "INC",
        "CO",
        "COMPANY",
        "CORP",
        "CORPORATION",
        "LTD",
        "LIMITED",
        "LP",
        "LLP",
        "LLLP",
        "THE",
        "PLANT",
        "FACILITY",
        "ETHANOL",
        "BIOREFINERY",
        "BIOREFINING",
        "RENEWABLE",
        "FUELS",
        "FUEL",
    }
    words = [w for w in text.split() if w and w not in stop_words]
    return " ".join(words)


def norm_city(value: object) -> str:
    return norm_text(value)


def norm_state(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).replace("\xa0", " ").strip().upper()


def norm_zip(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\xa0", " ").strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits[:5] if len(digits) >= 5 else digits


def norm_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\xa0", " ").strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text


def pick_column(df: pd.DataFrame, candidates: list[str], required: bool = True) -> str | None:
    lookup = {c.lower(): c for c in df.columns}
    compact = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in df.columns}
    for name in candidates:
        if name.lower() in lookup:
            return lookup[name.lower()]
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in compact:
            return compact[key]
    if required:
        raise KeyError(f"Could not find any of these columns: {candidates}")
    return None


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return round(100.0 * SequenceMatcher(None, a, b).ratio(), 1)


def classify(score: float, city_match: bool, state_match: bool) -> str:
    if state_match and city_match and score >= 90:
        return "strong"
    if state_match and city_match and score >= 78:
        return "review"
    if state_match and score >= 88:
        return "review_city_mismatch"
    return "weak"


def action_label(match_status: str, facility_id_match: bool | None, frs_id_match: bool | None) -> str:
    if match_status in {"weak", "no_state_candidate"}:
        return "do_not_update_from_this_match"
    if facility_id_match is True and (frs_id_match is True or frs_id_match is None):
        return "already_matches_epa_source"
    if facility_id_match is False or frs_id_match is False:
        return "id_conflict_review_before_sql"
    return "candidate_for_review"


def has_missing_existing_id(row: pd.Series) -> bool:
    return not norm_id(row.get("corn_existing_epa_facility_id")) or not norm_id(
        row.get("corn_existing_frs_id")
    )


def load_table(con: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f'SELECT * FROM "{table}"', con)


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as con:
        corn = load_table(con, CORN_TABLE)
        epa = load_table(con, EPA_TABLE)

    corn_cols = {
        "id": pick_column(corn, ["EPM_NUMBER", "epm", "epm_number", "facility_id", "id"], required=False),
        "plant": pick_column(corn, ["Plant", "plant_name", "Facility Name", "facility_name", "Name"]),
        "owner": pick_column(corn, ["Ownership", "owner", "Company"], required=False),
        "state": pick_column(corn, ["State", "state"]),
        "city": pick_column(corn, ["City", "city"]),
        "zip": pick_column(corn, ["Zip Code", "zip", "zipcode", "postal_code"], required=False),
        "existing_epa_facility_id": pick_column(corn, ["Facility Id", "EPA Facility ID", "epa_facility_id"], required=False),
        "existing_frs_id": pick_column(corn, ["FRS Id", "frs_id"], required=False),
    }
    epa_cols = {
        "epa_id": pick_column(
            epa,
            [
                "EPA Facility ID",
                "epa_facility_id",
                "facility_id",
                "GHGRP ID",
                "ghgrp_id",
                "FRS ID",
                "frs_id",
            ],
            required=False,
        ),
        "facility": pick_column(epa, ["Facility Name", "facility_name", "FACILITY_NAME", "Name"]),
        "state": pick_column(epa, ["State", "state"]),
        "city": pick_column(epa, ["City", "city"]),
        "zip": pick_column(epa, ["Zip Code", "zip", "zipcode", "postal_code"], required=False),
        "frs_id": pick_column(epa, ["FRS Id", "frs_id"], required=False),
    }

    corn_key_cols = [
        col
        for col in [
            corn_cols["id"],
            corn_cols["plant"],
            corn_cols["owner"],
            corn_cols["state"],
            corn_cols["city"],
            corn_cols["zip"],
            corn_cols["existing_epa_facility_id"],
            corn_cols["existing_frs_id"],
        ]
        if col
    ]
    corn = (
        corn.groupby(corn_key_cols, dropna=False)
        .size()
        .reset_index(name="source_row_count")
    )

    audit_rows: list[dict[str, object]] = []
    candidates_rows: list[dict[str, object]] = []
    zip_rows: list[dict[str, object]] = []

    epa_work = epa.copy()
    epa_work["_state_norm"] = epa_work[epa_cols["state"]].map(norm_state)
    epa_work["_city_norm"] = epa_work[epa_cols["city"]].map(norm_city)
    epa_work["_zip_norm"] = epa_work[epa_cols["zip"]].map(norm_zip) if epa_cols["zip"] else ""
    epa_work["_facility_norm"] = epa_work[epa_cols["facility"]].map(norm_text)

    for _, c in corn.iterrows():
        corn_state = norm_state(c[corn_cols["state"]])
        corn_city = norm_city(c[corn_cols["city"]])
        corn_zip = norm_zip(c[corn_cols["zip"]]) if corn_cols["zip"] else ""
        corn_name = norm_text(c[corn_cols["plant"]])

        same_state = epa_work[epa_work["_state_norm"] == corn_state].copy()
        same_city = same_state[same_state["_city_norm"] == corn_city].copy()
        pool = same_city if not same_city.empty else same_state

        scored = []
        for _, e in pool.iterrows():
            score = similarity(corn_name, e["_facility_norm"])
            city_match = bool(corn_city and corn_city == e["_city_norm"])
            state_match = bool(corn_state and corn_state == e["_state_norm"])
            scored.append((score, city_match, state_match, e))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best = scored[0] if scored else None

        def base_row() -> dict[str, object]:
            return {
                "corn_epm_or_id": c[corn_cols["id"]] if corn_cols["id"] else "",
                "corn_plant": c[corn_cols["plant"]],
                "corn_owner": c[corn_cols["owner"]] if corn_cols["owner"] else "",
                "corn_city": c[corn_cols["city"]],
                "corn_state": c[corn_cols["state"]],
                "corn_zip": c[corn_cols["zip"]] if corn_cols["zip"] else "",
                "corn_existing_epa_facility_id": c[corn_cols["existing_epa_facility_id"]]
                if corn_cols["existing_epa_facility_id"]
                else "",
                "corn_existing_frs_id": c[corn_cols["existing_frs_id"]]
                if corn_cols["existing_frs_id"]
                else "",
                "source_row_count": c["source_row_count"],
            }

        if best is None:
            if corn_zip:
                zip_pool = epa_work[epa_work["_zip_norm"] == corn_zip].copy()
                zip_scored = []
                for _, ze in zip_pool.iterrows():
                    zip_score = similarity(corn_name, ze["_facility_norm"])
                    zip_scored.append((zip_score, ze))
                zip_scored.sort(key=lambda x: x[0], reverse=True)
                corn_existing_epa_id = (
                    norm_id(c[corn_cols["existing_epa_facility_id"]])
                    if corn_cols["existing_epa_facility_id"]
                    else ""
                )
                for rank, (zip_score, ze) in enumerate(zip_scored[:5], start=1):
                    zip_epa_id = norm_id(ze[epa_cols["epa_id"]]) if epa_cols["epa_id"] else ""
                    zip_rows.append(
                        {
                            **base_row(),
                            "zip_match_rank": rank,
                            "zip_match_score": zip_score,
                            "normalized_zip": corn_zip,
                            "zip_epa_id": zip_epa_id,
                            "zip_epa_frs_id": norm_id(ze[epa_cols["frs_id"]]) if epa_cols["frs_id"] else "",
                            "zip_epa_facility": ze[epa_cols["facility"]],
                            "zip_epa_city": ze[epa_cols["city"]],
                            "zip_epa_state": ze[epa_cols["state"]],
                            "zip_epa_zip": ze[epa_cols["zip"]] if epa_cols["zip"] else "",
                            "zip_same_as_best_epa_id": None,
                            "zip_same_as_existing_epa_id": zip_epa_id == corn_existing_epa_id
                            if zip_epa_id and corn_existing_epa_id
                            else None,
                        }
                    )
            audit_rows.append(
                {
                    **base_row(),
                    "name_location_match_status": "no_state_candidate",
                    "match_score": 0,
                    "epa_id": "",
                    "epa_frs_id": "",
                    "epa_facility": "",
                    "epa_city": "",
                    "epa_state": "",
                    "epa_facility_id_matches_existing": None,
                    "epa_frs_id_matches_existing": None,
                    "audit_action": "do_not_update_from_this_match",
                    "city_match": False,
                    "state_match": False,
                    "candidate_count_same_state": len(same_state),
                    "candidate_count_same_city": len(same_city),
                }
            )
            continue

        score, city_match, state_match, e = best
        match_status = classify(score, city_match, state_match)
        corn_existing_epa_id = (
            norm_id(c[corn_cols["existing_epa_facility_id"]])
            if corn_cols["existing_epa_facility_id"]
            else ""
        )
        corn_existing_frs_id = (
            norm_id(c[corn_cols["existing_frs_id"]])
            if corn_cols["existing_frs_id"]
            else ""
        )
        epa_id = norm_id(e[epa_cols["epa_id"]]) if epa_cols["epa_id"] else ""
        epa_frs_id = norm_id(e[epa_cols["frs_id"]]) if epa_cols["frs_id"] else ""
        facility_id_match = (
            corn_existing_epa_id == epa_id
            if corn_existing_epa_id and epa_id
            else None
        )
        frs_id_match = (
            corn_existing_frs_id == epa_frs_id
            if corn_existing_frs_id and epa_frs_id
            else None
        )
        audit_rows.append(
            {
                **base_row(),
                "name_location_match_status": match_status,
                "match_score": score,
                "epa_id": epa_id,
                "epa_frs_id": epa_frs_id,
                "epa_facility": e[epa_cols["facility"]],
                "epa_city": e[epa_cols["city"]],
                "epa_state": e[epa_cols["state"]],
                "epa_facility_id_matches_existing": facility_id_match,
                "epa_frs_id_matches_existing": frs_id_match,
                "audit_action": action_label(match_status, facility_id_match, frs_id_match),
                "city_match": city_match,
                "state_match": state_match,
                "candidate_count_same_state": len(same_state),
                "candidate_count_same_city": len(same_city),
            }
        )

        for rank, (cand_score, cand_city_match, cand_state_match, cand) in enumerate(scored[:5], start=1):
            candidates_rows.append(
                {
                    **base_row(),
                    "candidate_rank": rank,
                    "candidate_score": cand_score,
                    "epa_id": norm_id(cand[epa_cols["epa_id"]]) if epa_cols["epa_id"] else "",
                    "epa_frs_id": norm_id(cand[epa_cols["frs_id"]]) if epa_cols["frs_id"] else "",
                    "epa_facility": cand[epa_cols["facility"]],
                    "epa_city": cand[epa_cols["city"]],
                    "epa_state": cand[epa_cols["state"]],
                    "city_match": cand_city_match,
                    "state_match": cand_state_match,
                }
            )

        if corn_zip:
            zip_pool = epa_work[epa_work["_zip_norm"] == corn_zip].copy()
            zip_scored = []
            for _, ze in zip_pool.iterrows():
                zip_score = similarity(corn_name, ze["_facility_norm"])
                zip_scored.append((zip_score, ze))

            zip_scored.sort(key=lambda x: x[0], reverse=True)
            for rank, (zip_score, ze) in enumerate(zip_scored[:5], start=1):
                zip_epa_id = norm_id(ze[epa_cols["epa_id"]]) if epa_cols["epa_id"] else ""
                zip_epa_frs_id = norm_id(ze[epa_cols["frs_id"]]) if epa_cols["frs_id"] else ""
                zip_rows.append(
                    {
                        **base_row(),
                        "zip_match_rank": rank,
                        "zip_match_score": zip_score,
                        "normalized_zip": corn_zip,
                        "zip_epa_id": zip_epa_id,
                        "zip_epa_frs_id": zip_epa_frs_id,
                        "zip_epa_facility": ze[epa_cols["facility"]],
                        "zip_epa_city": ze[epa_cols["city"]],
                        "zip_epa_state": ze[epa_cols["state"]],
                        "zip_epa_zip": ze[epa_cols["zip"]] if epa_cols["zip"] else "",
                        "zip_same_as_best_epa_id": zip_epa_id == epa_id if zip_epa_id and epa_id else None,
                        "zip_same_as_existing_epa_id": zip_epa_id == corn_existing_epa_id
                        if zip_epa_id and corn_existing_epa_id
                        else None,
                    }
                )

    audit = pd.DataFrame(audit_rows).sort_values(
        ["audit_action", "name_location_match_status", "match_score", "corn_state", "corn_city", "corn_plant"],
        ascending=[True, True, False, True, True, True],
    )
    candidates = pd.DataFrame(candidates_rows)
    zip_matches = pd.DataFrame(zip_rows)
    id_conflicts = audit[
        (audit["epa_facility_id_matches_existing"] == False)
        | (audit["epa_frs_id_matches_existing"] == False)
    ].copy()
    missing_existing_ids = audit[audit.apply(has_missing_existing_id, axis=1)].copy()
    review_needed = audit[
        audit["audit_action"].isin(
            [
                "candidate_for_review",
                "id_conflict_review_before_sql",
                "do_not_update_from_this_match",
            ]
        )
    ].copy()
    strong_name_id_mismatch = audit[
        (audit["name_location_match_status"] == "strong")
        & (
            (audit["epa_facility_id_matches_existing"] == False)
            | (audit["epa_frs_id_matches_existing"] == False)
        )
    ].copy()
    schema = pd.DataFrame(
        [
            {"table": CORN_TABLE, "role": role, "column": col or ""}
            for role, col in corn_cols.items()
        ]
        + [
            {"table": EPA_TABLE, "role": role, "column": col or ""}
            for role, col in epa_cols.items()
        ]
    )

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        review_needed.to_excel(writer, sheet_name="review_needed", index=False)
        id_conflicts.to_excel(writer, sheet_name="id_conflicts", index=False)
        missing_existing_ids.to_excel(writer, sheet_name="missing_existing_ids", index=False)
        strong_name_id_mismatch.to_excel(writer, sheet_name="strong_name_id_mismatch", index=False)
        zip_matches.to_excel(writer, sheet_name="zip_only_matches", index=False)
        audit.to_excel(writer, sheet_name="best_matches", index=False)
        candidates.to_excel(writer, sheet_name="top_5_candidates", index=False)
        schema.to_excel(writer, sheet_name="column_mapping", index=False)

    print(f"Wrote {OUT_XLSX}")
    print(audit["name_location_match_status"].value_counts(dropna=False).to_string())
    print()
    print(audit["audit_action"].value_counts(dropna=False).to_string())
    print()
    print(f"id_conflicts: {len(id_conflicts)}")
    print(f"missing_existing_ids: {len(missing_existing_ids)}")
    print(f"review_needed: {len(review_needed)}")
    print(f"zip_only_matches: {len(zip_matches)}")


if __name__ == "__main__":
    main()
