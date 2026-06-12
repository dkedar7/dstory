# Vizzu Chart Gallery

Every Vizzu chart type as a copy-paste JSON snippet that drops into a `kind: "vizzu"` scene's `frames[]` array. Vizzu has no fixed "chart types" — these are all combinations of **4 geometries × 2 coordinate systems × 7 channels**. Memorizing the four moves below unlocks the full range; the rest is recombination.

## The four geometries
- **`rectangle`** — bars, columns, treemaps, marimekkos, heatmaps, pies (with polar)
- **`circle`** — scatter, bubble, dot plots
- **`line`** — line charts, slope charts, radar (with polar)
- **`area`** — area, stacked area, streamgraph

## The two coordinate systems
- **`cartesian`** (default) — flat x/y plane
- **`polar`** — wraps the x-axis into a circle. Bars become wedges, lines become radial.

## The seven channels
- **`x`**, **`y`** — position axes
- **`color`** — hue (usually a dimension)
- **`size`** — area / radius (usually a measure)
- **`lightness`** — shade variation within a hue
- **`label`** — inline text on each element
- **`noop`** — included in groupby without encoding

## Channel value forms
- String: `"x": "Year"` (one field, default)
- Object: `"x": {"set": "Year", "aggregator": "sum"}` (with options like `aggregator`, `range`)
- Array (list): `"y": ["Region", "Pop"]` (multi-level grouping or stacking)

---

## Rectangle geometry

### Bar / Column

```json
{"channels": {"x": "Year", "y": "Sales"}, "geometry": "rectangle"}
```
*(column chart — vertical bars)*

```json
{"channels": {"x": "Sales", "y": "Region"}, "geometry": "rectangle"}
```
*(bar chart — horizontal bars)*

### Stacked column

```json
{"channels": {"x": "Year", "y": "Sales", "color": "Region"}, "geometry": "rectangle"}
```
*(stacks Region within each Year)*

### Grouped column (side-by-side, not stacked)

```json
{"channels": {"x": ["Year", "Region"], "y": "Sales", "color": "Region"}, "geometry": "rectangle"}
```
*(use array for `x` to break Region out from the stack into adjacent groups)*

### Percentage (100%) stacked column

```json
{"channels": {"x": "Year", "y": {"set": "Sales", "range": {"max": "100%"}}, "color": "Region"},
 "geometry": "rectangle"}
```

### Heatmap

```json
{"channels": {"x": "Day", "y": "Hour", "color": "Visits"}, "geometry": "rectangle"}
```
*(both axes are dimensions; color encodes the measure)*

### Treemap

```json
{"channels": {"size": "Pop", "color": "Region", "label": "Region"}, "geometry": "rectangle"}
```
*(no x/y — pure area-packing layout, color groups, label shows region name)*

### Stacked treemap (nested grouping)

```json
{"channels": {"size": "Pop", "color": ["Region", "Country"], "label": "Country"},
 "geometry": "rectangle"}
```

### Marimekko (Mekko)

```json
{"channels": {"x": {"set": "Region", "range": {"max": "100%"}},
              "y": {"set": "Sales",  "range": {"max": "100%"}},
              "color": "Product"},
 "geometry": "rectangle"}
```
*(width-weighted columns where each column's height is also a stretched stack)*

### Waterfall

```json
{"channels": {"x": "Step", "y": "Delta", "color": "Step"},
 "geometry": "rectangle",
 "align": "center"}
```
*(use signed `Delta` values; `align: "center"` produces the classic waterfall lift)*

### Lollipop

```json
{"channels": {"x": "Region", "y": "Sales", "color": "Region"},
 "geometry": "rectangle",
 "style": {"plot": {"marker": {"rectangleSpacing": "90%"}}}}
```
*(narrow bars — by squeezing rectangle width to ~10%)*

---

## Rectangle + polar (`coordSystem: "polar"`)

### Pie chart

```json
{"channels": {"x": "Sales", "color": "Region"}, "geometry": "rectangle", "coordSystem": "polar"}
```
*(only one channel; bars curl into a circle = pie wedges)*

### Donut chart

```json
{"channels": {"x": "Sales", "color": "Region"},
 "geometry": "rectangle", "coordSystem": "polar",
 "style": {"plot": {"marker": {"angularPadding": "1deg"},
                    "yAxis": {"label": {"position": "axis"}}}}}
```
*(pie with a hole — control via the inner radius style. See Vizzu donut docs.)*

### Variable-Radius Pie / Coxcomb / Nightingale Rose

```json
{"channels": {"x": "Region", "y": "Sales", "color": "Region"},
 "geometry": "rectangle", "coordSystem": "polar"}
```
*(when both x and y are set with polar, you get radial bars where each wedge has a different radius)*

### Polar bar (radial bar)

```json
{"channels": {"x": "Region", "y": "Sales", "color": "Region"},
 "geometry": "rectangle", "coordSystem": "polar"}
```

### Polar stacked column

```json
{"channels": {"x": "Year", "y": "Sales", "color": "Region"},
 "geometry": "rectangle", "coordSystem": "polar"}
```

---

## Circle geometry

### Scatter

```json
{"channels": {"x": "GDP", "y": "Lifespan"}, "geometry": "circle"}
```

### Bubble plot (scatter + size encoding)

```json
{"channels": {"x": "GDP", "y": "Lifespan", "size": "Population", "color": "Continent"},
 "geometry": "circle"}
```

### Bubble chart (no axes — packing layout)

```json
{"channels": {"size": "Pop", "color": "Region", "label": "City"}, "geometry": "circle"}
```

### Stacked bubble (nested groups)

```json
{"channels": {"size": "Pop", "color": ["Region", "Country"]}, "geometry": "circle"}
```

### Dot plot

```json
{"channels": {"x": "Region", "y": "Sales"}, "geometry": "circle"}
```
*(one axis as dimension, dots positioned by the measure)*

### Polar scatter / Star plot

```json
{"channels": {"x": "Variable", "y": "Value", "color": "Series"},
 "geometry": "circle", "coordSystem": "polar"}
```

---

## Line geometry

### Line chart (multi-series)

```json
{"channels": {"x": "Year", "y": "Sales", "color": "Region"}, "geometry": "line"}
```

### Single-series line

```json
{"channels": {"x": "Year", "y": "Sales"}, "geometry": "line"}
```

### Radar / Spider chart

```json
{"channels": {"x": "Skill", "y": "Score", "color": "Player"},
 "geometry": "line", "coordSystem": "polar"}
```
*(line + polar with categorical x = the classic radar)*

### Slope chart (two-time-point comparison)

```json
{"channels": {"x": "Year", "y": "Rank", "color": "City"},
 "geometry": "line"}
```
*(use a dataset with only 2 years; reverse y-scale for rank-1-on-top)*

---

## Area geometry

### Area chart

```json
{"channels": {"x": "Year", "y": "Sales"}, "geometry": "area"}
```

### Stacked area

```json
{"channels": {"x": "Year", "y": "Sales", "color": "Region"}, "geometry": "area"}
```

### Percentage stacked area

```json
{"channels": {"x": "Year", "y": {"set": "Sales", "range": {"max": "100%"}}, "color": "Region"},
 "geometry": "area"}
```

### Streamgraph (center-aligned stacked area)

```json
{"channels": {"x": "Year", "y": "Sales", "color": "Region"},
 "geometry": "area",
 "align": "center"}
```

### Polar area (rosette)

```json
{"channels": {"x": "Month", "y": "Rainfall", "color": "Month"},
 "geometry": "area", "coordSystem": "polar"}
```

---

## Distribution / special

### Histogram

```json
{"channels": {"x": "Value", "y": {"set": "count()"}}, "geometry": "rectangle"}
```
*(use Vizzu's `count()` aggregator OR pre-bin in your data prep)*

### Violin

```json
{"channels": {"x": "Group", "y": "Value", "color": "Group"},
 "geometry": "area",
 "split": true}
```
*(area with `split: true` mirrors above/below an axis)*

---

## What Vizzu canNOT do (use other dstory scene kinds)

| Want | Use |
|------|------|
| Sankey / alluvial | `kind: "sankey"` (d3-sankey) |
| Geographic map | `kind: "map"` (Leaflet) |
| Force-directed network | `kind: "network"` (d3-force) |
| 3D / WebGL | hand-write with Three.js in a `kind: "simple"` scene |
| Sunburst | best approximation: nested donut |
| Word cloud | hand-write with d3-cloud |
| Box plot | violin (above) is the closest preset |

---

## The morph trick (Vizzu's actual superpower)

Don't pick one chart per scene — pick **a sequence that morphs between qualitatively different shapes**. The reader stays oriented because the data is constant; only the lens changes. Examples that work:

**Bar → polar bar → pie → bubble → treemap** (same total per region, 5 different visual logics):
```json
"frames": [
  {"config": {"channels": {"x": "Region", "y": "Sales", "color": "Region"},
              "geometry": "rectangle"}},
  {"config": {"channels": {"x": "Region", "y": "Sales", "color": "Region"},
              "geometry": "rectangle", "coordSystem": "polar"}},
  {"config": {"channels": {"x": "Sales", "color": "Region"},
              "geometry": "rectangle", "coordSystem": "polar"}},
  {"config": {"channels": {"size": "Sales", "color": "Region"},
              "geometry": "circle"}},
  {"config": {"channels": {"size": "Sales", "color": "Region", "label": "Region"},
              "geometry": "rectangle"}}
]
```

**Stacked column → streamgraph → ribbon line** (same time series, three temporal logics):
```json
"frames": [
  {"config": {"channels": {"x": "Year", "y": "Sales", "color": "Cat"},
              "geometry": "rectangle"}},
  {"config": {"channels": {"x": "Year", "y": "Sales", "color": "Cat"},
              "geometry": "area", "align": "center"}},
  {"config": {"channels": {"x": "Year", "y": "Sales", "color": "Cat"},
              "geometry": "line"}}
]
```

**Scatter → dot plot → bubble** (same observations, three encoding emphases):
```json
"frames": [
  {"config": {"channels": {"x": "GDP", "y": "Lifespan", "color": "Continent"},
              "geometry": "circle"}},
  {"config": {"channels": {"x": "Continent", "y": "Lifespan", "color": "Continent"},
              "geometry": "circle"}},
  {"config": {"channels": {"size": "Pop", "color": "Continent"},
              "geometry": "circle"}}
]
```

## Anti-patterns

- **bar → area → line**: three cousins of the same chart. Easy to author, low surprise. Use only as part of a richer 5-frame morph, not as a 3-frame sequence on its own.
- **6+ frames in one scene**: morph fatigue. Cap at 5; use a second `vizzu` scene for more.
- **Continuous-only morphs that the reader can't decode**: changing from `circle` to `rectangle` while ALSO changing every channel breaks visual continuity. Hold at least one channel constant between frames.
- **Polar with > 8 categories**: the wedges become unreadable. Stick to ≤ 7 colors per polar chart.
