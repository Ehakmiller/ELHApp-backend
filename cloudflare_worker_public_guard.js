const KV_KEY = "calculator:data";
const SEARCH_LIMIT_DEFAULT = 10;
const SEARCH_LIMIT_MAX = 25;
const CALCULATOR_ORIGIN = "https://ehakmiller.github.io";
const CALCULATOR_REFERER_PREFIX = "https://ehakmiller.github.io/ELHApp-Carbon_Calculator/";

function corsHeaders(request) {
  const origin = request?.headers?.get("origin") || "";
  const allowedOrigin = origin === CALCULATOR_ORIGIN ? origin : "*";
  return {
    "access-control-allow-origin": allowedOrigin,
    "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "Content-Type, Authorization, X-Internal-Token",
    "vary": "Origin",
  };
}

function json(request, value, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...corsHeaders(request),
      ...extraHeaders,
    },
  });
}

function textValue(value) {
  return String(value ?? "").trim();
}

function lc(value) {
  return textValue(value).toLowerCase();
}

function plantId(p) {
  return textValue(p?.fac_info?.epm || p?.epm || p?.id);
}

function publicPlant(p) {
  const f = p?.fac_info || {};
  return {
    epm: textValue(f.epm),
    plant_name: f.plant_name ?? null,
    ownership: f.ownership ?? null,
    state: f.state ?? null,
    city: f.city ?? null,
  };
}

function searchMatch(p, params) {
  const f = p?.fac_info || {};
  const name = lc(params.get("name"));
  const state = textValue(params.get("state")).toUpperCase();

  if (state && textValue(f.state).toUpperCase() !== state) return false;
  if (!name) return true;

  return [f.plant_name, f.ownership, f.city, f.state, f.epm]
    .map(lc)
    .some((value) => value.includes(name));
}

async function loadPlants(env) {
  const raw = await env.CALCULATOR_DATA.get(KV_KEY, "json");
  return Array.isArray(raw) ? raw : [];
}

function hasInternalAccess(request, env, url) {
  const expected = env.INTERNAL_API_TOKEN;
  if (!expected) return false;

  const auth = request.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  const headerToken = request.headers.get("x-internal-token") || "";
  const queryToken = url.searchParams.get("token") || "";

  return [bearer, headerToken, queryToken].some((token) => token && token === expected);
}

function hasCalculatorBrowserAccess(request) {
  const origin = request.headers.get("origin") || "";
  const referer = request.headers.get("referer") || "";

  return origin === CALCULATOR_ORIGIN || referer.startsWith(CALCULATOR_REFERER_PREFIX);
}

function calculatePublicResult(plant, params) {
  const fac = plant?.fac_info || {};
  const ci = plant?.ci_summary || {};
  const epa = plant?.epa_ghg_derived || {};

  return {
    epm: textValue(fac.epm),
    plant_name: fac.plant_name ?? null,
    ownership: fac.ownership ?? null,
    state: fac.state ?? null,
    city: fac.city ?? null,
    ci_lcfs_delivered_g_per_mj: ci.ci_lcfs_delivered_g_per_mj ?? null,
    ci_date: ci.ci_date ?? null,
    thermal_btu_per_gal_est: epa.thermal_btu_per_gal_est ?? null,
    thermal_calc_method: epa.thermal_calc_method ?? null,
    fuel_type_master: plant?.fuel_summary?.fuel_type_master ?? null,
    note: "Public calculation endpoint currently returns calculator-safe summary fields only. Move scenario math here before removing client-side calculation dependencies.",
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }

    if (request.method !== "GET") {
      return json(request, { error: "Method not allowed" }, 405);
    }

    if (path === "/health") {
      return json(request, {
        ok: true,
        guarded_plant_endpoint: true,
        endpoints: ["/health", "/search", "/public-plant", "/calculate"],
      });
    }

    const plants = await loadPlants(env);

    if (path === "/search") {
      const hasFilter = ["name", "state", "epm"].some((key) => textValue(url.searchParams.get(key)));

      const epm = textValue(url.searchParams.get("epm"));
      const limitRaw = Number(url.searchParams.get("limit") || SEARCH_LIMIT_DEFAULT);
      const limit = hasFilter
        ? Math.max(1, Math.min(Number.isFinite(limitRaw) ? limitRaw : SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX))
        : plants.length;

      const rows = plants
        .filter((p) => (epm ? plantId(p) === epm : searchMatch(p, url.searchParams)))
        .slice(0, limit)
        .map(publicPlant);

      return json(request, { rows, count: rows.length, limit });
    }

    if (path === "/public-plant") {
      const id = textValue(url.searchParams.get("id"));
      if (!id) return json(request, { error: "Missing required id." }, 400);
      const plant = plants.find((p) => plantId(p) === id);
      if (!plant) return json(request, { error: "Plant not found", id }, 404);
      return json(request, publicPlant(plant));
    }

    if (path === "/plant") {
      if (!hasCalculatorBrowserAccess(request) && !hasInternalAccess(request, env, url)) {
        return json(
          request,
          {
            error: "Full plant records are not directly public. Use the calculator page, /public-plant, or /calculate.",
          },
          403
        );
      }
      const id = textValue(url.searchParams.get("id"));
      if (!id) return json(request, { error: "Missing required id." }, 400);
      const plant = plants.find((p) => plantId(p) === id);
      if (!plant) return json(request, { error: "Plant not found", id }, 404);
      return json(request, plant);
    }

    if (path === "/calculate") {
      const id = textValue(url.searchParams.get("id"));
      if (!id) return json(request, { error: "Missing required id." }, 400);
      const plant = plants.find((p) => plantId(p) === id);
      if (!plant) return json(request, { error: "Plant not found", id }, 404);
      return json(request, calculatePublicResult(plant, url.searchParams));
    }

    return json(request, { error: "Use /health, /search, /public-plant, or /calculate" }, 404);
  },
};
