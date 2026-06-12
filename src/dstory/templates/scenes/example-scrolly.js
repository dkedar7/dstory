// Example: a scrolly scene with a bar chart that highlights different bars on each step.
// Author rewrites this for the actual story; this file shows the registration pattern.
//
// Wire-up in index.html: <script src="scenes/example-scrolly.js" defer></script>
// (Plain script, NOT type="module" — so the bundler can inline cleanly into one file.)
//
// Scene JSON in data.json:
//   {
//     "id": "scene-bars",
//     "kind": "scrolly",
//     "headline": "Where the layoffs landed",
//     "steps": [
//       { "headline": "Product took the hardest hit", "commentary": "Product roles fell 38% in Q1." },
//       { "headline": "Engineering held steady", "commentary": "Down only 4% — the smallest drop." },
//       { "headline": "But sales reversed in Q2", "commentary": "After a sharp dip, sales rebounded above start." }
//     ],
//     "source_line": "Source: Layoffs.fyi, Jan–Jun 2024",
//     "dataset": "departments"
//   }
//
// data.json datasets.departments:
//   [{ "label": "Product", "value": -38 }, { "label": "Eng", "value": -4 }, { "label": "Sales", "value": 12 }]

STORY.register("scene-bars", function draw(mount, data, scene) {
  const dataset = data.datasets?.[scene.dataset] || [];
  const W = 520, H = 360;
  const margin = { top: 16, right: 16, bottom: 32, left: 64 };
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("width", "100%")
    .attr("height", "100%")
    .attr("role", "img")
    .attr("aria-label", scene.headline || "Bar chart");

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(dataset.map(d => d.label)).range([0, w]).padding(0.3);
  const yMax = d3.max(dataset, d => Math.abs(d.value)) || 1;
  const y = d3.scaleLinear().domain([-yMax, yMax]).nice().range([h, 0]);

  // Zero rule
  g.append("line")
    .attr("x1", 0).attr("x2", w)
    .attr("y1", y(0)).attr("y2", y(0))
    .attr("stroke", "var(--rule)").attr("stroke-opacity", 0.6);

  // Bars
  const bars = g.selectAll("rect.bar").data(dataset).join("rect")
    .attr("class", "bar")
    .attr("x", d => x(d.label))
    .attr("width", x.bandwidth())
    .attr("y", d => Math.min(y(0), y(d.value)))
    .attr("height", d => Math.abs(y(d.value) - y(0)))
    .attr("fill", "var(--ink-faint)")
    .attr("opacity", 0.5);

  // X labels
  g.append("g").attr("transform", `translate(0,${h})`)
    .call(d3.axisBottom(x).tickSize(0).tickPadding(8))
    .call(g => g.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  // Y axis
  g.append("g")
    .call(d3.axisLeft(y).ticks(5).tickFormat(d => `${d}%`))
    .call(g => g.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");

  // Step → highlighted bar index
  function highlight(i) {
    bars.transition().duration(450).ease(d3.easeCubicOut)
      .attr("fill", (_, idx) => idx === i ? "var(--accent)" : "var(--ink-faint)")
      .attr("opacity", (_, idx) => idx === i ? 1 : 0.35);
  }

  return {
    onStep(i) { highlight(i); }
  };
});
