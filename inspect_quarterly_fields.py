import json
from pathlib import Path


P = Path(r"C:\Users\ehakm\OneDrive\Documents\Ethanol Quarterly Data\Data Files\quarterly_master_current.json")


def walk(d, prefix="", depth=0, max_depth=3):
    if depth > max_depth:
        return []
    if isinstance(d, dict):
        out = []
        for k, v in d.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                out.append((p, type(v).__name__, len(v)))
                out.extend(walk(v, p, depth + 1, max_depth))
            else:
                out.append((p, type(v).__name__, v))
        return out
    if isinstance(d, list):
        out = [(prefix, "list", len(d))]
        if d and isinstance(d[0], dict):
            out.extend(walk(d[0], prefix + "[]", depth + 1, max_depth))
        return out
    return [(prefix, type(d).__name__, d)]


def main():
    data = json.load(open(P, encoding="utf-8"))
    for co, cv in data.items():
        print("\n===", co, "===")
        print("business_profile")
        for p, t, v in walk(cv.get("business_profile", {}), max_depth=3)[:120]:
            print(p, "=>", t, v)
        periods = cv.get("periods", {})
        for period in ["2026 Q1", "2025 FY", "2025 Q4", "2025 Q3"]:
            if period not in periods:
                continue
            rec = periods[period]
            print("\nPERIOD", period)
            for section in ["costs", "operations", "operating_metrics", "financials", "derived_metrics"]:
                print("SECTION", section)
                rows = walk(rec.get(section, {}), max_depth=3)
                for p, t, v in rows[:160]:
                    print(p, "=>", t, v)
            break


if __name__ == "__main__":
    main()
