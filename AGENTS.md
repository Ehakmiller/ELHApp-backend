# ELHApp Backend - Agent Notes

Last audited: 2026-05-22

## Purpose

This repository is the static publishing and output repository for ELHApp-related ethanol market work. It supports consulting in the corn ethanol space by publishing EIA ethanol supply/stock/use charts, Iowa State University/CARD margin analytics, corn basis maps, LCFS/technology views, rail data, yield views, and small HTML pages that show the value of ethanol as a commodity.

Most business logic and data collection code is still outside this repository in the user's OneDrive Python workspace. This repo mainly stores deployable artifacts and a few repo-local helper scripts.

## Publishing Surface

- Treat `docs/` as the primary GitHub Pages publishing surface unless the user says otherwise.
- `docs/index.html` redirects to `docs/static_data/Ethanol_Corn_Basis/Current_Basis.html`.
- `docs/static_data/index.html` redirects to `docs/static_data/Ethanol_Corn_Basis/Current_Basis.html`.
- `docs/.nojekyll` is tracked and should be preserved for GitHub Pages.
- Root `index.html` and top-level `static_data/` appear to be older or alternate publishing paths. Do not assume they are canonical without checking with the user.

## Repository Layout

- `docs/static_data/EIA_Stock_Data`: published EIA ethanol production, consumption, total use, exports as percent of production, stocks use, and stocks waterfall PNG outputs.
- `docs/static_data/Ethanol_Gross_Margin`: published ethanol margin and lag heatmap PNG outputs.
- `docs/static_data/Stocks_Use`: stocks-use and margin forecast HTML/chart outputs, including revenue share charts.
- `docs/static_data/Ethanol_Forecast`: forecast-oriented HTML output, including seasonal stocks-use views.
- `docs/static_data/Ethanol_Corn_Basis`: current, 30-day, 365-day, and basis-change corn basis map outputs.
- `docs/static_data/LCFS` and `docs/static_data/LCFS_Score`: LCFS exports, dropdown JSON, maps, score outputs, spreadsheets, and analysis CSVs.
- `docs/static_data/Ethanol_Technology`: plant technology map outputs. The dataset is keyed by EPM facility identifier and is used as a join layer for plant technology, LCFS, capacity, feedstock, and rail attributes.
- `docs/static_data/Rail`: rail network GeoJSON and CO2/storage/pipeline-related map layers.
- `docs/static_data/Ethanol_Plant_Yield` and `docs/static_data/Yield`: annual ethanol yield and corn oil yield chart outputs.
- `docs/static_data/Picture Files`: published chart/image assets, including state basis images and watermark/logo files.
- `scripts/Basis`: repo-local basis map and basis-change scripts, but they depend heavily on external OneDrive scripts and databases.
- `scripts/update_current_basis.sh`: Cygwin/Git Bash helper for copying the newest external basis map into top-level `static_data`; likely legacy unless the user says to use it.
- `app/` and `docs/app/`: minimal Flask placeholders. They are not the active application surface.

## Canonical External Workflows

### EIA, Stocks Use, Margin, Forecast

Primary entry point:

`C:\Users\ehakm\OneDrive\Documents\Python Code\EIA Information\EIA Data Generation\EIA information down load.py`

This script orchestrates the weekly EIA/margin workflow. It imports helpers from:

`C:\Users\ehakm\OneDrive\Documents\Python Code\EIA Information\Forecast Models`

Important files in that folder include:

- `config.py`: central path/config file for the EIA pipeline.
- `eia_data_pull.py`: pulls weekly EIA API series for ethanol consumption, production, stocks, imports, and exports.
- `chart_pack.py`: writes EIA and margin charts to repo output folders.
- `workbook_builder.py`: builds the Excel workbook using legacy pivot scripts.
- `margin_merge.py`, `stocks_use_forecast.py`, `margin_forecast.py`: build forecast and margin/stocks-use datasets and HTML outputs.

The EIA workflow also runs the Iowa State University/CARD margin downloader:

`C:\Users\ehakm\OneDrive\Documents\Python Code\EIA Information\Margin Generator\ISU Margin Download update.py`

That downloader uses Selenium/Chrome to download historical margin CSV data from CARD/ISU and saves it under the user's OneDrive ethanol margin data folder. `Margin.py` then reads that CSV, combines it with yield assumptions, updates the main workbook, and writes weekly margin sheets.

Primary workbook output:

`C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\Ethanol Supply, Consumption & Stocks\Stocks Use Report Data\ethanol_data_with_ratios.xlsx`

Repo output folders used by the external EIA config:

- `static_data/EIA_Stock_Data`
- `docs/static_data/EIA_Stock_Data`
- `static_data/Ethanol_Gross_Margin`
- `docs/static_data/Ethanol_Gross_Margin`

Prefer committing the `docs/static_data/...` outputs. Do not add top-level `static_data/` unless the user explicitly asks.

### Corn Basis

Repo-local basis scripts live in `scripts/Basis`, but they depend on external files:

- Database: `C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db`
- Basis dataframe scripts under `C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Basis_dataframe`
- Helper scripts such as `Largest Movers basis.py` and `Map that shows the basis change.py` under `C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db`
- Watermark/image assets under the user's OneDrive folders.

Important repo-local scripts:

- `scripts/Basis/Contour Map 2025.py`: current nearby basis map generator.
- `scripts/Basis/Contour Map 30 day back.py`: 30-day comparison map generator.
- `scripts/Basis/Contour Map 365 day back.py`: 365-day comparison map generator.
- `scripts/Basis/Basis Change Map.py`: reads the SQLite database, calculates weekly/monthly basis deltas, writes an Excel summary, then executes external map/chart writers.
- `scripts/Basis/_fast_Master.py`: Selenium scraper runner that reuses one Chrome driver against scripts in the external `Ethanol db\scrape` folder.

Several basis scripts contain `DEPLOY_TO_GITHUB = True` or internal `git add` / `git commit` / `git push` automation. Do not run those scripts without confirming whether the user wants automatic commit/push behavior. When editing them, preserve the ability to run locally without deploying.

### Yield And Revenue Outputs

External generators exist under:

- `C:\Users\ehakm\OneDrive\Documents\Python Code\EIA Information\Yield Generators`
- `C:\Users\ehakm\OneDrive\Documents\Python Code\EIA Information\Revenue Percentage`

These appear to feed the tracked yield charts and stocks-use revenue share charts under `docs/static_data`.

### LCFS, Technology, Rail

Published LCFS, technology, and rail artifacts are tracked under `docs/static_data`, but the main generation scripts are not fully contained in this repo. Before changing schemas or filenames in these areas, trace the external generator first or ask the user which script is canonical.

## Environment

- Windows-first project. Many scripts use absolute Windows paths and have historically been run from Spyder or an Anaconda prompt.
- The EIA/ethanol workflow should run in the `ethanolq` Conda environment.
- Keep the numerical Python stack consistent. Avoid mixing pip-installed and conda-installed NumPy, SciPy, pandas, scikit-learn, matplotlib, and related packages unless there is a clear reason.
- Known-good stack after the May 2026 repair:
  - `numpy 1.26.4`
  - `pandas 2.3.3`
  - `scipy 1.13.1`
  - `scikit-learn 1.5.1`
  - `matplotlib 3.9.2`
- Selenium and Chrome are required for ISU/CARD margin downloads and basis scraper workflows. Some scripts use `webdriver_manager`.
- `requirements.txt`, `Procfile`, and `render.yaml` are effectively empty placeholders. Do not treat them as authoritative environment or deployment documentation.
- The Flask package in `app/` is incomplete: `create_app()` imports `main` from `routes.py`, but `routes.py` is empty. Do not assume there is a working backend server here.

## Editing And Generation Guidance

- Prefer changing generator scripts instead of hand-editing generated Folium HTML, PNGs, JSON, CSVs, or XLSX files.
- If a generated HTML file must be patched directly, document that it will be overwritten by the next pipeline run.
- Preserve existing absolute path behavior unless the user asks for portability. If adding new path logic, use `pathlib.Path` and keep Windows path compatibility.
- Be careful with scripts whose filenames contain spaces; keep current names unless the user asks for a cleanup.
- Some Python files contain mojibake from emoji/logging text. Avoid broad encoding churn unless the task is specifically to repair encoding.
- Generated HTML files can be large. Use targeted search/diff and `git diff --stat` rather than reading or displaying entire generated files.
- Do not copy external workbooks, SQLite databases, API keys, or local OneDrive datasets into the repo unless the user explicitly asks.
- Treat the EIA API key currently stored in the external config as a credential. Do not move it into this repository.

## Git Guidance

- Generated deployable files under `docs/static_data` are tracked and may be committed after running the data pipeline.
- As of this audit, `AGENTS.md`, top-level `static_data/`, and `anaconda_projects/` were untracked. Do not automatically add `static_data/` or `anaconda_projects/`.
- Always run `git status --short` before staging, and `git diff --stat` before committing generated outputs.
- Stage specific files. Avoid `git add .` because repo-local scripts and external pipeline runs can create untracked folders and snapshots.
- Do not run repo scripts that commit or push without explicit user approval.
- The remote is `https://github.com/Ehakmiller/ELHApp-backend.git`.

## Validation Checklist

For EIA/margin pipeline changes:

- Run from the `ethanolq` environment.
- Confirm the EIA API pull succeeds and the ISU/CARD CSV download is fresh.
- Confirm the main workbook was updated.
- Confirm expected PNG/HTML outputs were written under `docs/static_data/EIA_Stock_Data`, `docs/static_data/Ethanol_Gross_Margin`, `docs/static_data/Stocks_Use`, and/or `docs/static_data/Ethanol_Forecast`.
- Review `git diff --stat` before deciding what to commit.

For basis map changes:

- Confirm the source SQLite database and external basis dataframe scripts are reachable.
- Confirm generated HTML map files are nonempty and have current data/build dates.
- Check that `docs/index.html`, `docs/static_data/index.html`, and `docs/static_data/Ethanol_Corn_Basis/index.html` still point to the intended current map.
- If possible, open the generated HTML locally and verify tiles, markers, colorbar, layer control, and mobile/desktop layout.
- Confirm whether auto-deploy should be enabled before running scripts with `DEPLOY_TO_GITHUB = True`.

For static output-only updates:

- Verify file timestamps and output paths.
- Prefer checking image dimensions or HTML title/build stamp over reviewing binary diffs.
- Use `git diff --stat` to catch unexpected churn.

## Known Cleanup Items

- Document which external scripts are canonical and which are legacy.
- Move secrets/configuration such as the EIA API key out of script files if this workflow becomes more formal.
- Decide whether top-level `static_data/` is legacy or a supported alternate Pages path.
- Consider adding a `.gitignore` for local Anaconda artifacts and noncanonical generated folders.
- Fill in real `requirements.txt` or an `environment.yml` for `ethanolq`.
- Clarify whether `app/` should be removed, completed, or left as a placeholder.
- Fix obvious placeholder/typo files only when the user asks or when they block deployment, such as `README,MD`, empty top-level files, and `docs/static_data/Ethanol_Technology/index.hrml`.
a
