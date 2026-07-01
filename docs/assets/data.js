/* Shared data-loading + taxonomy module for the Capital Cascade dashboard.
 * No build step, no framework: every page loads this file, then calls
 * CascadeData.loadAll() to fetch the three JSONL files (published as a
 * same-repo copy under docs/data/ by the daily/monthly GitHub Actions,
 * kept in sync with the real source of truth at data/ in the repo root)
 * and parses them client-side. */

const CascadeData = (() => {
  const SECTORS = {
    semiconductors: { label: "Semiconductors" },
    data_centers_ai_infra: { label: "Data Centers / AI Infra" },
    power_utilities_grid: { label: "Power / Utilities / Grid" },
    lng_gas: { label: "LNG / Gas" },
    oil_gas_refining: { label: "Oil & Gas Refining" },
    mining_metals: { label: "Mining & Metals" },
    industrial_materials: { label: "Industrial Materials" },
    chemicals_petrochemicals: { label: "Chemicals / Petrochemicals" },
    battery_ev: { label: "Battery / EV" },
    autos: { label: "Autos" },
    shipbuilding_shipping: { label: "Shipbuilding / Shipping" },
    aerospace_defence: { label: "Aerospace & Defence" },
    pharma_biomanufacturing: { label: "Pharma / Biomanufacturing" },
    construction_homebuilding: { label: "Construction / Homebuilding" },
    agriculture: { label: "Agriculture" },
    airlines: { label: "Airlines" },
    telecom: { label: "Telecom" },
    other_emerging: { label: "Other / Emerging" },
  };

  const PHASE_COLORS = {
    boom: "#2e7d32",
    peak: "#c77700",
    bust: "#c62828",
    trough: "#1565c0",
    unclear: "#7a7a7a",
  };

  const PHASE_LABELS = {
    boom: "Boom", peak: "Peak", bust: "Bust", trough: "Trough", unclear: "Unclear",
  };

  const ROLE_ICONS = {
    investor: "🏗️", // 🏗️
    supplier: "⛏️",       // ⛏️
    enabler: "🎟️",  // 🎟️
    macro: "🌐",          // 🌐
    unclear: "❔",              // ❔
  };

  function sectorLabel(key) {
    return (SECTORS[key] && SECTORS[key].label) || key.replace(/_/g, " ");
  }

  async function fetchJSONL(path) {
    try {
      const res = await fetch(path, { cache: "no-store" });
      if (!res.ok) return [];
      const text = await res.text();
      return text
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => {
          try {
            return JSON.parse(l);
          } catch (e) {
            return null;
          }
        })
        .filter(Boolean);
    } catch (e) {
      console.error("failed to load", path, e);
      return [];
    }
  }

  async function loadAll() {
    const [seeds, trends, assessments] = await Promise.all([
      fetchJSONL("data/seeds.jsonl"),
      fetchJSONL("data/sector_trends.jsonl"),
      fetchJSONL("data/sector_assessments.jsonl"),
    ]);
    return { seeds, trends, assessments };
  }

  // Latest assessment (max run_date) per sector.
  function latestAssessments(assessments) {
    const byDate = {};
    for (const a of assessments) {
      const cur = byDate[a.sector];
      if (!cur || a.run_date > cur.run_date) byDate[a.sector] = a;
    }
    return byDate;
  }

  // Trend rows for one sector, sorted by period_start ascending.
  function trendsFor(trends, sector) {
    return trends
      .filter((t) => t.sector === sector)
      .sort((a, b) => (a.period_start < b.period_start ? -1 : 1));
  }

  // Seeds for one sector, newest published first.
  function seedsFor(seeds, sector) {
    return seeds
      .filter((s) => s.sector === sector)
      .sort((a, b) => ((a.published || "") < (b.published || "") ? 1 : -1));
  }

  function fmtDate(iso) {
    if (!iso) return "";
    return iso.slice(0, 10);
  }

  return {
    SECTORS, PHASE_COLORS, PHASE_LABELS, ROLE_ICONS,
    sectorLabel, loadAll, latestAssessments, trendsFor, seedsFor, fmtDate,
  };
})();
