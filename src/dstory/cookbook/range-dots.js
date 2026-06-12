// recipe: range-dots
// kind: simple
// summary: Dumbbell rows — a before→after range per category, sorted by change.
//
// Dataset rows: { "<label>": "Norway", "<start>": 74.2, "<end>": 81.2 }
// scene.config (all optional):
//   { "label": "label", "start": "start", "end": "end",
//     "start_label": "1990", "end_label": "2020",
//     "highlight": ["Norway"], "format": ",", "sort": "delta" }   // "delta" | "end" | "none"
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const L = cfg.label || "label", S = cfg.start || "start", E = cfg.end || "end";
  const highlight = new Set(cfg.highlight || []);
  const fmt = d3.format(cfg.format || ",");
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  let rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ label: d[L], start: +d[S], end: +d[E] }))
    .filter(d => d.label != null && !isNaN(d.start) && !isNaN(d.end));
  if (!rows.length) { console.warn("[range-dots] empty dataset:", scene.dataset); return null; }

  const sort = cfg.sort || "delta";
  if (sort === "delta") rows = rows.slice().sort((a, b) => (b.end - b.start) - (a.end - a.start));
  else if (sort === "end") rows = rows.slice().sort((a, b) => b.end - a.end);

  const rowH = 36;
  const W = 720, H = rows.length * rowH + 88;
  const margin = { top: 48, right: 64, bottom: 32, left: 150 };
  const w = W - margin.left - margin.right;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear()
    .domain([
      d3.min(rows, d => Math.min(d.start, d.end)),
      d3.max(rows, d => Math.max(d.start, d.end)),
    ]).nice().range([0, w]);
  const y = (_, i) => i * rowH + rowH / 2;

  g.append("g").attr("transform", `translate(0,${rows.length * rowH + 8})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(fmt))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  // Start/end key, top-right.
  const key = g.append("g").attr("transform", `translate(${w - 150},-28)`);
  key.append("circle").attr("cx", 0).attr("r", 4.5)
    .attr("fill", "none").attr("stroke", "var(--ink-soft)").attr("stroke-width", 1.5);
  key.append("text").attr("class", "annotation").attr("x", 9).attr("dy", "0.32em")
    .text(cfg.start_label || "before");
  key.append("circle").attr("cx", 80).attr("r", 4.5).attr("fill", "var(--accent)");
  key.append("text").attr("class", "annotation").attr("x", 89).attr("dy", "0.32em")
    .text(cfg.end_label || "after");

  const emphasis = d => highlight.size === 0 || highlight.has(d.label) ? 1 : 0.45;
  const row = g.selectAll("g.row").data(rows).join("g").attr("class", "row")
    .attr("transform", (d, i) => `translate(0,${y(d, i)})`)
    .attr("opacity", emphasis);

  row.append("text").attr("class", "annotation")
    .attr("x", -12).attr("dy", "0.32em").attr("text-anchor", "end")
    .attr("font-weight", d => highlight.has(d.label) ? 600 : 400)
    .text(d => d.label);

  row.append("line")
    .attr("x1", d => x(d.start)).attr("x2", d => x(REDUCE ? d.end : d.start))
    .attr("stroke", "var(--ink-faint)").attr("stroke-width", 2)
    .transition().duration(REDUCE ? 0 : 700).delay((_, i) => REDUCE ? 0 : i * 60)
    .ease(d3.easeCubicOut)
    .attr("x2", d => x(d.end));

  row.append("circle")
    .attr("cx", d => x(d.start)).attr("r", 4.5)
    .attr("fill", "var(--bg)").attr("stroke", "var(--ink-soft)").attr("stroke-width", 1.5);
  row.append("circle")
    .attr("cx", d => x(REDUCE ? d.end : d.start)).attr("r", 4.5)
    .attr("fill", "var(--accent)")
    .transition().duration(REDUCE ? 0 : 700).delay((_, i) => REDUCE ? 0 : i * 60)
    .ease(d3.easeCubicOut)
    .attr("cx", d => x(d.end));

  row.append("text").attr("class", "annotation annotation--strong")
    .attr("x", d => x(d.end) + (d.end >= d.start ? 10 : -10))
    .attr("text-anchor", d => (d.end >= d.start ? "start" : "end"))
    .attr("dy", "0.32em").attr("opacity", 0)
    .text(d => fmt(d.end))
    .transition().delay((_, i) => REDUCE ? 0 : i * 60 + 650).duration(250)
    .attr("opacity", emphasis);

  return null;
});
