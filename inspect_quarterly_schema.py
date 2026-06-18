import json
from pathlib import Path


P = Path(r"C:\Users\ehakm\OneDrive\Documents\Ethanol Quarterly Data\Data Files\quarterly_master_current.json")


def main():
    data = json.load(open(P, encoding="utf-8"))
    print("top type", type(data).__name__)
    for co, cv in data.items():
        print("\nCOMPANY", co, "type", type(cv).__name__)
        if not isinstance(cv, dict):
            continue
        print("keys", list(cv.keys())[:60])
        for candidate in ["periods", "quarters", "data", "quarterly", "records", "history"]:
            periods = cv.get(candidate)
            if isinstance(periods, dict):
                print("period container", candidate, "count", len(periods), "sample", list(periods.keys())[:8])
                sample = next(iter(periods.values())) if periods else {}
                print("sample keys", list(sample.keys())[:120] if isinstance(sample, dict) else type(sample).__name__)
            elif isinstance(periods, list):
                print("period container", candidate, "list count", len(periods))
                if periods and isinstance(periods[0], dict):
                    print("sample keys", list(periods[0].keys())[:120])


if __name__ == "__main__":
    main()
