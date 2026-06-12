// story.js — orchestration. Reads window.__STORY_DATA__ (injected at bundle time)
// or fetches data.json (dev mode), then builds scenes.
//
// Per-scene chart code lives in scenes/<scene-id>.js — author writes those.
// Each scene file calls window.STORY.register("scene-id", drawFn).
//
// Motion One is loaded via a tiny module-to-global wrapper in index.html
// and exposed on window.MOTION = { animate, stagger, inView, scroll }.
// (We avoid ES-module imports in this file so the bundled HTML works under
// the file:// protocol — browsers block cross-origin module fetches there.)

const SCENE_RENDERERS = {};

// Read Motion at call time, not at module-load — the ESM shim may not have
// resolved yet. Each call falls back to a no-op if Motion isn't ready.
const animate = (...args) => (window.MOTION?.animate || (() => {}))(...args);
const stagger = (...args) => (window.MOTION?.stagger || (() => 0))(...args);
const inView  = (target, fn, opts) =>
  (window.MOTION?.inView || ((t, f) => f({ target: t })))(target, fn, opts);

function register(id, fn) {
  SCENE_RENDERERS[id] = fn;
}
window.STORY = { register };

// Wait for Motion to load before init (so opening animations actually animate).
function waitForMotion(timeoutMs = 2500) {
  return new Promise(resolve => {
    if (window.MOTION) return resolve();
    const t = setTimeout(resolve, timeoutMs);  // proceed anyway after timeout
    const check = setInterval(() => {
      if (window.MOTION) { clearInterval(check); clearTimeout(t); resolve(); }
    }, 30);
  });
}

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

async function getData() {
  if (window.__STORY_DATA__) return window.__STORY_DATA__;
  const res = await fetch("data.json");
  return res.json();
}

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v);
  }
  for (const k of kids) {
    if (k == null) continue;
    n.append(typeof k === "string" ? document.createTextNode(k) : k);
  }
  return n;
}

function renderHero(meta) {
  const h = document.querySelector(".hero");
  if (!h) return;
  h.querySelector(".hero__eyebrow").textContent = meta.subtitle || "";
  h.querySelector(".hero__headline").textContent = meta.title || "Untitled";
  h.querySelector(".hero__deck").textContent = meta.deck || "";
  h.querySelector(".hero__author").textContent = meta.author || "";
  h.querySelector(".hero__date").textContent = meta.published || "";

  if (!reduceMotion) {
    animate(
      [h.querySelector(".hero__eyebrow"), h.querySelector(".hero__headline"),
       h.querySelector(".hero__deck"), h.querySelector(".hero__byline")],
      { opacity: [0, 1], y: [16, 0] },
      { duration: 0.8, easing: [0.22, 1, 0.36, 1], delay: stagger(0.12, { start: 0.1 }) }
    );
  }
}

function renderSources(sources = [], meta = {}) {
  const ul = document.getElementById("sources");
  if (!ul) return;
  ul.replaceChildren(...sources.map(s => {
    const li = el("li");
    if (s.url) {
      li.append(el("a", { href: s.url, target: "_blank", rel: "noopener" }, s.name));
      if (s.accessed) li.append(el("span", { class: "outro__accessed" }, ` · accessed ${s.accessed}`));
    } else {
      li.textContent = s.name;
    }
    return li;
  }));
  const author = document.getElementById("credits-author");
  const pub = document.getElementById("credits-published");
  if (author) author.textContent = meta.author || "";
  if (pub) pub.textContent = meta.published || "";
}

function buildScene(scene) {
  let node;
  if (scene.kind === "scrolly")      node = buildScrollyScene(scene);
  else if (scene.kind === "bleed")   node = buildBleedScene(scene);
  else if (scene.kind === "pinned")  node = buildPinnedScene(scene);
  else if (scene.kind === "vizzu")   node = buildVizzuScene(scene);
  else if (scene.kind === "custom")  node = buildCustomScene(scene);
  else                                node = buildSimpleScene(scene);
  // Apply width modifier if set (default | narrow | wide | full)
  if (scene.width && scene.width !== "default") {
    node.classList.add("scene--w-" + scene.width);
  }
  return node;
}

function buildSimpleScene(scene) {
  const wrap = el("section", { class: "scene scene--simple", "data-scene": scene.id, id: scene.id });
  if (scene.chrome !== false) {
    wrap.append(el("h2", {}, scene.headline || ""));
    if (scene.commentary) wrap.append(el("p", {}, scene.commentary));
  }
  wrap.append(el("div", { class: "scene__graphic", "data-mount": scene.id }));
  if (scene.chrome !== false && scene.source_line) {
    wrap.append(el("p", { class: "scene__source" }, scene.source_line));
  }
  return wrap;
}

function buildCustomScene(scene) {
  // Chrome-free: no h2, no p, no .scene__graphic wrapper. The renderer gets
  // the full <section> as its mount and owns the entire DOM. Use for
  // typography animations, bespoke layouts, embedded interactives, etc.
  const wrap = el("section", {
    class: "scene scene--custom", "data-scene": scene.id, id: scene.id, "data-mount": scene.id,
  });
  return wrap;
}

function buildScrollyScene(scene) {
  const wrap = el("section", { class: "scene scene--scrolly", "data-scene": scene.id, id: scene.id });
  wrap.append(el("div", { class: "scene__graphic", "data-mount": scene.id }));
  const text = el("div", { class: "scene__text" });
  (scene.steps || []).forEach((step, i) => {
    const s = el("div", { class: "step", "data-step": String(i) });
    s.append(el("h3", {}, step.headline || ""));
    if (step.commentary) s.append(el("p", {}, step.commentary));
    text.append(s);
  });
  wrap.append(text);
  if (scene.source_line) wrap.append(el("p", { class: "scene__source" }, scene.source_line));
  return wrap;
}

function buildBleedScene(scene) {
  const wrap = el("section", { class: "scene scene--bleed", "data-scene": scene.id, id: scene.id });
  wrap.append(el("div", { class: "scene__bleedbg", "data-mount": scene.id }));
  const inner = el("div", { class: "scene__bleedinner" });
  inner.append(el("h2", {}, scene.headline || ""));
  if (scene.commentary) inner.append(el("p", {}, scene.commentary));
  wrap.append(inner);
  return wrap;
}

function buildPinnedScene(scene) {
  const wrap = el("section", { class: "scene scene--pinned", "data-scene": scene.id, id: scene.id });
  const pin = el("div", { class: "scene__pin", "data-mount": scene.id });
  wrap.append(pin);
  if (scene.source_line) wrap.append(el("p", { class: "scene__source" }, scene.source_line));
  return wrap;
}

function buildVizzuScene(scene) {
  // Same shape as scrolly: sticky chart + stepping text. The chart is a Vizzu
  // canvas that morphs between frames on each step.
  const wrap = el("section", { class: "scene scene--scrolly scene--vizzu", "data-scene": scene.id, id: scene.id });
  wrap.append(el("div", { class: "scene__graphic", "data-mount": scene.id }));
  const text = el("div", { class: "scene__text" });
  if (scene.headline) {
    const heading = el("h3", { class: "scene--vizzu__headline" }, scene.headline);
    text.append(heading);
  }
  (scene.frames || []).forEach((frame, i) => {
    const s = el("div", { class: "step", "data-step": String(i) });
    s.append(el("h3", {}, frame.headline || ""));
    if (frame.commentary) s.append(el("p", {}, frame.commentary));
    text.append(s);
  });
  wrap.append(text);
  if (scene.source_line) wrap.append(el("p", { class: "scene__source" }, scene.source_line));
  return wrap;
}

function activateScrollyScene(sceneEl, scene, data, slidesMode = false) {
  const renderer = SCENE_RENDERERS[scene.id];
  if (!renderer) return null;
  const mount = sceneEl.querySelector(`[data-mount="${scene.id}"]`);
  const ctrl = renderer(mount, data, scene); // expected to return { onStep(i, dir) } or null
  if (slidesMode) return ctrl;  // slides controller drives onStep

  const scroller = scrollama();
  scroller.setup({
    step: sceneEl.querySelectorAll(".step"),
    offset: 0.5,
    debug: false,
  }).onStepEnter(({ element, index, direction }) => {
    element.classList.add("is-active");
    if (ctrl && typeof ctrl.onStep === "function") ctrl.onStep(index, direction);
  }).onStepExit(({ element, direction }) => {
    if (direction === "up") element.classList.remove("is-active");
  });

  window.addEventListener("resize", () => scroller.resize());
  return ctrl;
}

function activateBleedScene(sceneEl, scene, data, slidesMode = false) {
  const renderer = SCENE_RENDERERS[scene.id];
  if (renderer) {
    const mount = sceneEl.querySelector(`[data-mount="${scene.id}"]`);
    renderer(mount, data, scene);
  }
  if (slidesMode || reduceMotion) return null;  // slides controller handles entry; CSS drives the rest
  inView(sceneEl, () => {
    animate(
      [sceneEl.querySelector("h2"), sceneEl.querySelector("p")].filter(Boolean),
      { opacity: [0, 1], y: [12, 0] },
      { duration: 0.7, easing: [0.22, 1, 0.36, 1], delay: stagger(0.12, { start: 0.1 }) }
    );
  }, { margin: "0px 0px -25% 0px" });
  return null;
}

function activatePinnedScene(sceneEl, scene, data, slidesMode = false) {
  const renderer = SCENE_RENDERERS[scene.id];
  if (!renderer) return null;
  const mount = sceneEl.querySelector(`[data-mount="${scene.id}"]`);
  const ctrl = renderer(mount, data, scene);
  if (!ctrl || typeof ctrl.onProgress !== "function") return ctrl;
  if (slidesMode) {
    // Pinned scenes are scroll-progress driven; in slides mode, show end state.
    ctrl.onProgress(1);
    return ctrl;
  }

  // Use IntersectionObserver + requestAnimationFrame for progress 0..1
  let raf = null;
  const update = () => {
    const r = sceneEl.getBoundingClientRect();
    const total = r.height - window.innerHeight;
    const p = Math.min(1, Math.max(0, -r.top / total));
    ctrl.onProgress(p);
    raf = null;
  };
  const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  update();
  return ctrl;
}

function activateSimpleScene(sceneEl, scene, data, slidesMode = false) {
  const renderer = SCENE_RENDERERS[scene.id];
  if (!renderer) return null;
  const mount = sceneEl.querySelector(`[data-mount="${scene.id}"]`);
  // Render immediately. Renderer may use inView internally for entry animations.
  return renderer(mount, data, scene);
}

function activateCustomScene(sceneEl, scene, data, slidesMode = false) {
  // The section IS the mount. The renderer owns the entire DOM and is free to
  // build any layout, including reading scene.headline / scene.commentary /
  // scene.source_line itself if it wants to display them.
  const renderer = SCENE_RENDERERS[scene.id];
  if (!renderer) {
    console.warn(`[dstory] kind:"custom" scene "${scene.id}" has no registered renderer.`);
    return null;
  }
  return renderer(sceneEl, data, scene);
}

function waitForVizzu(timeoutMs = 4000) {
  return new Promise(resolve => {
    if (window.Vizzu) return resolve(window.Vizzu);
    const t = setTimeout(() => resolve(null), timeoutMs);
    const check = setInterval(() => {
      if (window.Vizzu) { clearInterval(check); clearTimeout(t); resolve(window.Vizzu); }
    }, 30);
  });
}

function buildVizzuStyle() {
  // Map theme CSS custom properties → Vizzu style object so charts inherit theme.
  const cs = getComputedStyle(document.documentElement);
  const get = k => (cs.getPropertyValue(k) || "").trim();
  const palette = [1, 2, 3, 4, 5, 6, 7]
    .map(i => get(`--cat-${i}`)).filter(Boolean).join(" ");
  const ink     = get("--ink") || "#111";
  const inkSoft = get("--ink-soft") || "#666";
  const inkFaint= get("--ink-faint") || "#999";
  const bgElev  = get("--bg-elev") || "#fff";
  const fontDisplay = get("--font-display") || "Georgia, serif";
  const fontBody    = get("--font-body")    || "system-ui, sans-serif";

  return {
    fontFamily: fontBody,
    backgroundColor: bgElev,
    plot: {
      backgroundColor: bgElev,
      marker: { colorPalette: palette || undefined },
      xAxis: {
        label: { fontSize: 11, color: inkFaint },
        title: { color: inkSoft, fontSize: 11 },
        interlacing: { color: "#00000000" },   // hide alternating bands (transparent)
      },
      yAxis: {
        label: { fontSize: 11, color: inkFaint },
        title: { color: inkSoft, fontSize: 11 },
        interlacing: { color: "#00000000" },
      },
    },
    title: {
      fontFamily: fontDisplay,
      color: ink,
      fontSize: 18,
      paddingTop: 8, paddingBottom: 8,
    },
    legend: {
      label: { color: inkSoft, fontSize: 11 },
      title: { color: inkSoft, fontSize: 11 },
    },
    logo: { filter: "opacity(0)" },             // hide Vizzu logo
  };
}

async function activateVizzuScene(sceneEl, scene, data, slidesMode = false) {
  const Vizzu = await waitForVizzu();
  if (!Vizzu) {
    console.warn("Vizzu not available — scene", scene.id, "will be inert.");
    return null;
  }
  const records = data.datasets?.[scene.dataset];
  if (!Array.isArray(records) || records.length === 0) {
    console.warn("Vizzu scene", scene.id, "missing dataset:", scene.dataset);
    return null;
  }

  const mount = sceneEl.querySelector(`[data-mount="${scene.id}"]`);
  const chart = new Vizzu(mount);

  const series = (scene.series || []).map(s => ({
    name: s.name,
    type: s.type === "measure" ? "measure" : "dimension",
  }));

  // Custom renderer can override default behavior.
  const customRenderer = SCENE_RENDERERS[scene.id];
  if (customRenderer) {
    return customRenderer(mount, data, scene); // hand it the mount; it owns the chart
  }

  const themeStyle = buildVizzuStyle();
  const userStyle  = scene.style || {};

  await chart.initializing;
  const firstFrame = (scene.frames && scene.frames[0]) || {};
  try {
    await chart.animate({
      data: { series, records },
      config: firstFrame.config || {},
      style:  { ...themeStyle, ...userStyle },
    });
  } catch (e) {
    console.error(`[dstory] Vizzu init failed for scene "${scene.id}":`, e?.message || e);
    // Recover gracefully: re-try without the theme style override. Most of our
    // Vizzu issues historically have been style-shape mismatches; the chart
    // itself is usually fine.
    try {
      await chart.animate({
        data: { series, records },
        config: firstFrame.config || {},
      });
      console.warn(`[dstory] Scene "${scene.id}" rendered with default Vizzu style (theme override rejected).`);
    } catch (e2) {
      console.error(`[dstory] Scene "${scene.id}" failed to render even without style:`, e2?.message || e2);
      // Don't throw — let the rest of the page initialize.
    }
  }

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const duration = reduce ? 0 : (scene.duration || 1.0);

  // ctrl that the slides controller (or scroll mode) can call to morph to a frame.
  const ctrl = {
    onStep(i /*, direction */) {
      const frame = (scene.frames || [])[i];
      if (frame && frame.config) {
        chart.animate({ config: frame.config }, duration).catch(() => {});
      }
    },
  };

  if (slidesMode) return ctrl;

  const scroller = scrollama();
  scroller.setup({
    step: sceneEl.querySelectorAll(".step"),
    offset: 0.5,
    debug: false,
  }).onStepEnter(({ element, index, direction }) => {
    element.classList.add("is-active");
    ctrl.onStep(index, direction);
  }).onStepExit(({ element, direction }) => {
    if (direction === "up") element.classList.remove("is-active");
  });
  window.addEventListener("resize", () => scroller.resize());
  return ctrl;
}

function setupSlidesController(builtScenes, data) {
  const heroEl  = document.querySelector(".hero");
  const outroEl = document.querySelector(".outro");
  document.documentElement.classList.add("story-mode--slides");
  document.body.classList.add("story-mode--slides");

  // Flat slide list: [hero, ...one-per-step-or-frame, outro].
  const slides = [];
  if (heroEl) slides.push({ kind: "hero", el: heroEl });
  for (const entry of builtScenes) {
    const stepCount = entry.scene.steps?.length || entry.scene.frames?.length || 1;
    for (let i = 0; i < stepCount; i++) {
      slides.push({ kind: "scene", el: entry.node, sceneEntry: entry, stepIdx: i, totalSteps: stepCount });
    }
  }
  if (outroEl) slides.push({ kind: "outro", el: outroEl });

  // Initialize: every slide hidden except the first.
  slides.forEach((s, i) => {
    if (i === 0) {
      s.el.classList.add("is-current");
    } else {
      s.el.setAttribute("aria-hidden", "true");
    }
  });

  let current = 0;
  const indicator = document.querySelector("[data-slide-indicator]");
  const updateIndicator = () => {
    if (indicator) indicator.textContent = `${current + 1} / ${slides.length}`;
  };
  updateIndicator();

  function show(idx, dir = "forward") {
    if (idx < 0 || idx >= slides.length) return;
    if (idx === current) return;
    const prev = slides[current];
    const next = slides[idx];

    if (prev.el !== next.el) {
      prev.el.classList.remove("is-current");
      prev.el.setAttribute("aria-hidden", "true");
      next.el.classList.add("is-current");
      next.el.removeAttribute("aria-hidden");
    }

    if (next.kind === "scene") {
      const steps = next.el.querySelectorAll(".step");
      steps.forEach((st, i) => st.classList.toggle("is-active", i === next.stepIdx));
      if (next.sceneEntry.ctrl?.onStep) {
        next.sceneEntry.ctrl.onStep(next.stepIdx, dir === "forward" ? "down" : "up");
      }
    }

    current = idx;
    updateIndicator();
  }

  // Trigger first slide's chart state if applicable.
  const first = slides[0];
  if (first?.kind === "scene") {
    const steps = first.el.querySelectorAll(".step");
    steps.forEach((st, i) => st.classList.toggle("is-active", i === first.stepIdx));
    if (first.sceneEntry.ctrl?.onStep) first.sceneEntry.ctrl.onStep(first.stepIdx, "down");
  }

  // Keyboard navigation
  document.addEventListener("keydown", (e) => {
    if (e.target.matches?.("input, textarea, [contenteditable]")) return;
    switch (e.key) {
      case "ArrowRight":
      case "PageDown":
      case " ":
        e.preventDefault(); show(current + 1, "forward"); break;
      case "ArrowLeft":
      case "PageUp":
        e.preventDefault(); show(current - 1, "backward"); break;
      case "Home":
        e.preventDefault(); show(0, "backward"); break;
      case "End":
        e.preventDefault(); show(slides.length - 1, "forward"); break;
    }
  });

  // Click-anywhere navigation (skip interactive elements + the controls bar)
  document.addEventListener("click", (e) => {
    if (e.target.closest("a, button, input, textarea, select, [contenteditable], [data-slide-controls]")) return;
    if (e.shiftKey) show(current - 1, "backward");
    else show(current + 1, "forward");
  });

  // Buttons
  document.querySelector("[data-slide-prev]")?.addEventListener("click", () => show(current - 1, "backward"));
  document.querySelector("[data-slide-next]")?.addEventListener("click", () => show(current + 1, "forward"));

  // Reveal the controls.
  const controlsEl = document.querySelector("[data-slide-controls]");
  if (controlsEl) controlsEl.removeAttribute("hidden");
}

async function init() {
  await waitForMotion();
  const data = await getData();
  renderHero(data.meta || {});
  renderSources(data.meta?.sources || [], data.meta || {});

  const slidesMode = data.meta?.mode === "slides";
  if (slidesMode) {
    document.documentElement.classList.add("story-mode--slides");
    document.body.classList.add("story-mode--slides");
  }

  const story = document.getElementById("story");
  const built = (data.scenes || []).map(s => {
    const node = buildScene(s);
    story.append(node);
    return { node, scene: s, ctrl: null };
  });

  // Wait one frame so layout settles before activating renderers.
  // We use setTimeout(16) rather than requestAnimationFrame because rAF can
  // be starved on very long pages (>10k px) when other scripts (e.g. Vizzu
  // wasm) are still initializing. setTimeout always fires.
  await new Promise(r => setTimeout(r, 16));
  for (const entry of built) {
    const s = entry.scene;
    try {
      if (s.kind === "scrolly")      entry.ctrl = activateScrollyScene(entry.node, s, data, slidesMode);
      else if (s.kind === "bleed")   entry.ctrl = activateBleedScene(entry.node, s, data, slidesMode);
      else if (s.kind === "pinned")  entry.ctrl = activatePinnedScene(entry.node, s, data, slidesMode);
      else if (s.kind === "vizzu")   entry.ctrl = await activateVizzuScene(entry.node, s, data, slidesMode);
      else if (s.kind === "custom")  entry.ctrl = activateCustomScene(entry.node, s, data, slidesMode);
      else                            entry.ctrl = activateSimpleScene(entry.node, s, data, slidesMode);
    } catch (sceneErr) {
      // Don't let one failing scene kill the rest of the page.
      console.error(`[dstory] Scene "${s.id}" failed to activate:`, sceneErr?.message || sceneErr);
    }
  }

  if (slidesMode) setupSlidesController(built, data);
}

// Defer init until DOMContentLoaded so all `<script defer>` scenes have had
// a chance to call STORY.register() (defer scripts execute in document order
// and complete before DOMContentLoaded fires).
if (document.readyState === "complete") {
  // Page already fully loaded — call init directly on next microtask.
  Promise.resolve().then(init);
} else {
  document.addEventListener("DOMContentLoaded", () => init(), { once: true });
}
