// dstory chart explorer: every chart can be read with the keyboard.
//
// Injected by `dstory bundle` next to the data panel (it reuses the panel's
// number formatting). Every scene with a `dataset` gets a focusable chart:
// Tab to it and a live region speaks a summary ("Signups, 6 points, from 1,000
// to 3,400, rising"); the arrow keys then step through the rows ("Mar: 2,900
// (Signups), 3 of 6"). It reads window.__STORY_DATA__, never the chart's
// internals, so it works for recipes, your own D3 and Vizzu alike.
//
//   Left / Right   previous / next point        Home / End   first / last point
//   Up / Down      previous / next series       Enter        the summary again
//   Escape         leave the chart (in slides, the arrows go back to the deck)
//
// Turn it off with "a11y": {"explorer": false} in meta or a scene, or for the
// whole bundle with `dstory bundle my-story --no-a11y-extras`.
(() => {
  "use strict";
  if (window.__DSTORY_EXPLORER__) return;
  const panel = () => window.__DSTORY_DATA_PANEL__;
  const dataOf = () => window.__STORY_DATA__ || null;
  const attached = {};
  const state = new WeakMap();

  const opt = (data, scene, key) => {
    if (panel()) return panel().option(data, scene, key);
    const s = (scene && scene.a11y) || {}, m = (data && data.meta && data.meta.a11y) || {};
    const v = s[key] != null ? s[key] : m[key] != null ? m[key] : true;
    return v !== false;
  };
  const fmt = (v, raw) => panel() ? panel().fmt(v, raw)
    : (typeof v === "number" ? v.toLocaleString() : v == null ? "" : String(v));
  const pretty = (c) => String(c).replace(/[_-]+/g, " ").trim();

  // ---- which columns play which part ------------------------------------
  const DATEISH_NAME = /^(date|time|period|year|month|day|week|quarter|yr|fy)s?$/i;
  const DATEISH_VALUE = /^\d{4}(-\d{2}(-\d{2})?)?([T ][\d:.]+Z?)?$/;
  const GENERIC = /^(value|values|y|amount|val)$/i;

  function rolesOf(rows, cols, scene) {
    const cfg = (scene && typeof scene.config === "object" && scene.config) || {};
    const vals = (c) => rows.map(r => (r ? r[c] : null)).filter(v => v !== null && v !== undefined);
    const isNum = (c) => { const v = vals(c); return v.length > 0 && v.every(x => typeof x === "number"); };
    const distinct = (c) => new Set(vals(c).map(String)).size;
    const raw = panel() ? panel().rawColumns(rows, cols, scene) : cols.map(() => false);
    const isRaw = (c) => raw[cols.indexOf(c)];
    const pick = (keys, ok) => {
      for (const k of keys) { const c = cfg[k]; if (typeof c === "string" && cols.includes(c) && ok(c)) return c; }
      return null;
    };
    const dateish = (c) => DATEISH_NAME.test(String(c)) || (!isNum(c) && vals(c).length > 0
      && vals(c).every(v => typeof v === "string" && DATEISH_VALUE.test(v)));
    const n = rows.length;

    // The point's name: the x / label column if it is not a measure.
    let name = pick(["label", "x", "period"], c => !isNum(c) || isRaw(c))
      || cols.find(c => dateish(c))
      || cols.find(c => !isNum(c))
      || cols.find(c => isRaw(c)) || null;
    // A series column groups the rows into lines, panels or groups.
    let series = pick(["series", "group", "color"], c => c !== name && !isNum(c));
    if (!series && name && distinct(name) < n) {
      series = cols.find(c => c !== name && !isNum(c) && distinct(c) >= 2 && distinct(c) <= 24
        && distinct(c) < n) || null;
    }
    // The measures read out at each point.
    let measures = ["x", "y", "value", "start", "end"].map(k => cfg[k])
      .filter((c, i, a) => typeof c === "string" && cols.includes(c) && c !== name && isNum(c) && a.indexOf(c) === i);
    if (!measures.length) {
      for (const d of ["y", "value", "start", "end"]) if (cols.includes(d) && d !== name && isNum(d)) measures.push(d);
    }
    if (!measures.length) measures = cols.filter(c => c !== name && c !== series && isNum(c) && !isRaw(c));
    if (!measures.length) measures = cols.filter(c => c !== name && c !== series && isNum(c));
    measures = measures.slice(0, 4);
    const primary = measures.includes(cfg.end || "end") ? (cfg.end || "end")
      : measures.includes(cfg.y || "y") ? (cfg.y || "y") : measures[measures.length > 1 && cfg.x && measures[0] === cfg.x ? 1 : 0];
    const ordered = !!name && (dateish(name) || isNum(name));
    const notes = measures.length ? [] : cols.filter(c => c !== name && c !== series && !isNum(c)).slice(0, 2);
    const roles = { name, series, measures, notes, primary: primary || null, ordered, nameRaw: !!name && isRaw(name) };
    roles.nameText = nameFormatter(rows, roles);
    return roles;
  }

  // "2024-05-01" reads as "May 2024" (or "2024" when every date is 1 Jan),
  // in the story's language. Anything else is shown as it is.
  const ISO = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/;
  function nameFormatter(rows, roles) {
    const base = (v) => fmt(v, roles.nameRaw);
    if (!roles.name) return base;
    const vs = rows.map(r => (r ? r[roles.name] : null)).filter(v => v != null);
    if (!vs.length || !vs.every(v => typeof v === "string" && ISO.test(v))) return base;
    const parts = vs.map(v => v.match(ISO));
    const yearOnly = parts.every(m => m[2] === "01" && (!m[3] || m[3] === "01"));
    const monthOnly = parts.every(m => !m[3] || m[3] === "01");
    const lang = (dataOf() && dataOf().meta && dataOf().meta.lang) || undefined;
    let df;
    try {
      df = new Intl.DateTimeFormat(lang, yearOnly ? { year: "numeric", timeZone: "UTC" }
        : monthOnly ? { month: "short", year: "numeric", timeZone: "UTC" }
        : { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    } catch (e) { return base; }
    return (v) => {
      const m = typeof v === "string" ? v.match(ISO) : null;
      return m ? df.format(new Date(Date.UTC(+m[1], +m[2] - 1, +(m[3] || 1)))) : base(v);
    };
  }

  function groupsOf(rows, roles) {
    if (!roles.series) return [{ key: null, idx: rows.map((_, i) => i) }];
    const map = new Map();
    rows.forEach((r, i) => {
      const k = r ? r[roles.series] : null;
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(i);
    });
    return Array.from(map, ([key, idx]) => ({ key, idx }));
  }

  // ---- what is said ------------------------------------------------------
  function pointText(rows, roles, g, k) {
    const r = rows[g.idx[k]] || {};
    const nm = roles.name ? roles.nameText(r[roles.name]) : `Row ${g.idx[k] + 1}`;
    const ms = roles.measures;
    let body;
    if (!ms.length) body = roles.notes.map(c => fmt(r[c])).filter(Boolean).join(", ");
    else if (ms.length === 1 && GENERIC.test(String(ms[0]))) body = fmt(r[ms[0]]);
    else body = ms.map(m => `${pretty(m)} ${fmt(r[m])}`).join(", ");
    const ser = roles.series ? ` (${fmt(g.key)})` : "";
    return `${nm}${body ? ": " + body : ""}${ser}, ${k + 1} of ${g.idx.length}`;
  }

  function trendWord(a, b) {
    if (typeof a !== "number" || typeof b !== "number") return "";
    const base = Math.max(Math.abs(a), Math.abs(b)) || 1;
    if (Math.abs(b - a) / base < 0.01) return "roughly flat";
    return b > a ? "rising" : "falling";
  }

  function groupSummary(rows, roles, g) {
    const p = roles.primary;
    const label = roles.series ? `${fmt(g.key)}, ` : "";
    const count = `${g.idx.length} ${roles.ordered ? "point" : "item"}${g.idx.length === 1 ? "" : "s"}`;
    if (!p) {
      if (roles.ordered && roles.name && g.idx.length > 1) {
        const first = rows[g.idx[0]] || {}, lastR = rows[g.idx[g.idx.length - 1]] || {};
        return `${label}${count}, from ${roles.nameText(first[roles.name])} to ${roles.nameText(lastR[roles.name])}`;
      }
      return `${label}${count}`;
    }
    const pts = g.idx.map(i => rows[i] || {}).filter(r => typeof r[p] === "number");
    if (!pts.length) return `${label}${count}`;
    const nameOf = (r) => roles.name ? roles.nameText(r[roles.name]) : "";
    let hi = pts[0], lo = pts[0];
    for (const r of pts) { if (r[p] > hi[p]) hi = r; if (r[p] < lo[p]) lo = r; }
    if (roles.ordered && pts.length > 1) {
      const a = pts[0], b = pts[pts.length - 1];
      let s = `${label}${count}, from ${fmt(a[p])} to ${fmt(b[p])}, ${trendWord(a[p], b[p])}`;
      if (hi !== a && hi !== b) s += `, peaking at ${fmt(hi[p])}${roles.name ? " in " + nameOf(hi) : ""}`;
      else if (lo !== a && lo !== b) s += `, dipping to ${fmt(lo[p])}${roles.name ? " in " + nameOf(lo) : ""}`;
      return s;
    }
    if (pts.length === 1) return `${label}${count}: ${fmt(pts[0][p])}`;
    const what = roles.measures.length > 1 || !GENERIC.test(String(p)) ? ` ${pretty(p)}` : "";
    return `${label}${count}; highest${what} ${nameOf(hi)} (${fmt(hi[p])}), lowest${what} ${nameOf(lo)} (${fmt(lo[p])})`;
  }

  const headlineOf = (s) => s.headline
    || (s.steps && s.steps[0] && s.steps[0].headline)
    || (s.frames && s.frames[0] && s.frames[0].headline) || s.id;

  function summaryText(scene, rows, roles, groups) {
    const parts = groups.map(g => groupSummary(rows, roles, g));
    const keys = roles.series && groups.length > 1
      ? "Left and right arrows step through the points, up and down switch series"
      : "Arrow keys step through the data";
    const L = window.__DSTORY_LISTEN__;
    const listen = L && L.available(scene) ? (roles.series && groups.length > 1
      ? "; L plays this series as sound" : "; L plays the chart as sound") : "";
    return `${headlineOf(scene)}. ${parts.join("; ")}. ${keys}${listen}; Escape leaves the chart.`;
  }

  // ---- the live region ---------------------------------------------------
  let live = null;
  function liveRegion() {
    if (live && live.isConnected) return live;
    live = document.createElement("div");
    live.className = "scene-explore__live";
    live.id = "dstory-explore-live";
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    document.body.append(live);
    return live;
  }
  function say(text) {
    const r = liveRegion();
    // Re-announce identical text (Home pressed twice) by clearing first.
    if (r.textContent === text) r.textContent = "";
    r.textContent = text;
  }
  let hint = null;
  function hintId() {
    if (!hint || !hint.isConnected) {
      hint = document.createElement("span");
      hint.id = "dstory-explore-hint";
      hint.hidden = true;
      hint.textContent = "Interactive chart. Arrow keys step through the data; Escape leaves the chart.";
      document.body.append(hint);
    }
    return hint.id;
  }

  // ---- wiring ------------------------------------------------------------
  function attach(data, scene, mount) {
    const rows = panel() ? panel().rowsOf(data, scene) : null;
    if (!rows) return null;
    const cols = panel().columnsOf(rows, scene);
    const roles = rolesOf(rows, cols, scene);
    const groups = groupsOf(rows, roles);
    const st = { scene, rows, roles, groups, g: 0, k: -1 };
    state.set(mount, st);
    mount.setAttribute("tabindex", "0");
    mount.setAttribute("role", "application");
    mount.setAttribute("aria-roledescription", "chart");
    mount.setAttribute("aria-describedby", hintId());
    mount.setAttribute("data-explore", scene.id);
    mount.addEventListener("focus", () => {
      liveRegion().classList.add("is-visible");
      say(summaryText(scene, rows, roles, groups));
    });
    mount.addEventListener("blur", () => { liveRegion().classList.remove("is-visible"); });
    mount.addEventListener("keydown", (e) => onKey(e, mount, st));
    return mount;
  }

  function onKey(e, mount, st) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const g = st.groups[st.g];
    const last = g.idx.length - 1;
    let handled = true;
    switch (e.key) {
      case "ArrowRight": st.k = Math.min(last, st.k + 1); break;
      case "ArrowLeft":  st.k = st.k < 0 ? 0 : Math.max(0, st.k - 1); break;
      case "Home":       st.k = 0; break;
      case "End":        st.k = last; break;
      case "ArrowDown":
      case "ArrowUp": {
        if (st.groups.length < 2) { handled = false; break; }
        const step = e.key === "ArrowDown" ? 1 : -1;
        const prevName = st.k >= 0 && st.roles.name ? String((st.rows[g.idx[st.k]] || {})[st.roles.name]) : null;
        st.g = (st.g + step + st.groups.length) % st.groups.length;
        const ng = st.groups[st.g];
        // Keep the same x when the next series has it; else the same position.
        let k = prevName === null ? Math.max(0, st.k) : ng.idx.findIndex(i => String((st.rows[i] || {})[st.roles.name]) === prevName);
        if (k < 0) k = Math.min(Math.max(0, st.k), ng.idx.length - 1);
        st.k = k;
        break;
      }
      case "Enter": say(summaryText(st.scene, st.rows, st.roles, st.groups)); e.preventDefault(); e.stopPropagation(); return;
      case "Escape": mount.blur(); e.preventDefault(); e.stopPropagation(); return;
      case "l":
      case "L": {
        const L = window.__DSTORY_LISTEN__;
        if (!L || !L.available(st.scene)) { handled = false; break; }
        L.toggle(st.scene.id, st.groups.length > 1 ? st.g : null);
        e.preventDefault(); e.stopPropagation();
        return;
      }
      default: handled = false;
    }
    if (!handled) return;
    e.preventDefault();
    e.stopPropagation();          // in slides mode, the arrows belong to the chart now
    say(pointText(st.rows, st.roles, st.groups[st.g], st.k));
  }

  function attachAll() {
    const data = dataOf();
    if (!data || !Array.isArray(data.scenes) || !panel()) return true;
    let done = true;
    for (const scene of data.scenes) {
      if (!scene || !scene.id || attached[scene.id] !== undefined) continue;
      if (!panel().rowsOf(data, scene) || scene.kind === "custom" || !opt(data, scene, "explorer")) {
        attached[scene.id] = null;
        continue;
      }
      const section = document.getElementById(scene.id);
      const mount = section && section.matches("[data-scene]")
        ? section.querySelector(`[data-mount="${CSS.escape(scene.id)}"]`) : null;
      if (!mount) { done = false; continue; }
      attached[scene.id] = attach(data, scene, mount);
    }
    return done;
  }

  function start() {
    if (attachAll()) return;
    const obs = new MutationObserver(() => { if (attachAll()) obs.disconnect(); });
    obs.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => obs.disconnect(), 15000);
  }

  window.__DSTORY_EXPLORER__ = {
    attached, rolesOf, groupsOf, pointText, summaryText, groupSummary, say,
    expected: (scene) => !!(scene && scene.kind !== "custom" && opt(dataOf(), scene, "explorer")),
    // For tests and the vetter: what the explorer says for a scene's point.
    describe: (sceneId, g, k) => {
      const m = attached[sceneId];
      const st = m && state.get(m);
      if (!st) return null;
      return k == null ? summaryText(st.scene, st.rows, st.roles, st.groups)
        : pointText(st.rows, st.roles, st.groups[g], k);
    },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
