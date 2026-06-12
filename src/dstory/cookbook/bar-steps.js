// recipe: bar-steps
// kind: scrolly
// summary: A sticky bar chart where each scroll step spotlights a different bar.
//
// Dataset rows: { "<label>": "Product", "<y>": -38 }   (positive or negative)
// scene.steps[i].state (optional): a bar label to spotlight; defaults to bar i.
// scene.config (all optional):
//   { "label": "label", "y": "value", "format": "" }   (format e.g. "+" → "+12")
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const L = cfg.label || "label", Y = cfg.y || "value";
  const fmt = d3.format(cfg.format || "");
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ label: d[L], y: +d[Y] }))
    .filter(d => d.label != null && !isNaN(d.y));
  if (!rows.length) { console.warn("[bar-steps] empty dataset:", scene.dataset); return null; }
  const labels = rows.map(d => d.label);

  const W = 520, H = 380;
  const margin = { top: 24, right: 16, bottom: 36, left: 56 };
  const w = W - margin.left - margin.right, h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("width", "100%").attr("height", "100%")
    .attr("aria-hidden", "true");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(labels).range([0, w]).padding(0.3);
  const yMax = d3.max(rows, d => Math.abs(d.y)) || 1;
  const hasNeg = rows.some(d => d.y < 0);
  const y = d3.scaleLinear()
    .domain(hasNeg ? [-yMax, yMax] : [0, yMax]).nice().range([h, 0]);

  g.append("line")
    .attr("x1", 0).attr("x2", w).attr("y1", y(0)).attr("y2", y(0))
    .attr("stroke", "var(--rule)").attr("stroke-opacity", 0.6);

  const bars = g.selectAll("rect.bar").data(rows).join("rect").attr("class", "bar")
    .attr("x", d => x(d.label)).attr("width", x.bandwidth())
    .attr("y", d => Math.min(y(0), y(d.y)))
    .attr("height", d => Math.abs(y(d.y) - y(0)))
    .attr("fill", "var(--ink-faint)").attr("opacity", 0.5);

  const valueLabels = g.selectAll("text.val").data(rows).join("text")
    .attr("class", "val annotation annotation--strong")
    .attr("x", d => x(d.label) + x.bandwidth() / 2)
    .attr("y", d => (d.y >= 0 ? y(d.y) - 8 : y(d.y) + 16))
    .attr("text-anchor", "middle")
    .attr("opacity", 0)
    .text(d => fmt(d.y));

  // Category labels sit at the zero line, on the side the bar does NOT
  // occupy — the standard diverging-bar treatment, and it keeps them clear
  // of the value labels at the bar ends.
  g.selectAll("text.cat").data(rows).join("text")
    .attr("class", "cat annotation")
    .attr("x", d => x(d.label) + x.bandwidth() / 2)
    .attr("y", d => (d.y >= 0 ? y(0) + 16 : y(0) - 8))
    .attr("text-anchor", "middle")
    .text(d => d.label);
  g.append("g")
    .call(d3.axisLeft(y).ticks(5).tickFormat(fmt))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  function spotlight(i) {
    const step = (scene.steps || [])[i];
    const target = step && step.state ? labels.indexOf(step.state) : i;
    bars.transition().duration(REDUCE ? 0 : 450).ease(d3.easeCubicOut)
      .attr("fill", (_, idx) => idx === target ? "var(--accent)" : "var(--ink-faint)")
      .attr("opacity", (_, idx) => idx === target ? 1 : 0.35);
    valueLabels.transition().duration(REDUCE ? 0 : 450)
      .attr("opacity", (_, idx) => idx === target ? 1 : 0);
  }

  return { onStep(i) { spotlight(i); } };
});
