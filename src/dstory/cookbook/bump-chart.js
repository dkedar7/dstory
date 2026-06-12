// recipe: bump-chart
// kind: simple
// summary: Rank over time — who overtook whom, with end labels and a highlight set.
//
// Dataset rows (long format): { "<x>": "2021", "<series>": "Python", "<y>": 48.2 }
// Rank is computed per period from <y> (1 = highest value).
// scene.config (all optional):
//   { "x": "period", "series": "name", "y": "value", "highlight": ["Python"] }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const X = cfg.x || "period", S = cfg.series || "name", Y = cfg.y || "value";
  const highlight = new Set(cfg.highlight || []);
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const raw = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ x: String(d[X]), series: d[S], y: +d[Y] }))
    .filter(d => d.series != null && !isNaN(d.y));
  if (!raw.length) { console.warn("[bump-chart] empty dataset:", scene.dataset); return null; }

  // Rank within each period (1 = highest value).
  const periods = [...new Set(raw.map(d => d.x))];
  for (const p of periods) {
    const inP = raw.filter(d => d.x === p).sort((a, b) => b.y - a.y);
    inP.forEach((d, i) => { d.rank = i + 1; });
  }
  const bySeries = d3.group(raw, d => d.series);
  const nRanks = d3.max(raw, d => d.rank);

  const W = 720, H = Math.max(320, nRanks * 44 + 80);
  const margin = { top: 24, right: 130, bottom: 36, left: 130 };
  const w = W - margin.left - margin.right, h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scalePoint().domain(periods).range([0, w]);
  const y = d3.scalePoint().domain(d3.range(1, nRanks + 1)).range([0, h]);

  g.append("g").attr("transform", `translate(0,${h + 16})`)
    .call(d3.axisBottom(x).tickSize(0))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  const emphasized = s => highlight.size === 0 || highlight.has(s);
  const seriesNames = [...bySeries.keys()];
  const palette = seriesNames.map((_, i) => `var(--cat-${(i % 7) + 1})`);
  const color = s => emphasized(s)
    ? (highlight.size ? "var(--accent)" : palette[seriesNames.indexOf(s)])
    : "var(--ink-faint)";

  const line = d3.line()
    .x(d => x(d.x)).y(d => y(d.rank)).curve(d3.curveMonotoneX);

  for (const [name, points] of bySeries) {
    points.sort((a, b) => periods.indexOf(a.x) - periods.indexOf(b.x));
    const p = g.append("path").datum(points)
      .attr("fill", "none")
      .attr("stroke", color(name))
      .attr("stroke-width", emphasized(name) ? 3 : 1.5)
      .attr("opacity", emphasized(name) ? 1 : 0.45)
      .attr("d", line);
    if (!REDUCE) {
      const total = p.node().getTotalLength();
      p.attr("stroke-dasharray", total).attr("stroke-dashoffset", total)
        .transition().duration(1000).ease(d3.easeCubicOut).attr("stroke-dashoffset", 0);
    }
    g.selectAll(null).data(points).join("circle")
      .attr("cx", d => x(d.x)).attr("cy", d => y(d.rank)).attr("r", 4)
      .attr("fill", color(name)).attr("opacity", emphasized(name) ? 1 : 0.45);

    const first = points[0], lastP = points[points.length - 1];
    g.append("text").attr("class", "annotation")
      .attr("x", x(first.x) - 10).attr("y", y(first.rank)).attr("dy", "0.32em")
      .attr("text-anchor", "end").attr("fill", color(name))
      .attr("font-weight", emphasized(name) ? 600 : 400)
      .attr("opacity", emphasized(name) ? 1 : 0.6)
      .text(`${first.rank}. ${name}`);
    g.append("text").attr("class", "annotation")
      .attr("x", x(lastP.x) + 10).attr("y", y(lastP.rank)).attr("dy", "0.32em")
      .attr("fill", color(name))
      .attr("font-weight", emphasized(name) ? 600 : 400)
      .attr("opacity", emphasized(name) ? 1 : 0.6)
      .text(`${lastP.rank}. ${name}`);
  }
  return null;
});
