// recipe: small-multiples
// kind: simple
// summary: One mini line chart per series, shared scales — comparison without spaghetti.
//
// Dataset rows (long format): { "<x>": "2021", "<series>": "Norway", "<y>": 81.2 }
// scene.config (all optional):
//   { "x": "x", "series": "series", "y": "y",
//     "columns": 4, "parse": null,           // set parse (e.g. "%Y-%m-%d") for date x
//     "highlight": ["Norway"], "format": "," }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const X = cfg.x || "x", S = cfg.series || "series", Y = cfg.y || "y";
  const highlight = new Set(cfg.highlight || []);
  const fmt = d3.format(cfg.format || ",");
  const parse = cfg.parse ? d3.utcParse(cfg.parse) : null;
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const raw = (data.datasets?.[scene.dataset] || [])
    .map(d => ({
      x: parse ? (typeof d[X] === "string" ? parse(d[X]) : d[X]) : +d[X],
      series: d[S], y: +d[Y],
    }))
    .filter(d => d.x != null && !isNaN(d.y) && d.series != null);
  if (!raw.length) { console.warn("[small-multiples] empty dataset:", scene.dataset); return null; }

  const bySeries = d3.group(raw, d => d.series);
  const names = [...bySeries.keys()];
  const cols = cfg.columns || Math.min(4, Math.ceil(Math.sqrt(names.length)));
  const rowsN = Math.ceil(names.length / cols);

  const cellW = 170, cellH = 120, gapX = 24, gapY = 36;
  const W = cols * cellW + (cols - 1) * gapX + 16;
  const H = rowsN * cellH + (rowsN - 1) * gapY + 24;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");

  // Shared scales: honest comparison across panels.
  const xDomain = parse ? d3.extent(raw, d => d.x) : d3.extent(raw, d => d.x);
  const xScale = (parse ? d3.scaleUtc() : d3.scaleLinear())
    .domain(xDomain).range([0, cellW - 8]);
  const yScale = d3.scaleLinear()
    .domain([Math.min(0, d3.min(raw, d => d.y)), d3.max(raw, d => d.y)]).nice()
    .range([cellH - 28, 8]);
  const line = d3.line().x(d => xScale(d.x)).y(d => yScale(d.y)).curve(d3.curveMonotoneX);

  names.forEach((name, i) => {
    const px = (i % cols) * (cellW + gapX) + 8;
    const py = Math.floor(i / cols) * (cellH + gapY) + 8;
    const cell = svg.append("g").attr("transform", `translate(${px},${py})`);
    const pts = bySeries.get(name).slice().sort((a, b) => a.x - b.x);
    const hero = highlight.size === 0 || highlight.has(name);

    cell.append("line")
      .attr("x1", 0).attr("x2", cellW - 8)
      .attr("y1", cellH - 28).attr("y2", cellH - 28)
      .attr("stroke", "var(--rule)").attr("stroke-opacity", 0.5);

    cell.append("text").attr("class", "annotation")
      .attr("x", 0).attr("y", cellH - 10)
      .attr("font-weight", hero ? 600 : 400)
      .attr("fill", hero ? "var(--ink)" : "var(--ink-soft)")
      .text(name);

    const p = cell.append("path").datum(pts)
      .attr("fill", "none")
      .attr("stroke", hero ? "var(--accent)" : "var(--ink-faint)")
      .attr("stroke-width", hero ? 2.25 : 1.5)
      .attr("d", line);
    if (!REDUCE) {
      const total = p.node().getTotalLength();
      p.attr("stroke-dasharray", total).attr("stroke-dashoffset", total)
        .transition().duration(800).delay(i * 70).ease(d3.easeCubicOut)
        .attr("stroke-dashoffset", 0);
    }

    const last = pts[pts.length - 1];
    cell.append("circle")
      .attr("cx", xScale(last.x)).attr("cy", yScale(last.y)).attr("r", 2.5)
      .attr("fill", hero ? "var(--accent)" : "var(--ink-faint)");
    cell.append("text").attr("class", "annotation")
      .attr("x", xScale(last.x)).attr("y", yScale(last.y) - 7)
      .attr("text-anchor", "end")
      .attr("fill", hero ? "var(--accent)" : "var(--ink-faint)")
      .text(fmt(last.y));
  });

  return null;
});
