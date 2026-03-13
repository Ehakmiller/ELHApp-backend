# -*- coding: utf-8 -*-
import base64
from datetime import date

import folium
import geojsoncontour
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from branca.colormap import LinearColormap
from folium import FeatureGroup
from matplotlib.colors import LinearSegmentedColormap, rgb2hex
from scipy.interpolate import griddata
from branca.element import Element
from pathlib import Path
import subprocess
from datetime import datetime
import shutil
import os



# ==========================
# DEPLOY / DEV SWITCHES
# ==========================
DEPLOY_TO_GITHUB = True   # <-- set True when you want to push to GitHub
WRITE_TO_REPO    = True    # <-- keep True so files land in the repo for local preview

SHOW_MARKET_WATERMARK   = False
SHOW_PERSONAL_WATERMARK = True

# Optional: let an environment variable override (so you don’t edit code)
# In CMD:  set DEPLOY_GITHUB=1
# In PS:   $env:DEPLOY_GITHUB="1"

if os.getenv("DEPLOY_GITHUB", "").strip() == "1":
    DEPLOY_TO_GITHUB = True


# --- Load your prepared dataframe(s) (expects corn_df, selected optionally) ---
exec(open(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Basis_dataframe\Basis_df30day.py",
          'r', encoding='utf-8').read())

#____________________

#Helper for phone script
#____________________

def apply_mobile_theme(m: folium.Map) -> None:
    root = m.get_root()

    viewport_meta = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
"""

    cache_bust_block = """
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
<meta http-equiv="Pragma" content="no-cache" />
<meta http-equiv="Expires" content="0" />
"""

    # =========================
    # 1) SHARED / BASE CSS
    # =========================
    css_shared = r"""
<style>
  /* ===== Base layout ===== */
  html, body { height:100%; width:100%; margin:0; padding:0; }
  .folium-map, div[id^="map_"] { height:100vh !important; width:100vw !important; }

  :root{
    --safe-top: env(safe-area-inset-top, 0px);
    --title-top: 10px;
    --title-block: 60px;     /* reserved space for title */
    --left-pad: 12px;        /* MAIN “move left/right” knob */
    --gap: 8px;
    --market-width: 350px;
    --market-img-width: 350px;
    --layers-left: calc(var(--left-pad) + 50px);
    --colorbar-left: calc(var(--left-pad) - 15px);
    --market-top: calc(var(--safe-top) + var(--title-block) + 150px);
    --legend-top: calc(var(--safe-top) + var(--title-block) + 80px);
  }

  /* ===== Card styling ===== */
  .map-card{
    position: fixed;
    z-index: 9999;
    background: rgba(255,255,255,0.85);
    backdrop-filter: blur(6px);
    border-radius: 14px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.18);
    border: 1px solid rgba(0,0,0,0.08);
    padding: 10px 12px;
    font-family: Arial, sans-serif;
    box-sizing: border-box;
  }

  /* ===== Title ===== */
  .map-title{
    top: var(--title-top);
    left: 50%;
    transform: translateX(-50%);
    max-width: min(92vw, 520px);
    text-align: center;
  }
  .map-title h3{ margin:0; font-size:18px; line-height:1.15; }

  /* ===== Branca colorbar ===== */
  .legend,
  .legend.leaflet-control,
  .leaflet-control.legend{
    position: fixed !important;
    top: calc(var(--safe-top) + var(--title-block) + var(--gap) + 25px) !important;
    left: var(--colorbar-left) !important;
    right: auto !important;
    margin: 0 !important;
    transform: none !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    z-index: 12000 !important;
    pointer-events: none !important; /* don't steal taps/clicks */
  }
  .legend *{ border:none !important; box-shadow:none !important; }

  /* ===== Layer control ===== */
  .leaflet-control-layers.leaflet-control{
    position: fixed !important;
    top: calc(var(--safe-top) + var(--title-block) - 50px) !important;
    left: var(--layers-left) !important;
    right: auto !important;
    margin: 0 !important;
    z-index: 25000 !important;
  }
  .leaflet-control-layers-toggle{ width:44px !important; height:44px !important; }

  /* Label under the layer toggle */
  .leaflet-control-layers-toggle{
    position: relative !important;
    overflow: visible !important;
  }
  .leaflet-control-layers-toggle .layer-ctl-label{
    position:absolute;
    top: 50px;
    left: 50%;
    transform: translateX(-50%);
    text-align:center;
    line-height:1.05;
    background: rgba(255,255,255,0.85);
    border: 1px solid rgba(0,0,0,0.12);
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 6px;
    font-weight: 800;
    white-space: nowrap;
    color: #000 !important;
    font-family: "Space Grotesk", Arial, sans-serif !important;
    z-index: 30000!important;
    pointer-events:none;
  }
  .leaflet-control-layers.leaflet-control.leaflet-control-layers-expanded{ z-index: 25001 !important; }
  .leaflet-control-layers .leaflet-control-layers-list{
    position: relative !important;
    z-index: 25002 !important;
  }

  /* Prevent clipping of expanded panel */
  .leaflet-top.leaflet-left,
  .leaflet-top.leaflet-left .leaflet-control{
    overflow: visible !important;
  }

  /* ===== Your custom legend card ===== */
  .map-legend{
    position: fixed;
    top: var(--legend-top);
    left: var(--left-pad);
    right: auto;
    width: var(--market-width);
    font-size: 12px;
  }

  /* ===== Market watermark ===== */
  .market-watermark{
    position: fixed;
    top: var(--market-top);
    left: var(--left-pad);
    right: auto !important;
    z-index: 9999;
    padding: 0 !important;
  }
  .market-watermark img{ width: var(--market-img-width); height:auto; opacity:0.85; }

  /* ===== Personal watermark ===== */
  .personal-watermark{
    position: fixed;
    bottom: 1px;
    right: 45px;
    z-index: 9999;
  }
  .personal-watermark img{ width:200px; height:auto; }

  /* ===== City labels ===== */
  .leaflet-div-icon.city-label-icon{
    pointer-events:none !important;
    background:transparent !important;
    border:none !important;
  }

  /* Corner paint order: keep TOP-LEFT above TOP-RIGHT */
  .leaflet-top.leaflet-left{ z-index: 90000 !important; }
  .leaflet-top.leaflet-right{ z-index: 10000 !important; }
  .leaflet-bottom.leaflet-left,
  .leaflet-bottom.leaflet-right{ z-index: 8000 !important; }
</style>
"""

     # =========================
    # 2) DESKTOP-ONLY OVERRIDES
    # =========================
    css_desktop = r"""<style media="(hover: hover) and (pointer: fine)">
:root{
  --title-block: 60px;
  --left-pad: 12px;

  --market-width: 350px;
  --market-img-width: 350px;

  --layers-left: calc(var(--left-pad) + 50px);
  --colorbar-left: calc(var(--left-pad) - 15px);

  --market-top: calc(var(--safe-top) + var(--title-block) + 150px);
  --legend-top: calc(var(--safe-top) + var(--title-block) + 80px);
}

/* Desktop: fixed width legend (never full width) */
.map-legend{
  width: var(--market-width) !important;
  max-width: var(--market-width) !important;
  left: var(--left-pad) !important;
  right: auto !important;
  top: var(--legend-top) !important;
  bottom: auto !important;
}
</style>"""

    # =========================
    # 3) PHONE-ONLY OVERRIDES
    # =========================
    css_phone = r"""
<style media="(hover: none) and (pointer: coarse)">
  :root{
    --title-block: 72px;
    --left-pad: 10px;

    --market-width: 250px;
    --market-img-width: 250px;

    --layers-top: calc(var(--safe-top) + var(--title-top) + 6px);
    --colorbar-top: calc(var(--safe-top) + var(--title-top) + 40px);
    --market-top: calc(var(--colorbar-top) + 50px);

    --legend-bottom: 40px;
  }

  .map-title{
    padding: 6px 10px !important;
    padding-right: 56px !important;
    max-width: calc(100vw - 70px) !important;
  }
  .map-title h3{
    font-size: 13px !important;
    line-height: 1.05 !important;
  }

  /* Layer control: RIGHT of title */
  .leaflet-control-layers.leaflet-control{
    top: var(--layers-top) !important;
    right: 10px !important;
    left: auto !important;
    transform: none !important;
    z-index: 25000 !important;
  }
  .leaflet-control-layers.leaflet-control.leaflet-control-layers-expanded{
    right: 10px !important;
    left: auto !important;
  }

  /* Colorbar under title */
  .legend,
  .legend.leaflet-control,
  .leaflet-control.legend{
  top: calc(var(--colorbar-top) + 8px) !important;  /* <- drop it a bit */
  left: calc(var(--left-pad) - 10px) !important;
  right: auto !important;
  transform: none !important;
  z-index: 12000 !important;
  pointer-events: none !important;
}

  /* Market watermark under colorbar */
  .market-watermark{
    top: var(--market-top) !important;
    left: var(--left-pad) !important;
    right: auto !important;
  }
  .market-watermark img{
    width: var(--market-img-width) !important;
    height: auto !important;
  }

  /* Bottom watermark to LEFT */
.personal-watermark{
  bottom: 3px !important;
  left: 8px !important;
  right: auto !important;
}
.personal-watermark img{
  width: 120px !important;
  height: auto !important;
}


  /* Legend card — portrait default */
  .map-legend{
    bottom: var(--legend-bottom) !important;
    top: auto !important;
    left: 10px !important;
    right: 10px !important;
    width: auto !important;
    max-width: 92vw !important;
    max-height: 26vh !important;
    overflow-y: auto !important;
  }

  /* Legend card — landscape: fixed-width card */
  @media (orientation: landscape){
    .map-legend{
      left: 10px !important;
      right: auto !important;
      width: 320px !important;
      max-width: 350px !important;
      max-height: 38vh !important;
      overflow-y: auto !important;
    }
  }

  /* Disable hover tooltips on phones */
  .leaflet-tooltip{ display:none !important; }
</style>
"""

    # ✅ ONE injection point (and ONLY one)
    header_html = viewport_meta + cache_bust_block + css_shared + css_desktop + css_phone
    root.header.add_child(Element(header_html))




def add_build_stamp(m: folium.Map) -> str:
    """Add an HTML comment BUILD_STAMP to the map root and print it. Returns the stamp."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    m.get_root().html.add_child(folium.Element(f"<!-- BUILD_STAMP: {stamp} -->"))
    print("BUILD_STAMP:", stamp)
    return stamp



def _is_real_number(x) -> bool:
    
    if x is None:
        return False
    try:
        v = float(x)
    except Exception:
        return False
    return np.isfinite(v)

def add_optional_line(lines, label, value, *, fmt="{:.2f}", suffix=""):
    """Append a <br>-terminated line only if value is a real number."""
    if _is_real_number(value):
        lines.append(f"<b>{label}</b> {fmt.format(float(value))}{suffix}<br>")

def encode_image(path: str) -> str:
    if not os.path.exists(path):
        print(f"⚠️ image not found: {path}")
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# Source dataframe
corn = corn_df.copy()

today  = date.today().strftime("%m%d%y")
today2 = date.today().strftime("%m/%d/%y")


basis_dt = pd.to_datetime(corn["Basis_Date"], errors="coerce").max()
selected = basis_dt.strftime("%m/%d/%y") if pd.notna(basis_dt) else today2

corn['EPM'] = corn['EPM'].astype(str)
corn['Adj_Basis'] = corn['Adj_Basis'].astype('object').fillna("No Basis")

# Force Purefield to "No Basis"
#corn.loc[corn['Ownership'] == 'Purefield', 'Adj_Basis'] = 'No Basis'

#corn = corn[corn['State']=='WI']

# Shutdown & Startup flags
shutdown_epm_numbers = ['3259', '3278', '3281', '3282', '3284', '3285', '3552', '3615',
                        '3624', '3658', '3696', '8888', 'SD-02', 'SD-07', 'SD-09',
                        'SD-12', 'SD-15', 'SD-16', '3757']
startup_epm_numbers = ['3758']

Valero_epm_numbers= ['3721','3722','3723','3724','3725','3726','3727','3728','3729','3730','3731','3733'
]

#special = ['3614','3615','3616','3617','3619','3620','3621','3622','3623','3708']
#corn = corn[corn['EPM'].astype(str).isin(special)]

corn.loc[corn['EPM'].isin(shutdown_epm_numbers), 'Adj_Basis'] = 'Shut Down'
corn.loc[corn['EPM'].isin(startup_epm_numbers), 'Adj_Basis'] = 'Startup'
corn.loc[corn['EPM'].isin(Valero_epm_numbers), 'Adj_Basis'] = 'Valero'

today = date.today().strftime("%m%d%y")
today2 = date.today().strftime("%m/%d/%y")


# Basic cleaning
corn['State'] = corn['State'].astype(str).str.strip()

# Split rows by numeric vs non-numeric basis
adj_num = pd.to_numeric(corn["Adj_Basis"], errors="coerce")
is_num = adj_num.notna()

numeric_rows = corn[is_num].copy()
nonnumeric_rows = corn[~is_num].copy()

numeric_rows["Adj_Basis"] = adj_num[is_num].astype(float)


no_basis_rows  = nonnumeric_rows[nonnumeric_rows['Adj_Basis'] == 'No Basis'].copy()
shut_down_rows = nonnumeric_rows[nonnumeric_rows['Adj_Basis'] == 'Shut Down'].copy()
startup_rows   = nonnumeric_rows[nonnumeric_rows['Adj_Basis'] == 'Startup'].copy()
valero_rows   = nonnumeric_rows[nonnumeric_rows['Adj_Basis'] == 'Valero'].copy()

# Ensure numeric dtype for interpolation & colors
#numeric_rows['Adj_Basis'] = pd.to_numeric(numeric_rows['Adj_Basis'], errors='coerce')


# ====================
# Interpolated contours
# ====================
# Extract numeric basis for interpolation
# (Replace your whole if/else block with THIS)

# Always clean Lat/Lon so the map can't break
numeric_rows = numeric_rows.dropna(subset=["Latitude", "Longitude"]).copy()

# Shared colormap setup (used for both contour + marker colors)
colors = ["blue", "lightblue", "lightgreen", "yellow", "orange", "red"]
cmap = LinearSegmentedColormap.from_list("my_colormap", colors, N=20)

# Decide if we can interpolate
can_interpolate = (len(numeric_rows) >= 3)

if can_interpolate:
    Y = numeric_rows["Latitude"].to_numpy(float)
    X = numeric_rows["Longitude"].to_numpy(float)
    Z = numeric_rows["Adj_Basis"].to_numpy(float)

    # Interpolation grid
    grid_lats = np.linspace(float(np.min(Y)), float(np.max(Y)), 121)
    grid_lons = np.linspace(float(np.min(X)), float(np.max(X)), 121)
    X_grid, Y_grid = np.meshgrid(grid_lons, grid_lats)

    points = np.column_stack((X, Y))
    Z_grid = griddata(points, Z, (X_grid, Y_grid), method="linear")
    Z_grid_ma = np.ma.masked_invalid(Z_grid)

    # Map centered on data
    m = folium.Map(location=[float(np.mean(Y)), float(np.mean(X))], zoom_start=6)
    apply_mobile_theme(m)

    # --- BUILD STAMP (debug) ---
    add_build_stamp(m)
    # ---------------------------


    # Contour GeoJSON (skip if interpolation totally failed)
    if np.ma.count(Z_grid_ma) > 0:
        plt.figure()
        contour_filled = plt.contourf(X_grid, Y_grid, Z_grid_ma, levels=10, cmap=cmap)
        plt.close()

        geojson_filled = geojsoncontour.contourf_to_geojson(
            contourf=contour_filled,
            min_angle_deg=3.0,
            ndigits=3,
            stroke_width=0,
            fill_opacity=0.8
        )

        folium.GeoJson(
            geojson_filled,
            name="Basis Contour Layers",
            style_function=lambda x: {
                "color": x["properties"]["stroke"],
                "weight": 0,
                "fillColor": x["properties"].get("fill", None),
                "fillOpacity": 0.4
            }
        ).add_to(m)

else:
    # Not enough points for interpolation; still make a map (center over all plants)
    center_lat = float(corn["Latitude"].dropna().mean())
    center_lon = float(corn["Longitude"].dropna().mean())
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6)
    apply_mobile_theme(m)

    # --- BUILD STAMP (debug) ---
    add_build_stamp(m)
    # ---------------------------

   

    # Z exists for later safe_color() even if numeric_rows is empty
    if len(numeric_rows):
        Z = numeric_rows["Adj_Basis"].to_numpy(float)
    else:
        Z = np.array([0.0], dtype=float)

# ---- Colorbar (ALWAYS) ----
Zmin, Zmax = float(np.nanmin(Z)), float(np.nanmax(Z))
if not np.isfinite(Zmin) or not np.isfinite(Zmax) or Zmin == Zmax:
    # protect against all-NaN or constant arrays
    Zmin, Zmax = -0.50, 0.50

colormap = LinearColormap(colors=colors, vmin=Zmin, vmax=Zmax, caption="Adj_Basis")
colormap.width = 400
colormap.height = 40
m.add_child(colormap)




# ---- Currency tick formatting (ALWAYS) ----
currency_ticks_js = folium.Element("""
<script>
(function(){
  function formatTicks(){
    document
      .querySelectorAll('.legend svg g.tick text')
      .forEach(function(t){
        var raw = (t.textContent || "").trim();
        if(!raw) return;

        // Don't double-format
        if(raw.startsWith("$")) return;

        // Handle unicode minus + commas
        var cleaned = raw.replace(/\\u2212/g, "-").replace(/,/g, "").trim();
        var v = Number(cleaned);

        if(Number.isFinite(v)){
          t.textContent = "$" + v.toFixed(2);
        }
      });
  }

  function waitForLegend(){
    var svg = document.querySelector('.legend.leaflet-control svg');
    if(svg){
      formatTicks();
      var obs = new MutationObserver(function(){ formatTicks(); });
      obs.observe(svg, {subtree:true, childList:true, characterData:true});
    } else {
      setTimeout(waitForLegend, 100);
    }
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", waitForLegend);
  } else {
    waitForLegend();
  }
})();
</script>
""")
m.get_root().html.add_child(currency_ticks_js)

    


# ====================
# Helpers
# ====================


  # you can put this at the very top with your other imports


    
    


def format_special_tech(row: pd.Series) -> str:
    special_tech_columns = ['High Pro', 'CHP', 'White Fox', 'ICM P10', 'DCO Enhancement']
    present = [col for col in special_tech_columns if pd.notna(row.get(col))]
    return "<br><b>Special Technologies:</b> " + ", ".join(present) if present else "<br><b>Special Technologies:</b> None"



def safe_color(val: float) -> str:
    # normalize val in [Zmin, Zmax]
    den = (Zmax - Zmin) if (Zmax - Zmin) != 0 else 1.0
    norm = max(0.0, min(1.0, (float(val) - Zmin) / den))
    return rgb2hex(cmap(norm))

# ====================
# Layers
# ====================
label_layer = FeatureGroup(name="City/Basis Labels", show=False)  # OFF by default
numeric_basis_layer = FeatureGroup(name="Basis Facilities")
no_basis_layer      = FeatureGroup(name="No Basis Facilities")
shut_down_layer     = FeatureGroup(name="Shut Down Facilities")
startup_layer       = FeatureGroup(name="Startup Facilities")
valero_layer       = FeatureGroup(name="Valero Facilities")

for fg in (numeric_basis_layer, no_basis_layer, shut_down_layer, startup_layer, valero_layer, label_layer):
    fg.add_to(m)

folium.LayerControl(collapsed=True, position="topleft").add_to(m)

layer_control_label_js = folium.Element("""
<script>
(function(){
  function addLabel(){
    var toggle = document.querySelector('.leaflet-control-layers-toggle');
    if(!toggle){ setTimeout(addLabel, 100); return; }

    // prevent duplicates
    if(toggle.querySelector('.layer-ctl-label')) return;

    var d = document.createElement('div');
    d.className = 'layer-ctl-label';
    d.innerHTML = '<div>Layer Control</div><div>(Click)</div>';  // <-- 2 lines
    toggle.appendChild(d);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", addLabel);
  } else {
    addLabel();
  }
})();
</script>
""")
m.get_root().html.add_child(layer_control_label_js)


# --- Desktop default: turn ON City/Basis labels only for desktop screens ---
desktop_default_labels_js = folium.Element(f"""
<script>
(function() {{
  function syncCityLabels() {{
    var map = {m.get_name()};
    var labels = {label_layer.get_name()};
    if(!map || !labels) return;

    // Match your CSS breakpoint: phone is <= 768px
    var desktop = window.matchMedia("(min-width: 769px)").matches;

    if(desktop) {{
      if(!map.hasLayer(labels)) map.addLayer(labels);
    }} else {{
      if(map.hasLayer(labels)) map.removeLayer(labels);
    }}
  }}

  // run once after render
  setTimeout(syncCityLabels, 0);

  // keep correct if someone rotates/resizes
  window.addEventListener("resize", function() {{
    clearTimeout(window.__cityLblTimer);
    window.__cityLblTimer = setTimeout(syncCityLabels, 150);
  }});
}})();
</script>
""")
m.get_root().html.add_child(desktop_default_labels_js)



# ====================
# Tooltips + markers (numeric)
# ====================
# Pick the correct name column after merges
# Pick the correct name column ONCE (after merges) and reuse everywhere
def pick_name_col(df: pd.DataFrame) -> str:
    for c in ("Name_proc", "Name_x", "Name_basis", "Name"):
        if c in df.columns:
            return c
    return "Name"

NAME_COL = pick_name_col(corn)

# Ensure the chosen column exists so later selections never crash
if NAME_COL not in corn.columns:
    corn[NAME_COL] = ""


# Only rows with numeric basis for colored bubbles
if not numeric_rows.empty:
    # ensure dtype
    numeric_rows['Adj_Basis'] = numeric_rows['Adj_Basis'].astype(float)

    for row in numeric_rows.to_dict("records"):
        lat = row.get("Latitude")
        lon = row.get("Longitude")
        if pd.isna(lat) or pd.isna(lon):
            continue

        adj = float(row.get("Adj_Basis"))
        fill_color = safe_color(adj)


        
        lat, lon = float(lat), float(lon)
        special_tech_info = format_special_tech(pd.Series(row))  # keeps your helper working


        # build tooltip HTML (no NaNs)
        lines = []
        lines.append(f"<b>Name:</b> {row.get(NAME_COL, '')}<br>")
        lines.append(f"<b>Ownership Group:</b> {row.get('Ownership', '')}<br>")
        
        lcfs_lines = []
        add_optional_line(lcfs_lines, "LCFS Score (DDGS):",  row.get("CI_DDGS"), fmt="{:.1f}")
        add_optional_line(lcfs_lines, "LCFS Score (MDGS):",  row.get("CI_MDGS"), fmt="{:.1f}")
        add_optional_line(lcfs_lines, "LCFS Score (Wet):",   row.get("CI_WDGS"), fmt="{:.1f}")
        add_optional_line(lcfs_lines, "LCFS Score (Fiber):", row.get("CI_Fiber"), fmt="{:.1f}")
        
        if lcfs_lines:
            lines.append("<br><b>LCFS Scores</b><br>")
            lines.extend(lcfs_lines)
        
        lines.append("<br>")
        lines.append(f"<b>Ethanol Prod:</b> {row.get('Ethanol Capacity', 'N/A')} M gals<br>")
        lines.append(f"<b>Plant Design:</b> {row.get('Technology', '')} {special_tech_info}<br>")
        lines.append(f"<b>Rail Lines:</b> {row.get('Rail Lines', '')}")
        
        tooltip = "".join(lines)
        pop = folium.Popup(tooltip, max_width=320)
        
        # Popup only (tap/click). Tooltips intentionally not used.


        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            color="black",
            fill=True,
            fill_color=fill_color,
            fill_opacity=1,
            popup=pop,          # <-- popup only
        ).add_to(numeric_basis_layer)



        
        folium.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(
            class_name="city-label-icon",   # <--- add this
            icon_size=(150, 36),
            icon_anchor=(7, 28),
            html=(
                f"<div class='city-label' style='font-size: 8pt; color: black; "
                f"font-weight: bold; font-family: Arial;'>"
                f"{row.get('City','')}: {adj:.2f}</div>"
            )
        ),
        interactive=False,  # <--- IMPORTANT
    ).add_to(label_layer)



# ====================
# Markers for No Basis / Shut Down / Startup
# ====================
def add_status_markers(df: pd.DataFrame, layer: FeatureGroup, label: str, border: str, fill: str):
    """
    Adds markers for non-numeric status rows (No Basis / Shut Down / Startup / Valero).
    Uses POPUP ONLY (prevents double-bubble on phones).
    Also adds the city/status label to label_layer (non-interactive so it doesn't steal taps).
    """
    for _, row in df.iterrows():
        if pd.isna(row.get("Latitude")) or pd.isna(row.get("Longitude")):
            continue

        lat, lon = float(row["Latitude"]), float(row["Longitude"])
        special_tech_info = format_special_tech(row)

        # Build HTML FIRST
        lines = []
        lines.append(f"<b>Name:</b> {row.get(NAME_COL, '')}<br>")
        lines.append(f"<b>Ownership Group:</b> {row.get('Ownership', '')}<br><br>")
        lines.append(f"<b>Status:</b> {label}<br>")
        lines.append(f"<b>Ethanol Prod:</b> {row.get('Ethanol Capacity', 'N/A')} M gals<br>")
        lines.append(f"<b>Plant Design:</b> {row.get('Technology', '')} {special_tech_info}<br>")
        lines.append(f"<b>Rail Lines:</b> {row.get('Rail Lines', '')}")

        popup_html = "".join(lines)                 # <-- assigned here
        pop = folium.Popup(popup_html, max_width=320)

        # Marker (POPUP ONLY)
        if label == "Valero":
            folium.Marker(
                location=[lat, lon],
                popup=pop,
                icon=folium.DivIcon(
                    class_name="city-label-icon",
                    icon_size=(22, 22),
                    icon_anchor=(11, 11),
                    html="""
                    <div style="
                        width:16px;
                        height:16px;
                        background:white;
                        background-image:linear-gradient(135deg, transparent 0 45%, #999 45% 55%, transparent 55% 100%);
                        border-radius:50%;
                        box-shadow: 0 0 0 3px black;
                    "></div>
                    """
                ),
            ).add_to(layer)
        else:
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color=border,
                fill=True,
                fill_color=fill,
                fill_opacity=0.7,
                popup=pop,
            ).add_to(layer)

        # City label (non-interactive so it doesn't create extra bubbles)
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                class_name="city-label-icon",   # <-- ADD THIS
                icon_size=(150, 36),
                icon_anchor=(7, 26),
                html=(
                    "<div class='city-label' style='font-size: 8pt; color: black; "
                    "font-weight: bold; font-family: Arial;'>"
                    f"{row.get('City','')}: {label}</div>"
                )
            ),
            interactive=False,
        ).add_to(label_layer)

add_status_markers(no_basis_rows,  no_basis_layer,  "No Basis", 'black', 'white')
add_status_markers(shut_down_rows, shut_down_layer, "Shut Down", 'black', 'grey')
add_status_markers(startup_rows,   startup_layer,   "Startup",  'black', 'lightgrey')
add_status_markers(valero_rows, valero_layer, "Valero", 'black', 'darkgrey')

# ====================
# Legend & Title/Footer
# ====================
legend_html = """
<div class="map-card map-legend">
  <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
    <div style="width:14px;height:14px;background-color:white;border:1px solid black;border-radius:50%;"></div>
    <b>No Basis</b>

    <div style="width:14px;height:14px;background-color:grey;border:1px solid black;border-radius:50%;"></div>
    <b>Shut Down</b>

    <div style="width:14px;height:14px;background-color:lightgrey;border:1px solid black;border-radius:50%;"></div>
    <b>Startup</b>

    <div style="
      width:14px;height:14px;
      background-color:white;
      background-image:linear-gradient(135deg, transparent 0 45%, #999 45% 55%, transparent 55% 100%);
      border:1px solid black;border-radius:50%;
    "></div>
    <b>Valero</b>
  </div>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))



title_html = f"""
<div class="map-card map-title">
  <h3 align="center" style="margin:0;"><b>Ethanol Corn <br> Nearby Basis Map (30 Days Ago) {selected}</b></h3>
</div>
"""
m.get_root().html.add_child(folium.Element(title_html))



foot_html = f"""
<div class="desktop-only" style="position: absolute; bottom: -5px; left: 90%;
     transform: translateX(-45%); z-index: 1000; padding: 10px; border-radius: 5px;">
  <h3 align="center" style="font-size:10px; margin: 0;"><b>Ethanol Producer Database {today2}</b></h3>
</div>
"""
m.get_root().html.add_child(folium.Element(foot_html))


# Market watermark
if SHOW_MARKET_WATERMARK:
    market_path = r"C:\Users\ehakm\OneDrive\Documents\Python Code\figure.png"
    market_base64 = encode_image(market_path)

    market_html = f"""
    <div class="market-watermark">
      <img src="data:image/png;base64,{market_base64}" alt="Watermark">
    </div>
    """
    m.get_root().html.add_child(folium.Element(market_html))

# Personal watermark
if SHOW_PERSONAL_WATERMARK:
    watermark_path = r"C:\Users\ehakm\OneDrive\Documents\Watermark\Hakmiller-02.PNG"
    watermark_base64 = encode_image(watermark_path)

    watermark_html = f"""
    <div class="personal-watermark">
      <img src="data:image/png;base64,{watermark_base64}" alt="Watermark">
    </div>
    """
    m.get_root().html.add_child(folium.Element(watermark_html))


print("#" * 60 )

# Render ONCE (expensive step)
html = m.get_root().render()

# 1) Save an archived copy (local) WITHOUT re-rendering
archive_path = Path(rf"C:/Users/ehakm/OneDrive/Documents/Sankey/Corn Map/ethanol_map_30DaysAgo_{today}.html")

archive_path.parent.mkdir(parents=True, exist_ok=True)
archive_path.write_text(html, encoding="utf-8")
print("Saved Archive HTML")



# ========================================================
# PAGES PUBLISH MIRROR (covers Pages source: /root or /docs)
# ========================================================
REPO_DIR = Path(r"C:\Users\ehakm\Documents\ELHApp-backend")

LOCAL_MARKET_IMG   = r"C:\Users\ehakm\OneDrive\Documents\Python Code\figure.png"
LOCAL_PERSONAL_IMG = r"C:\Users\ehakm\OneDrive\Documents\Watermark\Hakmiller-02.PNG"

def deploy_to_github():
    print("\n🚀 Starting Git Automation...")

    # Clear any stuck states
    subprocess.run(["git", "rebase", "--abort"], cwd=str(REPO_DIR), capture_output=True)
    subprocess.run(["git", "merge", "--abort"], cwd=str(REPO_DIR), capture_output=True)

    # Stage all changes
    subprocess.run(["git", "add", "."], cwd=str(REPO_DIR))

    # Commit
    commit_msg = f"Auto-update Basis Map: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    c = subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(REPO_DIR))

    if c.returncode != 0:
        print("⚠️ Nothing new to commit (or commit failed). Not pushing.")
        return

    # Push
    print("📡 Uploading to GitHub...")
    result = subprocess.run(["git", "push", "origin", "main"], cwd=str(REPO_DIR))

    if result.returncode == 0:
        print("✨ SUCCESS: Map is live on GitHub.")
    else:
        print("❌ FAILED: push did not go through. Check auth/network.")


# Write to BOTH places so Pages updates whether it is configured to publish from / or /docs
PUBLISH_ROOTS = [
    REPO_DIR,           # Pages: main / (root)
    REPO_DIR / "docs"   # Pages: main /docs
]

def write_pages_bundle(root_dir: Path, html: str) -> None:
    static_dir = root_dir / "static_data"
    static_dir.mkdir(parents=True, exist_ok=True)

    snap_dir = static_dir / "30_days_ago"
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Save the file the redirect will point to
    out_html = snap_dir / "Current_Basis_30DaysAgo.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"✅ 30-days-ago map saved -> {out_html}")

    # Redirect only controls /static_data/30_days_ago/
    (snap_dir / "index.html").write_text(
        """<!doctype html><html><head><meta charset="utf-8">
    <script>
      window.location.replace("Current_Basis_30DaysAgo.html?ts=" + Date.now());
    </script>
    </head><body></body></html>""",
            encoding="utf-8"
        )
    print(f"✅ 30-days-ago redirect index -> {snap_dir / 'index.html'}")

    # Copy images (optional; harmless even though you embed base64)
    copy_list = []
    if SHOW_MARKET_WATERMARK:
        copy_list.append(LOCAL_MARKET_IMG)
    if SHOW_PERSONAL_WATERMARK:
        copy_list.append(LOCAL_PERSONAL_IMG)
    
    for src in copy_list:

        p = Path(src)
        if p.exists():
            shutil.copy(p, snap_dir / p.name)
            print(f"✅ Image copied -> {snap_dir / p.name}")
        else:
            print(f"⚠️ Warning: Image not found -> {p}")






for root in PUBLISH_ROOTS:
    write_pages_bundle(root, html)


# Deploy once (stages + commits + pushes everything, including docs/ if created)
if DEPLOY_TO_GITHUB:
    deploy_to_github()
else:
    print("🛑 DEPLOY_TO_GITHUB=False -> skipping git push (local files still saved).")



# --- Assumes you already have a DataFrame named `Corn` with columns: State, Adj_Basis, Date ---

df = corn.copy()

# Hygiene
df['Basis_Date'] = pd.to_datetime(df['Basis_Date'], errors='coerce')
df['Adj_Basis'] = pd.to_numeric(df['Adj_Basis'], errors='coerce')
df['State'] = df['State'].astype(str).str.strip()
df = df.dropna(subset=['State', 'Basis_Date', 'Adj_Basis'])

# Latest overall date present in the dataset
latest_date = df['Basis_Date'].max()

# Helper: for a single state's sub-DF, find the date closest to a target date.
# If tolerance is provided and the nearest is farther than tolerance, return NaN/None.
def nearest_date_value(state_df, target_date, tolerance=None):
    # Find index of the nearest date
    idx = (state_df['Basis_Date'] - target_date).abs().idxmin()
    nearest_dt = state_df.loc[idx, 'Basis_Date']
    if tolerance is not None and abs(nearest_dt - target_date) > tolerance:
        return np.nan, pd.NaT
    # On that nearest calendar date, average in case multiple rows exist
    day_mask = state_df['Basis_Date'] == nearest_dt
    val = state_df.loc[day_mask, 'Adj_Basis'].mean()
    return val, nearest_dt

# Build per-state latest average (on the latest overall date)
latest_day = df[df['Basis_Date'] == latest_date]
latest_avg = latest_day.groupby('State', as_index=True)['Adj_Basis'].mean()

# Targets relative to the latest overall date
t_1w = latest_date - pd.Timedelta(days=7)
t_1m = latest_date - pd.DateOffset(months=1)
t_1y = latest_date - pd.DateOffset(years=1)

# Optional tolerances for how far we're willing to accept a "nearest" match
tol_1w = pd.Timedelta(days=7)   # e.g., within ±5 days of 1 week ago
tol_1m = pd.Timedelta(days=15)  # within ±15 days of 1 month ago
tol_1y = pd.Timedelta(days=30)  # within ±30 days of 1 year ago

# Prepare result index = all states present
states = sorted(df['State'].unique())
result = pd.DataFrame(index=states)

# Fill latest averages
result['Avg_Latest'] = latest_avg.reindex(result.index)

# Compute nearests per state
vals_1w, dates_1w = [], []
vals_1m, dates_1m = [], []
vals_1y, dates_1y = [], []

# Build each state's df ONCE (avoids filtering the full df repeatedly)
state_groups = {st: g.sort_values("Basis_Date") for st, g in df.groupby("State")}

for st in result.index:
    sdf = state_groups.get(st)
    if sdf is None or sdf.empty:
        vals_1w.append(np.nan); dates_1w.append(pd.NaT)
        vals_1m.append(np.nan); dates_1m.append(pd.NaT)
        vals_1y.append(np.nan); dates_1y.append(pd.NaT)
        continue

    v1w, d1w = nearest_date_value(sdf, t_1w, tolerance=tol_1w)
    v1m, d1m = nearest_date_value(sdf, t_1m, tolerance=tol_1m)
    v1y, d1y = nearest_date_value(sdf, t_1y, tolerance=tol_1y)

    vals_1w.append(v1w); dates_1w.append(d1w)
    vals_1m.append(v1m); dates_1m.append(d1m)
    vals_1y.append(v1y); dates_1y.append(d1y)


result['Near_1W'] = vals_1w
result['Near_1M'] = vals_1m
result['Near_1Y'] = vals_1y

# (Optional) also include which dates were matched so you can verify proximity
result['Date_1W_Matched'] = dates_1w
result['Date_1M_Matched'] = dates_1m
result['Date_1Y_Matched'] = dates_1y

# Nice ordering and sorting
result = result[['Avg_Latest', 'Near_1W', 'Near_1M', 'Near_1Y',
                 'Date_1W_Matched', 'Date_1M_Matched', 'Date_1Y_Matched']]

# Example: sort by state name
result = result.sort_index()

# Peek
#print(f"Latest overall date in dataset: {latest_date:%Y-%m-%d}")
#display(result)

# ====================

#


# No-basis plants but only in states with bids
basis_states = corn[corn['Adj_Basis'] != 'No Basis']['State'].unique()
no_basis_in_bid_states = corn[(corn['Adj_Basis'] == 'No Basis') & (corn['State'].isin(basis_states))]
no_bid = no_basis_in_bid_states[['EPM', 'Ownership', NAME_COL, 'State']].copy()
no_bid = no_bid.rename(columns={NAME_COL: "Name"})  # optional: standardize column name


print("#" * 60 + "\n")
print("Number of locations without a bid:  "+str(len(no_bid)))
print('\n')
print(no_bid.head(25))
print('\n')

# (Optional) Only print df_basis diagnostics if available in this runtime
if 'df_basis' in globals():
    print("=== Sanity Check (df_basis) ===")
    print("Latest date in df_basis:", getattr(df_basis['Date'].max(), 'strftime', lambda fmt: df_basis['Date'].max())("%Y-%m-%d")
          if not df_basis.empty else "N/A")
    print("Rows @ latest date:", len(df_basis))
    print("Unique EPMs @ latest date:", df_basis['Epm_number'].nunique())
    dupes = (df_basis.groupby('Epm_number').size()
             .reset_index(name='rows_per_epm')
             .query('rows_per_epm > 1'))
    print("Plants with duplicates:", len(dupes))
    if not dupes.empty:
        print(dupes.head(20))
    print("\n")

# ====================


# Prepare scripts
# (Optional) other scripts that produce charts saved to disk
exec(open(r'C:\Users\ehakm\OneDrive\Documents\Sankey\LCFS top ten chart.py').read())
exec(open(r'C:\Users\ehakm\OneDrive\Documents\Sankey\state_average.py').read())
exec(open(r'C:\Users\ehakm\OneDrive\Documents\Python Code\Basis Project\Maps\distribution basis.py').read())
#exec(open(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Financial\corn market.py", encoding="utf-8").read())
#exec(open(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Contour map\top_ten_producer.py", encoding="utf-8").read())


# Bash commands
#cd /c/Users/ehakm/Documents/ELHApp-backend
#git pull --rebase origin main
#git add static_data/Current_Basis.html
#git commit -m "Update map"
#git push origin main

# --- sanity: make sure REPO_DIR is a real git repo ---
print('\n')
print("#" * 60 + "\n")
print("REPO_DIR:", REPO_DIR)
print("Repo exists:", REPO_DIR.exists())
print(".git exists:", (REPO_DIR / ".git").exists())
print('\n')



