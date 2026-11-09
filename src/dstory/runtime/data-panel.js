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

  let nf = null;
  const fmt = (v) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "number") {
      if (!nf) {
        const lang = (dataOf() && dataOf().meta && dataOf().meta.lang) || undefined;
        try { nf = new Intl.NumberFormat(lang, { maximumFractionDigits: 6 }); }
        catch (e) { nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 }); }
      }
      return nf.format(v);
    }
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  };
  // CSV: raw values (not locale-formatted), RFC 4180 quoting. Text that a
  // spreadsheet would run as a formula (=, +, @) is prefixed with a quote.
  const csvCell = (v) => {
    if (v === null || v === undefined) return "";
    let t = typeof v === "object" ? JSON.stringify(v) : String(v);
    if (typeof v === "string" && /^[=+@\t\r]/.test(t)) t = "'" + t;
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

  function fillBody(tbody, rows, cols, numeric, upto) {
    const frag = document.createDocumentFragment();
    for (const r of rows.slice(tbody.rows.length, upto)) {
      const tr = h("tr");
      cols.forEach((c, i) => {
        const cell = h(i === 0 ? "th" : "td", i === 0 ? { scope: "row" } : {}, fmt(r ? r[c] : ""));
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
      fillBody(tbody, rows, cols, numeric, Math.min(n, MAX_ROWS));
      body.append(h("div", { class: "scene-data__scroll", tabindex: "0", role: "region",
        "aria-label": `Data table: ${headlineOf(scene)}` }, table));
      if (n > MAX_ROWS) {
        const more = h("button", { type: "button", class: "scene-data__all" }, `Show all ${label}`);
        more.addEventListener("click", () => { fillBody(tbody, rows, cols, numeric, n); more.remove(); });
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

  function place(scene, section, panel) {
    if (scene.kind === "custom") {
      // A custom renderer owns its whole <section>: sit after it, never inside.
      if (slides()) return false;
      section.after(panel);
      return true;
    }
    const inner = scene.kind === "bleed" ? section.querySelector(".scene__bleedinner") : null;
    (inner || section).append(panel);
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
    MAX_ROWS, attached, option, fmt, csvRow, columnsOf, rowsOf,
    expected: (scene) => {
      const data = dataOf();
      return { table: option(data, scene, "table"), download: option(data, scene, "download"),
               placed: scene.kind !== "custom" || !slides() };
    },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
