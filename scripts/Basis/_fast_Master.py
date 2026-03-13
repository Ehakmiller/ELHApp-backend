# -*- coding: utf-8 -*-
"""
_fast_master.py
Runs scrapers in ONE Python process and reuses ONE Chrome driver.

Conventions:
- New-style scrapers define: run(driver, ...)
- Legacy scripts (no run()) are sandbox-executed with webdriver.Chrome monkeypatched
  to the shared driver proxy.
"""

from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
import importlib.util
import inspect
import time
import traceback

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options


SCRAPE_DIR = Path(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\scrape")
OUTPUT_DIR = Path(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Error Log")
ERROR_LOG = OUTPUT_DIR / "error_log_fast.txt"

PATTERN = "*.py"
SKIP = {
    "__init__.py",
    "AAAscraper.py",
    "_fast_master.py",
    "corn_market.py",
    "ethanol_webdriver_setup.py",
}


def build_chrome(headless: bool = True):
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")

    # look less like Selenium
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # normal-ish browser identity
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )

    return options


class _SharedDriverProxy:
    """
    Wraps the real shared driver so legacy scripts can't accidentally quit it.
    """
    def __init__(self, real_driver):
        self._d = real_driver

    def __getattr__(self, name):
        if name in ("quit", "close"):
            return lambda *a, **k: None
        return getattr(self._d, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def monkeypatch_webdriver_chrome(shared_driver):
    """
    Temporarily patch selenium.webdriver.Chrome to return our shared driver proxy.
    """
    import selenium.webdriver as swd

    original_chrome = swd.Chrome
    proxy = _SharedDriverProxy(shared_driver)

    def _fake_chrome(*args, **kwargs):
        return proxy

    swd.Chrome = _fake_chrome
    try:
        yield
    finally:
        swd.Chrome = original_chrome


def log(msg: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def load_module_from_path(path: Path):
    """Import a .py file as a module."""
    mod_name = f"scrape_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def run_legacy_script(script_path: Path, shared_driver, ctx: dict) -> None:
    """
    Execute a legacy scraper file in a sandboxed globals dict, while monkeypatching
    webdriver.Chrome -> shared driver proxy.
    """
    code = script_path.read_text(encoding="utf-8", errors="replace")

    g = {
        "__file__": str(script_path),
        "__name__": f"legacy_{script_path.stem}",
        "ctx": ctx,
        "start_time": time.time(),
        "today": ctx["today"],
        # expose market data for legacy scripts that still expect globals
        "fut": ctx.get("fut"),
        "price_diffs": ctx.get("price_diffs"),
        "futures_data": ctx.get("futures_data"),
    }

    with monkeypatch_webdriver_chrome(shared_driver):
        exec(compile(code, str(script_path), "exec"), g, g)

def call_run(mod, driver, ctx):
    """
    Call mod.run(...) and pass only the arguments it actually supports.

    Returns:
        The scraper's actual return value, so the master can derive item counts.
    """
    fn = getattr(mod, "run", None)
    if fn is None or not callable(fn):
        return None

    sig = inspect.signature(fn)
    params = sig.parameters
    param_names = set(params.keys())

    kw = {}
    supported_kw = {
        "ctx": ctx,
        "options": ctx.get("options"),
        "timeout": ctx.get("timeout"),
        "today": ctx.get("today"),
        "fut": ctx.get("fut"),
        "price_diffs": ctx.get("price_diffs"),
        "futures_data": ctx.get("futures_data"),
        "debug": ctx.get("debug", False),
        "debug_dump_dir": ctx.get("debug_dump_dir"),
    }

    accepts_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

    for k, v in supported_kw.items():
        if accepts_varkw or k in param_names:
            kw[k] = v

    positional_params = [
        p for p in params.values()
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if positional_params:
        first_name = positional_params[0].name.lower()
        if first_name in {"driver", "d", "browser", "webdriver"}:
            return fn(driver, **kw)
        elif first_name == "ctx":
            kw_no_ctx = dict(kw)
            kw_no_ctx.pop("ctx", None)
            return fn(ctx, **kw_no_ctx)
        else:
            try:
                return fn(driver, **kw)
            except TypeError:
                return fn(**kw)
    else:
        return fn(**kw)


def normalize_item_count(return_value) -> int:
    """
    Convert a scraper return value into an item count.

    Rules:
    - int -> that exact count
    - None -> assume 1 successful item for legacy/single-site scrapers
    - sized containers -> len(...)
    - anything else -> 1
    """
    if return_value is None:
        return 1

    if isinstance(return_value, bool):
        return int(return_value)

    if isinstance(return_value, int):
        return return_value

    try:
        return len(return_value)
    except Exception:
        return 1


def prime_corn_market(driver, ctx: dict) -> None:
    """
    Run corn_market once and stash outputs in ctx so FAST scrapers can receive them.
    """
    import corn_market

    # Some versions expose run(driver), some may just populate globals on import.
    if hasattr(corn_market, "run") and callable(corn_market.run):
        try:
            corn_market.run(driver)
        except TypeError:
            corn_market.run()

    ctx["fut"] = getattr(corn_market, "fut", None)
    ctx["price_diffs"] = getattr(corn_market, "price_diffs", None)
    ctx["futures_data"] = getattr(corn_market, "futures_data", None)

    if ctx["fut"] is None or ctx["price_diffs"] is None:
        raise RuntimeError(
            "corn_market did not populate fut and price_diffs. "
            f"Found fut={ctx['fut']!r}, price_diffs={ctx['price_diffs']!r}"
        )


def main() -> int:
    scripts = sorted(p for p in SCRAPE_DIR.glob(PATTERN) if p.name not in SKIP)

    log("=" * 100)
    log(f"FAST RUN START | SCRAPE_DIR={SCRAPE_DIR} | scripts={len(scripts)}")
    log("=" * 100)

    print(f"FAST: Found {len(scripts)} scripts in {SCRAPE_DIR}")

    options = build_chrome(headless=True)

    ctx = {
        "SCRAPE_DIR": str(SCRAPE_DIR),
        "ERROR_LOG": str(ERROR_LOG),
        "run_started_at": datetime.now().isoformat(timespec="seconds"),
        "today": datetime.now().strftime("%m%d%y"),
        "options": options,
        "timeout": 12,
        "debug": False,
        "debug_dump_dir": str(OUTPUT_DIR / "debug_dumps"),
        "fut": None,
        "price_diffs": None,
        "futures_data": None,
    }

    failures = 0
    legacy_ran = 0
    run_ran = 0

    total_items = 0
    total_seconds = 0.0
    ok_scripts = 0

    with webdriver.Chrome(options=options) as driver:
        # Prime corn market ONCE
        try:
            print("\nPriming corn_market once for shared futures data...")
            prime_corn_market(driver, ctx)
            print("corn_market ready.")
            log("corn_market primed successfully.")
        except Exception:
            log("FAILED during corn_market priming")
            log("TRACEBACK:\n" + traceback.format_exc())
            log("-" * 100)
            raise

        for script in scripts:
            print("\n" + "=" * 80)
            print(f"FAST RUNNING: {script.name}")
            print("=" * 80)

            t0 = time.time()

            try:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

                try:
                    driver.delete_all_cookies()
                except WebDriverException:
                    pass

                mod = load_module_from_path(script)
                
                if hasattr(mod, "run") and callable(mod.run):
                    return_value = call_run(mod, driver, ctx)
                    item_count = normalize_item_count(return_value)
                    run_ran += 1
                else:
                    run_legacy_script(script, driver, ctx)
                    return_value = None
                    item_count = 1
                    legacy_ran += 1

                dt = time.time() - t0
                avg_sec_per_item = (dt / item_count) if item_count > 0 else 0.0

                ok_scripts += 1
                total_items += item_count
                total_seconds += dt

                print(
                    f"✅ OK: {script.name} | {dt:.2f}s | "
                    f"count={item_count} | avg={avg_sec_per_item:.2f}s/item"
                )
                log(
                    f"OK: {script.name} | {dt:.2f}s | "
                    f"count={item_count} | avg={avg_sec_per_item:.2f}s/item"
                )

            except Exception:

                failures += 1
                dt = time.time() - t0
                total_seconds += dt
            
                print(f"❌ FAILED: {script.name} | {dt:.2f}s | count=0")
            
                log(f"FAILED: {script.name} | {dt:.2f}s | count=0")
                log("TRACEBACK:\n" + traceback.format_exc())
                log("-" * 100)

        overall_avg = (total_seconds / total_items) if total_items > 0 else 0.0

        log(
            f"FAST RUN END | failures={failures} / total={len(scripts)} | "
            f"ok={ok_scripts} | run()={run_ran} | legacy={legacy_ran} | "
            f"total_items={total_items} | total_seconds={total_seconds:.2f} | "
            f"avg={overall_avg:.2f}s/item"
        )
        log("=" * 100)

    print("\n" + "-" * 80)
    print(
        f"FAST DONE. Failures: {failures} / {len(scripts)} | "
        f"ok={ok_scripts} | run()={run_ran} | legacy={legacy_ran} | "
        f"total_items={total_items} | total_seconds={total_seconds:.2f} | "
        f"avg={overall_avg:.2f}s/item"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())