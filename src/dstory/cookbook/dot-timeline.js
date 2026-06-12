// recipe: dot-timeline
// kind: simple
// summary: Events on a time axis with alternating stems — the shape of a history at a glance.
//
// Dataset rows: { "<x>": "2007-06-29", "<label>": "iPhone launches" }
// scene.config (all optional):
//   { "x": "date", "label": "label", "parse": "%Y-%m-%d",
//     "highlight": ["iPhone launches"], "tick_format": "%Y" }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const X = cfg.x || "date", L = cfg.label || "label";
  const parse = d3.utcParse(cfg.parse || "%Y-%m-%d");
  const tickFmt = d3.utcFormat(cfg.tick_format || "%Y");
  const highlight = new Set(cfg.highlight || []);
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ x: typeof d[X] === "string" ? parse(d[X]) : d[X], label: d[L] }))
    .filter(d => d.x != null && d.label != null)
    .sort((a, b) => a.x - b.x);
  if (!rows.length) { console.warn("[dot-timeline] empty dataset:", scene.dataset); return null; }

  const W = 760, H = 320;
  const margin = { top: 24, right: 48, bottom: 24, left: 48 };
  const w = W - margin.left - margin.right;
  const mid = (H - margin.top - margin.bottom) / 2;
  const stem = 64;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleUtc().domain(d3.extent(rows, d => d.x)).range([0, w]).nice();

  g.append("line").attr("x1", 0).attr("x2", w).attr("y1", mid).attr("y2", mid)
    .attr("stroke", "var(--rule)");
  g.append("g").attr("transform", `translate(0,${mid + 8})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(tickFmt).tickSize(0).tickPadding(14))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  const isHero = d => highlight.size === 0 || highlight.has(d.label);
  const ev = g.selectAll("g.event").data(rows).join("g").attr("class", "event")
    .attr("transform", d => `translate(${x(d.x)},${mid})`);

  // Alternate stems up/down to avoid label collisions.
  const dir = (_, i) => (i % 2 === 0 ? -1 : 1);
  ev.append("line")
    .attr("y1", 0).attr("y2", 0)
    .attr("stroke", d => isHero(d) ? "var(--accent)" : "var(--ink-faint)")
    .attr("stroke-width", 1)
    .transition().duration(REDUCE ? 0 : 450).delay((_, i) => REDUCE ? 0 : i * 90)
    .attr("y2", (d, i) => dir(d, i) * stem);
  ev.append("circle").attr("r", 0)
    .attr("fill", d => isHero(d) ? "var(--accent)" : "var(--ink-soft)")
    .transition().duration(REDUCE ? 0 : 300).delay((_, i) => REDUCE ? 0 : i * 90)
    .attr("r", d => isHero(d) ? 6 : 4);
  ev.append("text")
    .attr("class", d => isHero(d) ? "annotation annotation--strong" : "annotation")
    .attr("y", (d, i) => dir(d, i) * (stem + 12))
    .attr("dy", (d, i) => (dir(d, i) < 0 ? "0" : "0.7em"))
    .attr("text-anchor", "middle")
    .attr("opacity", 0)
    .text(d => d.label)
    .transition().duration(REDUCE ? 0 : 300).delay((_, i) => REDUCE ? 0 : i * 90 + 250)
    .attr("opacity", d => isHero(d) ? 1 : 0.75);
  ev.append("text").attr("class", "annotation")
    .attr("y", (d, i) => dir(d, i) * (stem + 26))
    .attr("dy", (d, i) => (dir(d, i) < 0 ? "0" : "0.7em"))
    .attr("text-anchor", "middle")
    .attr("opacity", 0)
    .attr("fill", "var(--ink-faint)")
    .text(d => tickFmt(d.x))
    .transition().duration(REDUCE ? 0 : 300).delay((_, i) => REDUCE ? 0 : i * 90 + 320)
    .attr("opacity", 0.8);

  return null;
});
