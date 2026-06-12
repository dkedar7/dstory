// recipe: annotated-scatter
// kind: simple
// summary: An x/y scatter where the points that matter are named and the rest fade back.
//
// Dataset rows: { "<x>": 12.4, "<y>": 81.2, "<label>": "Norway" }
// scene.config (all optional):
//   { "x": "x", "y": "y", "label": "label",
//     "annotate": ["Norway", "Chad"],          // named → accent + label; others fade
//     "x_label": "GDP per capita ($k)", "y_label": "Life expectancy",
//     "x_format": ",", "y_format": "," }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const X = cfg.x || "x", Y = cfg.y || "y", L = cfg.label || "label";
  const annotate = new Set(cfg.annotate || []);
  const fx = d3.format(cfg.x_format || ",");
  const fy = d3.format(cfg.y_format || ",");
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ x: +d[X], y: +d[Y], label: d[L] }))
    .filter(d => !isNaN(d.x) && !isNaN(d.y));
  if (!rows.length) { console.warn("[annotated-scatter] empty dataset:", scene.dataset); return null; }

  const W = 720, H = 440;
  const margin = { top: 24, right: 32, bottom: 52, left: 60 };
  const w = W - margin.left - margin.right, h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear().domain(d3.extent(rows, d => d.x)).nice().range([0, w]);
  const y = d3.scaleLinear().domain(d3.extent(rows, d => d.y)).nice().range([h, 0]);

  g.append("g")
    .call(d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(""))
    .call(s => s.select(".domain").remove())
    .selectAll("line").attr("stroke", "var(--rule)").attr("stroke-opacity", 0.25);
  g.append("g").attr("transform", `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(fx))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");
  g.append("g")
    .call(d3.axisLeft(y).ticks(5).tickFormat(fy))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  if (cfg.x_label) {
    g.append("text").attr("class", "annotation")
      .attr("x", w).attr("y", h + 40).attr("text-anchor", "end").text(cfg.x_label);
  }
  if (cfg.y_label) {
    g.append("text").attr("class", "annotation")
      .attr("x", 0).attr("y", -10).text(cfg.y_label);
  }

  const isHero = d => annotate.has(d.label);
  g.selectAll("circle.pt").data(rows).join("circle").attr("class", "pt")
    .attr("cx", d => x(d.x)).attr("cy", d => y(d.y))
    .attr("fill", d => isHero(d) ? "var(--accent)" : "var(--ink-faint)")
    .attr("fill-opacity", d => isHero(d) ? 1 : 0.45)
    .attr("r", 0)
    .transition().duration(REDUCE ? 0 : 500).delay((_, i) => REDUCE ? 0 : i * 4)
    .ease(d3.easeCubicOut)
    .attr("r", d => isHero(d) ? 7 : 4.5);

  // Callout placement: above the point unless that runs off the top, then
  // below; anchored away from the plot edges; finally a greedy dodge pass so
  // heroes that sit near each other don't overprint.
  const callouts = rows.filter(isHero).map(d => ({
    label: d.label,
    x: x(d.x),
    y: y(d.y) - 12 < 14 ? y(d.y) + 22 : y(d.y) - 12,
    anchor: x(d.x) < w * 0.08 ? "start" : x(d.x) > w * 0.92 ? "end" : "middle",
  })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < callouts.length; k++) {
    const prev = callouts[k - 1], cur = callouts[k];
    if (Math.abs(cur.x - prev.x) < 90 && cur.y - prev.y < 15) cur.y = prev.y + 16;
  }
  g.selectAll("text.callout").data(callouts).join("text")
    .attr("class", "callout annotation annotation--strong")
    .attr("x", d => d.x).attr("y", d => d.y)
    .attr("text-anchor", d => d.anchor)
    .attr("opacity", 0).text(d => d.label)
    .transition().delay(REDUCE ? 0 : 500).duration(300).attr("opacity", 1);

  return null;
});
