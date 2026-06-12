// recipe: waffle
// kind: simple
// summary: Part-of-whole as a 10×10 grid — percentages people can count.
//
// Dataset rows: { "<label>": "Renewables", "<value>": 34 }   (values are shares; any units)
// scene.config (all optional):
//   { "label": "label", "value": "value" }
//
// Set scene.alt in data.json — one sentence: what the chart shows and the takeaway.

STORY.register("__SCENE_ID__", function draw(mount, data, scene) {
  const cfg = scene.config || {};
  const L = cfg.label || "label", V = cfg.value || "value";
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = (data.datasets?.[scene.dataset] || [])
    .map(d => ({ label: d[L], value: +d[V] }))
    .filter(d => d.label != null && !isNaN(d.value) && d.value > 0);
  if (!rows.length) { console.warn("[waffle] empty dataset:", scene.dataset); return null; }

  // Largest-remainder apportionment of 100 cells.
  const total = d3.sum(rows, d => d.value);
  const exact = rows.map(d => (d.value / total) * 100);
  const cells = exact.map(Math.floor);
  let leftover = 100 - d3.sum(cells);
  exact.map((e, i) => ({ i, frac: e - cells[i] }))
    .sort((a, b) => b.frac - a.frac)
    .slice(0, leftover)
    .forEach(({ i }) => { cells[i] += 1; });

  const W = 720, H = 420;
  const grid = 10, cell = 30, gap = 4;
  const gridSize = grid * cell + (grid - 1) * gap;
  const left = 36, top = 36;

  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${W} ${H}`)
    .attr("aria-hidden", "true")
    .style("width", "100%").style("height", "auto").style("display", "block");
  const g = svg.append("g").attr("transform", `translate(${left},${top})`);

  // One flat list of 100 cells, category index per cell (fills bottom-up).
  const flat = [];
  cells.forEach((n, ci) => { for (let k = 0; k < n; k++) flat.push(ci); });
  const palette = rows.map((_, i) => `var(--cat-${(i % 7) + 1})`);

  g.selectAll("rect.cell").data(flat).join("rect").attr("class", "cell")
    .attr("x", (_, i) => (i % grid) * (cell + gap))
    .attr("y", (_, i) => gridSize - cell - Math.floor(i / grid) * (cell + gap))
    .attr("width", cell).attr("height", cell).attr("rx", 3)
    .attr("fill", ci => palette[ci])
    .attr("opacity", 0)
    .transition().duration(REDUCE ? 0 : 350)
    .delay((_, i) => REDUCE ? 0 : i * 8).attr("opacity", 1);

  // Legend, right of the grid.
  const lg = svg.append("g")
    .attr("transform", `translate(${left + gridSize + 48},${top + 8})`);
  const rowsWithPct = rows.map((d, i) => ({ ...d, pct: cells[i], color: palette[i] }));
  const item = lg.selectAll("g.item").data(rowsWithPct).join("g")
    .attr("class", "item")
    .attr("transform", (_, i) => `translate(0,${i * 30})`);
  item.append("rect").attr("width", 14).attr("height", 14).attr("rx", 3)
    .attr("y", -7).attr("fill", d => d.color);
  item.append("text").attr("class", "annotation")
    .attr("x", 22).attr("dy", "0.32em")
    .text(d => `${d.label} — ${d.pct}%`);

  return null;
});
