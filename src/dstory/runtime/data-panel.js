// dstory data panel: every chart ships its own data.
//
// Injected by `dstory bundle` (and build()) into every story. Under each scene
// that has a `dataset`, it adds a collapsed "Data" disclosure holding a real
// <table> (screen-reader and keyboard friendly) and a "Download CSV" link built
// from the inlined data, so it works offline. It is renderer-agnostic: it reads
// window.__STORY_DATA__ and never looks inside a chart.
//
// Turn parts off in data.json:  "meta": {"a11y": {"table": false, "download": false}}
// or per scene:                 {"id": "s1", "a11y": {"table": false}, "table_columns": ["month", "value"]}
// or for the whole bundle:      dstory bundle my-story --no-a11y-extras
(() => {
  "use strict";
  if (window.__DSTORY_DATA_PANEL__) return;
  const MAX_ROWS = 50;
  const attached = {};

  const dataOf = () => window.__STORY_DATA__ || null;
  const option = (data, scene, key) => {
    const s = (scene && scene.a11y) || {};
    const m = (data && data.meta && data.meta.a11y) || {};
    const v = s[key] !== undefined && s[key] !== null ? s[key]
      : m[key] !== undefined && m[key] !== null ? m[key] : true;
    return v !== false;
  };
  const slides = () => document.body.classList.contains("story-mode--slides");

  const rowsOf = (data, scene) => {
    const rows = scene && scene.dataset && data.datasets ? data.datasets[scene.dataset] : null;
    return Array.isArray(rows) && rows.length ? rows : null;
  };
  const columnsOf = (rows, scene) => {
    if (Array.isArray(scene.table_columns) && scene.table_columns.length) return scene.table_columns.slice();
    const cols = [];
    for (const r of rows.slice(0, 500)) {
      if (r && typeof r === "object") for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
    }
    return cols;
  };

  let nf = null, nfRaw = null;
  const lang = () => (dataOf() && dataOf().meta && dataOf().meta.lang) || undefined;
  const numberFormat = (grouping) => {
    try { return new Intl.NumberFormat(lang(), { maximumFractionDigits: 6, useGrouping: grouping }); }
    catch (e) { return new Intl.NumberFormat(undefined, { maximumFractionDigits: 6, useGrouping: grouping }); }
  };
  // fmt(v, raw): raw drops the thousands separator (years, IDs, codes) but
  // keeps the locale's decimal mark.
  const fmt = (v, raw) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "number") {
      if (raw) return (nfRaw || (nfRaw = numberFormat(false))).format(v);
      return (nf || (nf = numberFormat(true))).format(v);
    }
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  };
  // Columns whose numbers are labels, not quantities: "2020" is a year, not
  // two thousand and twenty. Override per scene with
  // "table_format": {"col": "raw" | "number"}.
  const ID_NAME = /(^|[_\s-])(year|yr|fy|id|code|fips|zip|zipcode|postcode|postal|geoid|isbn|sku|ean|upc)s?$/i;
  const isRawColumn = (rows, col, scene) => {
    const o = scene && scene.table_format && scene.table_format[col];
    if (o === "raw") return true;
    if (o === "number") return false;
    const vals = rows.map(r => r ? r[col] : null).filter(v => typeof v === "number");
    if (!vals.length || !vals.every(Number.isInteger)) return false;
    if (ID_NAME.test(String(col)) || /^id$/i.test(String(col))) return true;
    return vals.every(v => v >= 1000 && v <= 2999);          // looks like years
  };
  const rawColumns = (rows, cols, scene) => cols.map(c => isRawColumn(rows, c, scene));
  const cellText = (rows, i, cols, scene) => {
    const raw = rawColumns(rows, cols, scene);
    return cols.map((c, j) => fmt(rows[i] ? rows[i][c] : "", raw[j]));
  };
  // CSV: raw values (not locale-formatted), RFC 4180 quoting. Text that a
  // spreadsheet would run as a formula (OWASP: = + - @ tab CR, and their
  // full-width forms) is prefixed with a quote; a plain number stored as text
  // ("-5", "+1.2%") is left alone.
  const FORMULA = /^[=+\-@\t\r\uFF1D\uFF0B\uFF0D\uFE63\u2212\uFF20]/;
  const PLAIN_NUMBER = /^[+\-\u2212]?(\d[\d,]*)?(\.\d+)?([eE][+-]?\d+)?%?$/;
  const csvCell = (v) => {
    if (v === null || v === undefined) return "";
    let t = typeof v === "object" ? JSON.stringify(v) : String(v);
    if (typeof v === "string") {
      const lead = t.replace(/^[ \u00A0]+/, "");
      if (FORMULA.test(lead) && !(PLAIN_NUMBER.test(lead) && /\d/.test(lead))) t = "'" + t;
    }
    return /[",\r\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
  };
  const csvRow = (r, cols) => cols.map(c => csvCell(r ? r[c] : "")).join(",");
  const toCSV = (rows, cols) => [cols.map(csvCell).join(","), ...rows.map(r => csvRow(r, cols))].join("\r\n");

  const headlineOf = (s) => s.headline
    || (s.steps && s.steps[0] && s.steps[0].headline)
    || (s.frames && s.frames[0] && s.frames[0].headline) || s.id;

  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    for (const k of kids) if (k != null) n.append(typeof k === "string" ? document.createTextNode(k) : k);
    return n;
  }

  function fillBody(tbody, rows, cols, numeric, raw, upto) {
    const frag = document.createDocumentFragment();
    for (const r of rows.slice(tbody.rows.length, upto)) {
      const tr = h("tr");
      cols.forEach((c, i) => {
        const cell = h(i === 0 ? "th" : "td", i === 0 ? { scope: "row" } : {}, fmt(r ? r[c] : "", raw[i]));
        if (numeric[i]) cell.classList.add("num");
        tr.append(cell);
      });
      frag.append(tr);
    }
    tbody.append(frag);
  }

  function panelFor(data, scene) {
    const rows = rowsOf(data, scene);
    if (!rows) return null;
    const wantTable = option(data, scene, "table");
    const wantCsv = option(data, scene, "download");
    if (!wantTable && !wantCsv) return null;
    const cols = columnsOf(rows, scene);
    const n = rows.length;
    const label = `${n.toLocaleString()} row${n === 1 ? "" : "s"}`;
    const details = h("details", { class: "scene-data", "data-scene-data": scene.id });
    details.append(h("summary", {}, wantTable ? "Data" : "Get the data",
      h("span", { class: "scene-data__count" }, ` · ${label}`)));
    const body = h("div", { class: "scene-data__body" });
    if (wantTable) {
      const numeric = cols.map(c => rows.every(r => !r || r[c] == null || typeof r[c] === "number")
        && rows.some(r => r && typeof r[c] === "number"));
      const table = h("table", { "data-rows": String(n), "data-cols": cols.join("\u001f") });
      table.append(h("caption", {}, `Underlying data: ${headlineOf(scene)} (${label})`));
      const hr = h("tr");
      cols.forEach((c, i) => hr.append(h("th", { scope: "col", class: numeric[i] ? "num" : "" }, c)));
      table.append(h("thead", {}, hr));
      const tbody = h("tbody");
      table.append(tbody);
      const raw = rawColumns(rows, cols, scene);
      fillBody(tbody, rows, cols, numeric, raw, Math.min(n, MAX_ROWS));
      body.append(h("div", { class: "scene-data__scroll", tabindex: "0", role: "region",
        "aria-label": `Data table: ${headlineOf(scene)}` }, table));
      if (n > MAX_ROWS) {
        const more = h("button", { type: "button", class: "scene-data__all" }, `Show all ${label}`);
        more.addEventListener("click", () => { fillBody(tbody, rows, cols, numeric, raw, n); more.remove(); });
        body.append(more);
      }
    }
    if (wantCsv) {
      const href = "data:text/csv;charset=utf-8," + encodeURIComponent("﻿" + toCSV(rows, cols));
      body.append(h("p", { class: "scene-data__actions" },
        h("a", { class: "scene-data__csv", href, download: `${scene.id}.csv` }, "Download CSV")));
    }
    details.append(body);
    // In slides mode a click anywhere advances the deck; the panel is not "anywhere".
    details.addEventListener("click", e => e.stopPropagation());
    return details;
  }

  // One row of reader tools per scene ("Listen", "Data"), placed under the
  // chart. Shared with the explorer's Listen button (explorer.js).
  function toolsFor(scene, section) {
    const sel = `[data-scene-tools="${CSS.escape(scene.id)}"]`;
    const found = document.querySelector(sel);
    if (found) return found;
    // A custom renderer owns its whole <section>: sit after it, never inside
    // (and not at all in slides, where the section is the slide).
    if (scene.kind === "custom" && slides()) return null;
    const tools = h("div", { class: "scene-tools", "data-scene-tools": scene.id });
    // In slides mode a click anywhere advances the deck; the tools are not "anywhere".
    tools.addEventListener("click", e => e.stopPropagation());
    if (scene.kind === "custom") section.after(tools);
    else {
      const inner = scene.kind === "bleed" ? section.querySelector(".scene__bleedinner") : null;
      (inner || section).append(tools);
    }
    return tools;
  }

  function place(scene, section, panel) {
    const tools = toolsFor(scene, section);
    if (!tools) return false;
    tools.append(panel);
    return true;
  }

  function attachAll() {
    const data = dataOf();
    if (!data || !Array.isArray(data.scenes)) return true;
    let done = true;
    for (const scene of data.scenes) {
      if (!scene || !scene.id || attached[scene.id] !== undefined) continue;
      if (!rowsOf(data, scene)) { attached[scene.id] = null; continue; }
      const section = document.getElementById(scene.id);
      if (!section || !section.matches("[data-scene]")) { done = false; continue; }
      const panel = panelFor(data, scene);
      attached[scene.id] = panel && place(scene, section, panel) ? panel : null;
    }
    return done;
  }

  function start() {
    if (attachAll()) return;
    const obs = new MutationObserver(() => { if (attachAll()) obs.disconnect(); });
    obs.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => obs.disconnect(), 15000);
  }

  // Slides: "t" opens or closes the current slide's data.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "t" || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target && e.target.matches && e.target.matches("input, textarea, [contenteditable]")) return;
    if (!slides()) return;
    const cur = document.querySelector(".scene.is-current .scene-data");
    if (cur) { cur.open = !cur.open; e.preventDefault(); }
  });

  // Print: a PDF handout carries the data.
  const reopened = [];
  window.addEventListener("beforeprint", () => {
    document.querySelectorAll("details.scene-data:not([open])").forEach(d => { d.open = true; reopened.push(d); });
  });
  window.addEventListener("afterprint", () => { while (reopened.length) reopened.pop().open = false; });

  window.__DSTORY_DATA_PANEL__ = {
    MAX_ROWS, attached, option, fmt, csvRow, csvCell, columnsOf, rowsOf, rawColumns, cellText, toolsFor,
    expected: (scene) => {
      const data = dataOf();
      return { table: option(data, scene, "table"), download: option(data, scene, "download"),
               placed: scene.kind !== "custom" || !slides() };
    },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
