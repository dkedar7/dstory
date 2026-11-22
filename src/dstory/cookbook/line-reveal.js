// recipe: line-reveal
// kind: simple
// summary: A line chart that draws itself in, with direct end-labeling and an optional annotation.
//
// Dataset rows: { "<x>": "2024-01-15", "<y>": 1234 }   (x parses as %Y-%m-%d by default)
// scene.config (all optional):
//   { "x": "date", "y": "value", "parse": "%Y-%m-%d", "format": ",.2s" }
// scene.annotation (optional): { "x": "2024-03-15", "y": 4200000, "text": "The spike" }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const X = cfg.x || "date", Y = cfg.y || "value";
  const FMT = cfg.parse || "%Y-%m-%d";
  // Fall back to an ISO 8601 timestamp ("2024-01-01T00:00:00", as to_records()
  // wrote before 0.14.6), read as UTC like the format itself (#43).
  const isoT = d3.utcParse("%Y-%m-%dT%H:%M:%S");
  const iso = s => /^\d{4}-\d\d-\d\dT/.test(s) ? (isoT(s) ?? d3.isoParse(s)) : null;
  const fmtParse = d3.utcParse(FMT);
  const parse = s => fmtParse(s) ?? iso(s);
  const fmt = d3.format(cfg.format || ",.2s");
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const src = data.datasets?.[scene.dataset] || [];
  const rows = src.map(d => ({
    x: typeof d[X] === "string" ? parse(d[X]) : d[X],
    y: +d[Y],
  })).filter(d => d.x != null && !isNaN(d.y));
  if (!rows.length) {
    if (src.length) console.warn(`[line-reveal] ${src.length} rows in dataset ${scene.dataset}, none with a ${X} that parses as ${FMT} and a numeric ${Y}: e.g. ${JSON.stringify(src[0])}`);
    else console.warn("[line-reveal] empty dataset:", scene.dataset);
    return null;
  }

  const W = 720, H = 400;
  const margin = { top: 24, right: 88, bottom: 36, left: 56 };
  const w = W - margin.left - margin.right, h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleUtc().domain(d3.extent(rows, d => d.x)).range([0, w]);
  const y = d3.scaleLinear().domain([0, d3.max(rows, d => d.y)]).nice().range([h, 0]);

  g.append("g")
    .call(d3.axisLeft(y).ticks(4).tickSize(-w).tickFormat(""))
    .call(s => s.select(".domain").remove())
    .selectAll("line").attr("stroke", "var(--rule)").attr("stroke-opacity", 0.3);
  g.append("g").attr("transform", `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(6))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");
  g.append("g")
    .call(d3.axisLeft(y).ticks(4).tickFormat(fmt))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  const line = d3.line().x(d => x(d.x)).y(d => y(d.y)).curve(d3.curveMonotoneX);
  const path = g.append("path").datum(rows)
    .attr("fill", "none").attr("stroke", "var(--accent)").attr("stroke-width", 2.5)
    .attr("d", line);

  const total = path.node().getTotalLength();
  path.attr("stroke-dasharray", total).attr("stroke-dashoffset", REDUCE ? 0 : total)
    .transition().duration(REDUCE ? 0 : 1200).ease(d3.easeCubicOut)
    .attr("stroke-dashoffset", 0);

  const last = rows[rows.length - 1];
  g.append("text").attr("class", "annotation annotation--strong")
    .attr("x", x(last.x) + 8).attr("y", y(last.y)).attr("dy", "0.32em")
    .attr("opacity", 0).text(fmt(last.y))
    .transition().delay(REDUCE ? 0 : 1100).duration(400).attr("opacity", 1);

  const a = scene.annotation;
  if (a && a.text) {
    const ax = typeof a.x === "string" ? parse(a.x) : a.x;
    g.append("circle").attr("cx", x(ax)).attr("cy", y(+a.y)).attr("r", 0)
      .attr("fill", "var(--accent)")
      .transition().delay(REDUCE ? 0 : 1200).duration(400).attr("r", 5);
    g.append("text").attr("class", "annotation annotation--strong")
      .attr("x", x(ax)).attr("y", y(+a.y) - 14).attr("text-anchor", "middle")
      .attr("opacity", 0).text(a.text)
      .transition().delay(REDUCE ? 0 : 1400).duration(400).attr("opacity", 1);
  }
  return null;
});
