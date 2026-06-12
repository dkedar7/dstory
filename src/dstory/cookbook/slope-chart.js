// recipe: slope-chart
// kind: simple
// summary: Two-period comparison — what rose, what fell, and by how much, with direct labels.
//
// Dataset rows: { "<label>": "Product", "<start>": 42, "<end>": 61 }
// scene.config (all optional):
//   { "label": "label", "start": "start", "end": "end",
//     "start_label": "2020", "end_label": "2024",
//     "highlight": ["Product"], "format": "," }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const L = cfg.label || "label", S = cfg.start || "start", E = cfg.end || "end";
  const highlight = new Set(cfg.highlight || []);
  const fmt = d3.format(cfg.format || ",");
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ label: d[L], start: +d[S], end: +d[E] }))
    .filter(d => d.label != null && !isNaN(d.start) && !isNaN(d.end));
  if (!rows.length) { console.warn("[slope-chart] empty dataset:", scene.dataset); return null; }

  const W = 720, H = Math.max(360, rows.length * 44 + 96);
  const margin = { top: 48, right: 170, bottom: 24, left: 170 };
  const w = W - margin.left - margin.right, h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const y = d3.scaleLinear()
    .domain([
      Math.min(0, d3.min(rows, d => Math.min(d.start, d.end))),
      d3.max(rows, d => Math.max(d.start, d.end)),
    ]).nice().range([h, 0]);

  // Period rails + headers
  for (const [px, name] of [[0, cfg.start_label || "Before"], [w, cfg.end_label || "After"]]) {
    g.append("line").attr("x1", px).attr("x2", px).attr("y1", 0).attr("y2", h)
      .attr("stroke", "var(--rule)").attr("stroke-opacity", 0.5);
    g.append("text").attr("class", "annotation").attr("x", px).attr("y", -20)
      .attr("text-anchor", "middle").attr("font-weight", 600).text(name);
  }

  const color = d => highlight.size === 0 || highlight.has(d.label)
    ? "var(--accent)" : "var(--ink-faint)";
  const emphasis = d => highlight.size === 0 || highlight.has(d.label) ? 1 : 0.55;

  // Dodge label rows that would overlap (greedy pass, preserves order).
  function dodge(values, gap) {
    const idx = values.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
    for (let k = 1; k < idx.length; k++) {
      if (idx[k].v - idx[k - 1].v < gap) idx[k].v = idx[k - 1].v + gap;
    }
    const out = new Array(values.length);
    idx.forEach(d => { out[d.i] = d.v; });
    return out;
  }
  const startLabelY = dodge(rows.map(d => y(d.start)), 16);
  const endLabelY   = dodge(rows.map(d => y(d.end)), 16);

  const slope = g.selectAll("g.slope").data(rows).join("g").attr("class", "slope");
  slope.append("line")
    .attr("x1", 0).attr("y1", d => y(d.start))
    .attr("x2", REDUCE ? w : 0).attr("y2", d => y(REDUCE ? d.end : d.start))
    .attr("stroke", color).attr("stroke-width", 2).attr("opacity", emphasis)
    .transition().duration(REDUCE ? 0 : 800).ease(d3.easeCubicOut)
    .attr("x2", w).attr("y2", d => y(d.end));
  slope.append("circle").attr("cx", 0).attr("cy", d => y(d.start)).attr("r", 3.5)
    .attr("fill", color).attr("opacity", emphasis);
  slope.append("circle").attr("cx", w).attr("cy", d => y(d.end)).attr("r", 3.5)
    .attr("fill", color).attr("opacity", 0)
    .transition().delay(REDUCE ? 0 : 700).duration(200).attr("opacity", emphasis);

  slope.append("text").attr("class", "annotation")
    .attr("x", -10).attr("y", (d, i) => startLabelY[i]).attr("dy", "0.32em")
    .attr("text-anchor", "end").attr("opacity", emphasis)
    .text(d => `${d.label}  ${fmt(d.start)}`);
  slope.append("text").attr("class", "annotation annotation--strong")
    .attr("x", w + 10).attr("y", (d, i) => endLabelY[i]).attr("dy", "0.32em")
    .attr("fill", color).attr("opacity", 0)
    .text(d => `${fmt(d.end)}  ${d.label}`)
    .transition().delay(REDUCE ? 0 : 750).duration(300).attr("opacity", emphasis);

  return null;
});
