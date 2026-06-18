import requests


BASE = "https://flat-silence-a8a3.elhakmiller.workers.dev"


def num(value):
    try:
        return float(value)
    except Exception:
        return None


def main():
    rows = requests.get(f"{BASE}/search", timeout=20).json()
    ca = []
    fiber = []
    eligible = []
    for row in rows:
        epm = row.get("epm")
        plant = requests.get(f"{BASE}/plant", params={"id": epm}, timeout=20).json()
        ci = plant.get("ci_summary", {}) or {}
        fs = ci.get("ci_by_feedstock", {}) or {}
        ca_ci = ci.get("ci_lcfs_delivered_g_per_mj")
        corn = fs.get("ci_corn_g_per_mj")
        fib = fs.get("ci_fiber_g_per_mj")
        item = (epm, row.get("plant_name"), ca_ci, corn, fib)
        if num(ca_ci) is not None:
            ca.append(item)
        if num(fib) is not None:
            fiber.append(item)
        if num(ca_ci) is not None and num(corn) is not None and num(fib) is not None:
            eligible.append(item)

    print("rows", len(rows))
    print("ca_ci", len(ca))
    print("fiber", len(fiber))
    print("ckf_eligible", len(eligible))
    print("eligible sample")
    for item in eligible[:20]:
        print(item)
    print("fiber sample")
    for item in fiber[:20]:
        print(item)


if __name__ == "__main__":
    main()
