// Example: a line chart that draws itself in on enter, with a single annotated outlier.
// Pattern: simple "scene-on-enter" reveal — not scrolly, just one impactful chart.
//
// Wire-up in index.html: <script src="scenes/example-line-reveal.js" defer></script>
//
// Scene JSON:
//   {
//     "id": "scene-trend",
//     "kind": "simple",
//     "headline": "The trend was clear by March",
//     "commentary": "After two flat years, monthly volume tripled in a single quarter.",
//     "source_line": "Source: Internal weekly metrics, Jan 2022 – Jun 2024",
//     "dataset": "trend",
//     "annotation": { "date": "2024-03-15", "value": 4200000, "text": "Spike: $4.2M, 3× the prior month" }
//   }

STORY.register("scene-trend", function draw(mount, data, scene) {
  const dataset = (data.datasets?.[scene.dataset] || []).map(d => ({
    date: typeof d.date === "string" ? d3.utcParse("%Y-%m-%d")(d.date) : d.date,
    value: +d.value,
  }));
  if (!dataset.length) return null;

  const W = 720, H = 360;
  const margin = { top: 24, right: 96, bottom: 32, left: 56 };
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("role", "img")
    .attr("aria-label", scene.headline || "Trend chart")
    .style("width", "100%")
    .style("height", "auto")
    .style("display", "block");

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleUtc().domain(d3.extent(dataset, d => d.date)).range([0, w]);
  const y = d3.scaleLinear().domain([0, d3.max(dataset, d => d.value)]).nice().range([h, 0]);

  // Faint gridlines
  g.append("g").attr("class", "grid")
    .call(d3.axisLeft(y).ticks(4).tickSize(-w).tickFormat(""))
    .call(g => g.select(".domain").remove())
    .selectAll("line").attr("stroke", "var(--rule)").attr("stroke-opacity", 0.3);

  // Axes
  g.append("g").attr("transform", `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(d3.utcFormat("%b %Y")))
    .call(g => g.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");
  g.append("g")
    .call(d3.axisLeft(y).ticks(4).tickFormat(d3.format("$.2s")))
    .call(g => g.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  // Line
  const line = d3.line().x(d => x(d.date)).y(d => y(d.value)).curve(d3.curveMonotoneX);
  const path = g.append("path")
    .datum(dataset)
    .attr("fill", "none")
    .attr("stroke", "var(--accent)")
    .attr("stroke-width", 2)
    .attr("d", line);

  // Reveal animation
  const total = path.node().getTotalLength();
  path.attr("stroke-dasharray", total).attr("stroke-dashoffset", total)
    .transition().duration(1200).ease(d3.easeCubicOut)
    .attr("stroke-dashoffset", 0);

  // End-of-line label (direct labeling)
  const last = dataset[dataset.length - 1];
  g.append("text")
    .attr("class", "annotation annotation--strong")
    .attr("x", x(last.date) + 8)
    .attr("y", y(last.value))
    .attr("dy", "0.32em")
    .attr("opacity", 0)
    .text(d3.format("$,.2s")(last.value))
    .transition().delay(1100).duration(400).attr("opacity", 1);

  // Annotation
  if (scene.annotation) {
    const a = scene.annotation;
    const ad = d3.utcParse("%Y-%m-%d")(a.date);
    g.append("circle")
      .attr("cx", x(ad)).attr("cy", y(a.value)).attr("r", 0)
      .attr("fill", "var(--accent)")
      .transition().delay(1200).duration(400).attr("r", 5);

    g.append("text")
      .attr("class", "annotation annotation--strong")
      .attr("x", x(ad)).attr("y", y(a.value) - 14)
      .attr("text-anchor", "middle")
      .attr("opacity", 0)
      .text(a.text)
      .transition().delay(1400).duration(400).attr("opacity", 1);
  }

  return null;
});
