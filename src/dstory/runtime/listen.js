// dstory "Listen": hear a chart's shape. Web Audio, no library.
//
// Injected by `dstory bundle` after the data panel and the explorer, whose
// column roles it reuses. Under every chart with a numeric series sits a
// "Listen" button: each series plays as a run of short tones, pitch rising
// with the value (two octaves, low to high) and panning left to right as it
// goes. Series play one after another, each announced first through the
// explorer's aria-live region ("West, 6 points, from 100 to 171, rising").
// Nothing ever plays until a reader asks. With a chart focused, "L" plays
// the current series.
//
// Turn it off with "a11y": {"sonify": false} in meta or a scene, or for the
// whole bundle with `dstory bundle my-story --no-a11y-extras`.
(() => {
  "use strict";
  if (window.__DSTORY_LISTEN__) return;
  const panel = () => window.__DSTORY_DATA_PANEL__;
  const ex = () => window.__DSTORY_EXPLORER__;
  const dataOf = () => window.__STORY_DATA__ || null;
  const attached = {};

  const LOW_HZ = 220, OCTAVES = 2;          // A3 .. A5
  const SERIES_GAP = 0.6;                   // seconds of silence between series
  const LEAD_IN = 0.08;

  // ---- the plan: what plays, when (pure; the vetter and tests read it) ----
  function planFor(scene, only) {
    const P = panel(), E = ex();
    if (!P || !E) return null;
    const data = dataOf();
    const rows = P.rowsOf(data, scene);
    if (!rows) return null;
    const roles = E.rolesOf(rows, P.columnsOf(rows, scene), scene);
    const p = roles.primary;
    if (!p) return null;
    let groups = E.groupsOf(rows, roles);
    const all = groups;
    const vals = rows.map(r => (r ? r[p] : null)).filter(v => typeof v === "number" && isFinite(v));
    if (!vals.length) return null;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const freqOf = (v) => LOW_HZ * Math.pow(2, OCTAVES * (hi === lo ? 0.5 : (v - lo) / (hi - lo)));
    if (only != null && groups[only]) groups = [groups[only]];
    // A scatter (x and y both numbers, no ordered name) plays left to right
    // along x, not in row order.
    const cfg = (scene && typeof scene.config === "object" && scene.config) || {};
    const xcol = roles.measures.length > 1 && roles.measures[0] !== p
      && roles.measures[0] === (cfg.x || "x") && !roles.ordered ? roles.measures[0] : null;
    if (xcol) {
      const xv = (i) => (rows[i] && typeof rows[i][xcol] === "number" ? rows[i][xcol] : Infinity);
      groups = groups.map(g => ({ key: g.key, idx: g.idx.slice().sort((a, b) => xv(a) - xv(b)) }));
    }
    const series = [];
    let t = LEAD_IN;
    for (const g of groups) {
      const n = g.idx.length;
      const step = Math.min(0.3, Math.max(0.09, 3.2 / n));   // ~3 s per series, clamped
      const notes = [];
      g.idx.forEach((ri, k) => {
        const v = rows[ri] ? rows[ri][p] : null;
        if (typeof v !== "number" || !isFinite(v)) return;      // a gap stays silent
        notes.push({ t: t + k * step, dur: step * 0.8, freq: freqOf(v),
                     pan: n > 1 ? -0.8 + 1.6 * (k / (n - 1)) : 0, value: v, row: ri });
      });
      series.push({ key: g.key, start: t, end: t + n * step,
                    says: E.groupSummary(rows, roles, g), notes });
      t += n * step + SERIES_GAP;
    }
    return { scene: scene.id, measure: p, low: lo, high: hi, series,
             duration: t - SERIES_GAP, groups: all.length };
  }

  // ---- playback --------------------------------------------------------
  let playing = null;    // { ctx, timers, button, sceneId }
  const AC = () => window.AudioContext || window.webkitAudioContext;

  function stop() {
    if (!playing) return;
    const cur = playing;
    playing = null;
    cur.timers.forEach(clearTimeout);
    const live = document.getElementById("dstory-explore-live");
    const focused = document.activeElement && document.activeElement.hasAttribute
      && document.activeElement.hasAttribute("data-explore");
    if (live && !focused) live.classList.remove("is-visible");
    try { cur.ctx.close(); } catch (e) { /* already closed */ }
    if (cur.button) setIdle(cur.button);
  }

  function play(sceneId, only) {
    stop();
    const data = dataOf();
    const scene = data && (data.scenes || []).find(s => s && s.id === sceneId);
    const plan = scene && planFor(scene, only);
    const Ctx = AC();
    if (!plan || !Ctx) return null;
    const ctx = new Ctx();
    const master = ctx.createGain();
    master.gain.value = 0.22;
    master.connect(ctx.destination);
    const t0 = ctx.currentTime;
    let oscillators = 0;
    for (const s of plan.series) {
      for (const n of s.notes) {
        const osc = ctx.createOscillator();
        osc.type = "triangle";
        osc.frequency.value = n.freq;
        const env = ctx.createGain();
        const at = t0 + n.t, end = at + n.dur;
        env.gain.setValueAtTime(0, at);
        env.gain.linearRampToValueAtTime(1, at + 0.012);          // no clicks
        env.gain.setValueAtTime(1, Math.max(at + 0.012, end - 0.04));
        env.gain.linearRampToValueAtTime(0, end);
        let node = osc.connect(env);
        if (ctx.createStereoPanner) {
          const pan = ctx.createStereoPanner();
          pan.pan.value = n.pan;
          node = env.connect(pan);
        } else node = env;
        node.connect(master);
        osc.start(at);
        osc.stop(end + 0.02);
        oscillators += 1;
      }
    }
    const button = document.querySelector(`[data-listen="${CSS.escape(sceneId)}"]`);
    // The announcements also show on screen while the chart plays.
    const live = () => document.getElementById("dstory-explore-live");
    const say = (text) => {
      if (ex() && ex().say) ex().say(text);
      if (live()) live().classList.add("is-visible");
    };
    const timers = plan.series.map(s => setTimeout(() => say(s.says), Math.max(0, s.start * 1000 - 60)));
    timers.push(setTimeout(stop, (plan.duration + 0.25) * 1000));
    playing = { ctx, timers, button, sceneId };
    if (button) setPlaying(button);
    return { oscillators, duration: plan.duration };
  }

  function toggle(sceneId, only) {
    if (playing && playing.sceneId === sceneId) { stop(); return null; }
    return play(sceneId, only);
  }

  // ---- the button --------------------------------------------------------
  const headlineOf = (s) => s.headline
    || (s.steps && s.steps[0] && s.steps[0].headline)
    || (s.frames && s.frames[0] && s.frames[0].headline) || s.id;
  function setIdle(b) {
    b.textContent = "▶ Listen";
    b.setAttribute("aria-pressed", "false");
  }
  function setPlaying(b) {
    b.textContent = "■ Stop";
    b.setAttribute("aria-pressed", "true");
  }

  const available = (scene) => {
    const P = panel();
    if (!P || !AC() || !scene || !P.option(dataOf(), scene, "sonify")) return false;
    const plan = planFor(scene);
    return !!(plan && plan.series.some(s => s.notes.length > 1));
  };

  function attachAll() {
    const data = dataOf(), P = panel();
    if (!data || !Array.isArray(data.scenes) || !P || !ex()) return true;
    let done = true;
    for (const scene of data.scenes) {
      if (!scene || !scene.id || attached[scene.id] !== undefined) continue;
      if (!available(scene)) { attached[scene.id] = null; continue; }
      const section = document.getElementById(scene.id);
      if (!section || !section.matches("[data-scene]")) { done = false; continue; }
      const tools = P.toolsFor(scene, section);
      if (!tools) { attached[scene.id] = null; continue; }
      const b = document.createElement("button");
      b.type = "button";
      b.className = "scene-listen";
      b.setAttribute("data-listen", scene.id);
      b.setAttribute("aria-label", `Listen to the chart: ${headlineOf(scene)}`);
      setIdle(b);
      b.addEventListener("click", () => toggle(scene.id, null));
      tools.prepend(b);
      attached[scene.id] = b;
    }
    return done;
  }

  function start() {
    if (attachAll()) return;
    const obs = new MutationObserver(() => { if (attachAll()) obs.disconnect(); });
    obs.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => obs.disconnect(), 15000);
  }
  // Capture phase: the explorer stops Escape from bubbling once it has used it.
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") stop(); }, true);
  window.addEventListener("pagehide", stop);

  window.__DSTORY_LISTEN__ = {
    attached, plan: (sceneId, only) => {
      const s = dataOf() && (dataOf().scenes || []).find(x => x && x.id === sceneId);
      return s ? planFor(s, only) : null;
    },
    play, stop, toggle, available,
    expected: (scene) => available(scene),
    get playing() { return playing ? playing.sceneId : null; },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
