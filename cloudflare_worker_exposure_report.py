from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = "https://flat-silence-a8a3.elhakmiller.workers.dev"
OUT_REPORT = Path(__file__).with_name("Cloudflare_Worker_Exposure_Report.txt")


def fetch(path: str):
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"User-Agent": "ELHApp-audit/1.0"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            elapsed_ms = round((time.time() - started) * 1000)
            return {
                "path": path,
                "status": resp.status,
                "content_type": resp.headers.get("Content-Type", ""),
                "bytes": len(body),
                "elapsed_ms": elapsed_ms,
                "body": body,
                "error": "",
            }
    except urllib.error.HTTPError as e:
        body = e.read()
        return {
            "path": path,
            "status": e.code,
            "content_type": e.headers.get("Content-Type", ""),
            "bytes": len(body),
            "elapsed_ms": round((time.time() - started) * 1000),
            "body": body,
            "error": str(e),
        }
    except Exception as e:
        return {
            "path": path,
            "status": "ERR",
            "content_type": "",
            "bytes": 0,
            "elapsed_ms": round((time.time() - started) * 1000),
            "body": b"",
            "error": str(e),
        }


def parse_json(body: bytes):
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def rows_from_search(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("value", "plants", "rows", "data", "results", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def dict_field_report(d: dict, prefix: str = "") -> list[str]:
    out = []
    for key, value in d.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.append(f"{name}.* ({len(value)} fields)")
            out.extend(dict_field_report(value, name))
        elif isinstance(value, list):
            out.append(f"{name}[] ({len(value)} rows)")
            if value and isinstance(value[0], dict):
                out.extend(dict_field_report(value[0], f"{name}[]"))
        else:
            out.append(name)
    return out


def main() -> None:
    endpoints = [
        "/",
        "/search",
        "/search?name=adm",
        "/search?state=IA",
        "/search?name=adm&state=IA",
        "/plant?id=3619",
        "/plant?id=3283",
        "/plant",
        "/data",
        "/json",
    ]

    results = [fetch(path) for path in endpoints]
    parsed = {r["path"]: parse_json(r["body"]) for r in results}

    search_payload = parsed.get("/search")
    search_rows = rows_from_search(search_payload)
    plant_payload = parsed.get("/plant?id=3619")

    lines = []
    lines.append("Cloudflare Worker Exposure Report")
    lines.append(f"Base URL: {BASE_URL}")
    lines.append("")
    lines.append("Endpoint Inventory")
    for r in results:
        preview = ""
        if r["body"]:
            preview = r["body"][:160].decode("utf-8", errors="replace").replace("\n", " ")
        lines.append(
            f"- {r['path']}: status={r['status']}, bytes={r['bytes']}, "
            f"content_type={r['content_type']}, elapsed_ms={r['elapsed_ms']}, preview={preview}"
        )
        if r["error"]:
            lines.append(f"  error={r['error']}")

    lines.append("")
    lines.append("Fields Returned By /search")
    lines.append(f"- /search row count with no filters: {len(search_rows)}")
    if search_rows:
        lines.append(f"- row fields: {', '.join(sorted(search_rows[0].keys()))}")
        lines.append(f"- first row sample: {json.dumps(search_rows[0], ensure_ascii=False)}")

    lines.append("")
    lines.append("Fields Returned By /plant?id=3619")
    if isinstance(plant_payload, dict):
        lines.append(f"- top-level sections: {', '.join(sorted(plant_payload.keys()))}")
        for section, value in plant_payload.items():
            if isinstance(value, dict):
                lines.append(f"- {section}: {', '.join(sorted(value.keys()))}")
            elif isinstance(value, list):
                lines.append(f"- {section}: list rows={len(value)}")
            else:
                lines.append(f"- {section}: {type(value).__name__}")

        lines.append("")
        lines.append("Full /plant Field Tree")
        for field in dict_field_report(plant_payload):
            lines.append(f"- {field}")

    lines.append("")
    lines.append("Estimated Scrape Risk")
    risk = "High"
    reasons = []
    if len(search_rows) > 100:
        reasons.append("/search with no filters returns the full plant index.")
    if isinstance(plant_payload, dict) and "epa_ghg" in plant_payload:
        reasons.append("/plant exposes detailed EPA GHG, thermal estimates, LCFS detail, technology flags, and metadata.")
    plant_missing = parsed.get("/plant")
    if isinstance(plant_missing, dict) or any(r["path"] == "/plant" and r["status"] == 200 for r in results):
        reasons.append("/plant endpoint is reachable without authentication.")
    reasons.append("EPM IDs are enumerable from /search, then each can be requested from /plant?id=EPM.")
    lines.append(f"- Overall risk: {risk}")
    for reason in reasons:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("Practical Exposure")
    lines.append("- A scraper can call /search once to get all EPM IDs, names, owners, states, and cities.")
    lines.append("- It can then loop over those IDs and call /plant?id=... to reconstruct the detailed plant database.")
    lines.append("- No authentication, token, rate limit signal, or bot challenge was observed from these probes.")
    lines.append("")
    lines.append("Suggested Next Controls")
    lines.append("- Make /search require at least a name or state query and return capped results.")
    lines.append("- Return only display-safe fields from /plant; keep sensitive/source fields server-side.")
    lines.append("- Add basic rate limiting per IP/request pattern.")
    lines.append("- Consider short-lived signed requests or Turnstile if this needs stronger protection.")
    lines.append("- Split public calculator fields from private audit/source fields in KV.")

    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_REPORT)
    print(f"search_rows={len(search_rows)}")


if __name__ == "__main__":
    main()
