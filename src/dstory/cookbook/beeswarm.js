// recipe: beeswarm
// kind: simple
// summary: Every data point visible — a distribution along one axis, optionally colored by group.
//
// Dataset rows: { "<label>": "Norway", "<value>": 81.2, "<group>": "Europe" }   (group optional)
// scene.config (all optional):
//   { "value": "value", "label": "label", "group": "group",
//     "radius": 5, "format": ",", "axis_label": "Life expectancy (years)",
//     "annotate": ["Norway", "Chad"] }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const V = cfg.value || "value", L = cfg.label || "label", G = cfg.group || "group";
  const R = cfg.radius || 5;
  const fmt = d3.format(cfg.format || ",");
  const annotate = new Set(cfg.annotate || []);
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ label: d[L], value: +d[V], group: d[G] }))
    .filter(d => !isNaN(d.value));
  if (!rows.length) { console.warn("[beeswarm] empty dataset:", scene.dataset); return null; }

  const W = 720, H = 340;
  const margin = { top: 32, right: 24, bottom: 48, left: 24 };
  const w = W - margin.left - margin.right, h = H - margin.top - margin.bottom;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear().domain(d3.extent(rows, d => d.value)).nice().range([0, w]);
  const groups = [...new Set(rows.map(d => d.group).filter(v => v != null))];
  const palette = groups.map((_, i) => `var(--cat-${(i % 7) + 1})`);
  const color = d => groups.length ? palette[groups.indexOf(d.group)] : "var(--accent)";

  // Deterministic layout: run the simulation to completion before drawing.
  const sim = d3.forceSimulation(rows)
    .force("x", d3.forceX(d => x(d.value)).strength(1))
    .force("y", d3.forceY(h / 2).strength(0.08))
    .force("collide", d3.forceCollide(R + 1))
    .stop();
  for (let i = 0; i < 160; i++) sim.tick();

  g.append("g").attr("transform", `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(fmt))
    .call(s => s.select(".domain").remove())
    .selectAll("text").attr("class", "annotation");
  if (cfg.axis_label) {
    g.append("text").attr("class", "annotation")
      .attr("x", w / 2).attr("y", h + 38).attr("text-anchor", "middle")
      .text(cfg.axis_label);
  }

  g.selectAll("circle.bee").data(rows).join("circle").attr("class", "bee")
    .attr("cx", d => d.x).attr("cy", d => d.y)
    .attr("fill", color).attr("fill-opacity", 0.85)
    .attr("r", 0)
    .transition().duration(REDUCE ? 0 : 600).delay((_, i) => REDUCE ? 0 : i * 6)
    .ease(d3.easeCubicOut).attr("r", R);

  // Alternate callouts above/below their dot so neighbors don't collide.
  g.selectAll("text.callout").data(rows.filter(d => annotate.has(d.label)))
    .join("text").attr("class", "callout annotation annotation--strong")
    .attr("x", d => d.x)
    .attr("y", (d, i) => i % 2 === 0 ? d.y - R - 8 : d.y + R + 8)
    .attr("dy", (d, i) => (i % 2 === 0 ? "0" : "0.7em"))
    .attr("text-anchor", "middle")
    .text(d => `${d.label} ${fmt(d.value)}`);

  // Group legend (only when grouped)
  if (groups.length > 1) {
    const lg = g.append("g").attr("transform", `translate(0,-24)`);
    let cx = 0;
    groups.forEach((grp, i) => {
      lg.append("circle").attr("cx", cx + 5).attr("cy", 0).attr("r", 5).attr("fill", palette[i]);
      const t = lg.append("text").attr("class", "annotation")
        .attr("x", cx + 14).attr("dy", "0.32em").text(grp);
      cx += 22 + (t.node().getComputedTextLength ? t.node().getComputedTextLength() : grp.length * 7) + 14;
    });
  }
  return null;
});
