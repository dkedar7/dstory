// recipe: small-multiples
// kind: simple
// summary: One mini line chart per series, shared scales — comparison without spaghetti.
//
// Dataset rows (long format): { "<x>": "2021", "<series>": "Norway", "<y>": 81.2 }
// scene.config (all optional):
//   { "x": "x", "series": "series", "y": "y",
//     "columns": 4, "parse": null,           // set parse (e.g. "%Y-%m-%d") for date x
//     "highlight": ["Norway"], "format": ",",
//     "scale": "shared" }                    // "independent": each panel gets its own
//                                            // y-axis, labelled with its min and max
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

  // Shared scales by default: honest comparison across panels. "independent"
  // gives each panel its own y-range (for series of very different sizes or
  // units) and labels that range, so the reader compares shapes, not heights.
  const independent = cfg.scale === "independent";
  const gutter = independent ? 34 : 0;
  const xDomain = d3.extent(raw, d => d.x);
  const xScale = (parse ? d3.scaleUtc() : d3.scaleLinear())
    .domain(xDomain).range([gutter, cellW - 8]);
  const yFor = rows => {
    let [lo, hi] = d3.extent(rows, d => d.y);
    if (!independent) lo = Math.min(0, lo);
    else {
      // Its own range, but never so tight that a 1% wobble fills the panel.
      const minSpan = 0.1 * Math.max(Math.abs(lo), Math.abs(hi));
      if (hi - lo < minSpan) { const mid = (hi + lo) / 2; lo = mid - minSpan / 2; hi = mid + minSpan / 2; }
      if (lo >= 0 && lo - (hi - lo) * 0.25 < 0) lo = 0;   // near zero: keep the baseline
    }
    return d3.scaleLinear().domain([lo, hi]).nice().range([cellH - 28, 8]);
  };
  const shared = yFor(raw);

  names.forEach((name, i) => {
    const px = (i % cols) * (cellW + gapX) + 8;
    const py = Math.floor(i / cols) * (cellH + gapY) + 8;
    const cell = svg.append("g").attr("transform", `translate(${px},${py})`);
    const pts = bySeries.get(name).slice().sort((a, b) => a.x - b.x);
    const hero = highlight.size === 0 || highlight.has(name);
    const yScale = independent ? yFor(pts) : shared;
    const line = d3.line().x(d => xScale(d.x)).y(d => yScale(d.y)).curve(d3.curveMonotoneX);
    if (independent) {
      const [lo, hi] = yScale.domain();
      [[hi, 8], [lo, cellH - 28]].forEach(([v, y]) => cell.append("text")
        .attr("class", "annotation scale-tick")
        .attr("x", gutter - 6).attr("y", y).attr("dy", "0.32em")
        .attr("text-anchor", "end").attr("fill", "var(--ink-faint)")
        .style("font-size", "10px").text(fmt(v)));
    }

    cell.append("line")
      .attr("x1", gutter).attr("x2", cellW - 8)
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
