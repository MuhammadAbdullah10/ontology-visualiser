# Ontology Visualiser

An interactive exploration tool for OWL/RDFS ontologies. Give it a `.ttl` file
and it draws the classes, the object properties between them and — on demand —
the datatype properties hanging off each class. It searches, it traces routes
between classes, and it exports the whole thing as a single interactive HTML
file that works without Python.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◈ Private Company Valuation      [search…]  Fit  Reset  Save HTML    │
├──────────────┬───────────────────────────────────────────────────────┤
│ Selection    │                                                       │
│ Search       │                    ┌───────────┐   hasValuation       │
│ Find path    │                    │  Company  │ ───────────────▶ …   │
│ Display      │                    └───────────┘                      │
│ Legend       │                      ◇ id  ◇ name  ◇ sector           │
│ Statistics   │                                                       │
└──────────────┴───────────────────────────────────────────────────────┘
```

---

## 1. Install

Python 3.10 or newer.

```bash
git clone <this-repo> ontology-visualiser
cd ontology-visualiser

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## 2. Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. Upload a `.ttl` file in the sidebar,
or press **Load the example ontology** to start with `examples/valuation.ttl`.

There is also a command line, useful for batch export and for CI:

```bash
# statistics
python -m ontovis.cli examples/valuation.ttl --stats

# how do these two classes connect?
python -m ontovis.cli examples/valuation.ttl --path Company ValuationMethod

# every route, ignoring direction
python -m ontovis.cli examples/manufacturing.ttl --path Repair Supplier --undirected --all-paths

# standalone interactive export
python -m ontovis.cli examples/valuation.ttl -o valuation.html
```

Or use it as a library:

```python
from pathlib import Path
from ontovis import parse_ontology, write_html, PathFinder

ontology = parse_ontology(Path("examples/valuation.ttl"))
print(ontology.statistics.to_dict())

finder = PathFinder(ontology)
route = finder.shortest_path(
    "http://example.org/valuation#Company",
    "http://example.org/valuation#ValuationMethod",
)
print(route.as_text(ontology.class_labels()))

write_html(ontology, Path("valuation.html"))
```

## 3. Example walkthrough

Using the bundled `examples/valuation.ttl`:

1. **Load** — 12 classes, 10 object properties, 23 datatype properties appear.
2. **Explore** — click **Company**; `id`, `name`, `sector`, `currency`,
   `revenue`, `foundedDate` fan out as diamonds, with their `xsd:` types.
   `name` and `jurisdiction` are tagged as inherited from **Organisation**.
   Click **Company** again and they disappear.
3. **Search** — type `valuation`. Results are grouped into Classes
   (Valuation, Valuation Method), Object properties (hasValuation) and
   Datatype properties (valuationDate). Click one to zoom to it.
4. **Find path** — from **Company** to **Valuation Method** gives
   `Company --hasValuation--> Valuation --usesMethod--> Valuation Method`,
   highlighted in crimson with everything else muted. Switch to **All routes**
   and pick **Report** as the target to see both ways of getting there.
5. **Export** — **Download interactive HTML** in the sidebar. Open the file
   from your desktop: same graph, same interactions, no Python.

`examples/manufacturing.ttl` is modelled in a completely different style — no
`rdfs:domain`/`rdfs:range` on any object property, every relationship expressed
as an `owl:Restriction` — and produces an equally complete graph.

## 4. Project structure

```
ontology-visualiser/
├── app.py                              Streamlit entry point
├── requirements.txt / requirements-dev.txt
├── examples/
│   ├── valuation.ttl                   domain/range modelling style
│   └── manufacturing.ttl               restriction-based modelling style
├── ontovis/
│   ├── cli.py                          headless export + path queries
│   ├── parsing/
│   │   ├── models.py                   typed ontology model (no RDF, no UI)
│   │   └── ontology_parser.py          rdflib → model
│   ├── graphmodel/
│   │   ├── graph_builder.py            model → viewer payload + search index
│   │   ├── path_finder.py              BFS / bounded DFS over the class graph
│   │   └── styling.py                  design tokens (single source of truth)
│   ├── export/
│   │   ├── html_exporter.py            payload + template → standalone HTML
│   │   └── templates/viewer.html       the entire interactive application
│   └── ui/
│       ├── sidebar.py  state.py  theme.py     Streamlit shell
└── tests/
    ├── test_ontovis.py                 pytest: parsing, paths, export
    └── js/                             jsdom: viewer interaction logic
```

Layer rule: `parsing` knows nothing about graphs, `graphmodel` knows nothing
about HTML, `export` knows nothing about Streamlit, and `ui` is a thin shell.

## 5. How the ontology is parsed

`ontovis/parsing/ontology_parser.py`, built on **rdflib**.

Ontologies are modelled inconsistently in the wild, so the parser collects
evidence rather than assuming one shape.

**Classes** come from `owl:Class` and `rdfs:Class` declarations, and also from
anything used on either side of `rdfs:subClassOf`, from the domains and ranges
of object properties, and from restriction fillers. `owl:Thing`, `owl:Nothing`,
`rdfs:Resource` and XSD datatypes are excluded — they add no information to a
diagram.

**Properties** come from `owl:ObjectProperty` and `owl:DatatypeProperty`.
A bare `rdf:Property` is classified by its range: a literal range makes it a
datatype property, a class range makes it an object property, and no range at
all defaults to datatype (the conservative choice, because it never invents
class-to-class edges). `owl:AnnotationProperty` is metadata and is skipped.

**Relations** are derived two ways:

| Source in the TTL | Becomes |
|---|---|
| `:p rdfs:domain :A ; rdfs:range :B` | `A --p--> B` |
| `:A rdfs:subClassOf :B` | `A ⇢ B` (subclass) |
| `:A rdfs:subClassOf [ owl:onProperty :p ; owl:someValuesFrom :B ]` | `A --p--> B`, marked as restriction-derived |

Class expressions are unfolded: a `owl:unionOf` domain produces one relation
per member, so `documentedIn` with domain *(Valuation ∪ FundingRound)* yields
two edges. `owl:intersectionOf` is walked the same way, and restrictions nested
inside intersections are found. Cardinality is read where present and shown as
a note (`min 1`, `exactly 2`, `some values from`).

One subtlety worth calling out: when expanding an `rdfs:subClassOf` object the
parser deliberately does **not** follow restriction fillers. `Backsolve
subClassOf [onProperty calibratedTo; someValuesFrom FundingRound]` means
Backsolve is linked to FundingRound by a property — it does not make
FundingRound a superclass, and treating it as one would fabricate a hierarchy.

**Attributes** attach to their `rdfs:domain` class, carrying their range for
display (`revenue : xsd:decimal`). If no range is declared, only the name is
shown — nothing is invented. Attributes are then propagated down subclass
chains and tagged with the class that declared them, so **Company** shows
`name ↑ inherited from Organisation`. Cyclic subclass axioms are guarded
against. Properties with no usable domain are not dropped: they go into an
"unplaced" list that stays searchable, and the sidebar says how many there are.

Labels prefer `rdfs:label`, then `skos:prefLabel`, then `dcterms:title`, then
the URI's local name, with language preference for `en`. Unparseable input
raises `OntologyParseError` carrying a message meant for humans; the app shows
that and never a traceback.

## 6. How the graph is constructed

`ontovis/graphmodel/graph_builder.py` produces a JSON payload of *semantics*,
not pixels: classes (each carrying its attribute list), relations, a
pre-computed search index and the statistics. The browser decides what to
instantiate.

That is what keeps large ontologies workable:

* Only class nodes exist at start-up. A 400-class ontology with 900 datatype
  properties opens as 400 nodes, not 1300.
* Expanding a class adds only that class's attribute nodes and edges; the rest
  of the graph is never rebuilt. Collapsing removes exactly the nodes and edges
  owned by that class, which is why repeated toggling leaves no residue.
* Restyling (selection, path, dimming) writes a *style signature* per element
  and skips any element whose signature is unchanged, so a highlight pass
  touches only what actually changed.
* Physics runs during initial stabilisation and then stops, so opening a class
  does not rearrange the whole diagram under the user. The Display panel can
  switch it back on.

Attribute fans are placed geometrically rather than dropped in a fixed
direction: the viewer finds the widest angular gap around the class — counting
every nearby node, not just linked ones — aims the fan into it, and sizes the
ring so adjacent diamonds stay at least 74 px apart along the arc, staggering
alternate rows. Opening *every* class at once is beyond what any greedy
placement can guarantee, so that one action ends with a short physics relax
before the layout freezes again.

Visual encoding is carried by shape *and* colour, never colour alone: classes
are rounded boxes in cool blue, datatype properties are ochre diamonds, object
properties are solid labelled arrows, subclass links are dashed arrows pointing
at the parent, restriction-derived links are dotted. Selection adds a thick
teal outline plus a glow; the path is crimson and thickened while everything
off it is muted. All tokens live in `graphmodel/styling.py` and are injected
into both the Streamlit chrome and the exported CSS.

## 7. How path finding works

`ontovis/graphmodel/path_finder.py` (Python) and the same algorithms in the
viewer (JavaScript) operate on the class graph only: object properties and
`rdfs:subClassOf`. Datatype properties are never traversable — `Company
--name--> xsd:string` is an attribute, not a route.

* **Shortest path** — breadth-first search with predecessor tracking, O(V+E),
  returns one minimum-hop route.
* **All routes** — depth-first enumeration of *simple* paths (no class visited
  twice), bounded by `max_depth` (7 in the UI) and `max_paths` (25), sorted
  shortest first. The bounds are what stop a densely connected ontology from
  producing a combinatorial explosion.

Two switches change the traversal: **Follow relationship direction** (off means
edges are usable both ways, and reverse hops are marked `◀ … (reverse)` in the
output) and **Travel along subclass links**. When a discovered route uses a
link family that is currently hidden, the viewer switches that family back on
rather than drawing a highlight that points at nothing.

The result is rendered as a vertical chain — class, property, class — beside
the graph, while the graph itself highlights the path nodes and edges and mutes
everything else.

## 8. How the HTML export works

`ontovis/export/templates/viewer.html` **is** the application: layout, styling
and all interaction logic. `html_exporter.py` reads it and substitutes three
markers — the page title, the CSS custom properties generated from
`styling.py`, and one line assigning the ontology payload.

The Streamlit app embeds the very same rendered string it offers for download
(the only difference is a flag that hides the export button inside an export).
There is no second, weaker rendering path, so "what you see" and "what you
download" cannot drift apart. The exported file keeps nodes, edges, property
labels, attribute expansion, search, path finding, zoom, pan, selection
highlighting, the legend and the statistics.

The one external dependency is the vis-network rendering library, fetched from
a CDN with three fallbacks. For a genuinely offline artefact, inline it:

```bash
curl -o vis-network.min.js \
  https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js
python -m ontovis.cli examples/valuation.ttl -o valuation.html --embed-vis vis-network.min.js
```

Alternatively, drop `vis-network.min.js` next to the exported file — that path
is the last entry in the fallback chain. If every source fails the page says
so plainly and tells you how to fix it, instead of showing an empty canvas.

## 9. UI architecture

The Streamlit layer does four things: upload, parse, report statistics, offer
the download. Everything else lives in the viewer, which owns its whole page
inside an iframe. Splitting it this way is what makes the export honest, and it
also means the graph never re-renders because a Python widget changed.

Inside the viewer:

* **Top bar** — identity, search, fit, reset, save.
* **Left rail** — Selection details, contextual search results, Find path,
  Display toggles, Legend, Statistics, Namespaces. The legend is always
  visible, never behind a menu. Below 820 px the rail becomes a drawer.
* **Stage** — the graph, a small zoom/centre/fit cluster bottom-right, and a
  dismissible hint bottom-left.

State lives in one object (`expanded`, `selection`, `path`, `searchHits`, plus
display flags); every visual change is a pure function of it, applied by a
single `paint()` pass. Keyboard: `/` focuses search, `Enter` opens the first
result, `Esc` clears search, path and selection. `prefers-reduced-motion` is
respected, focus rings are visible, and controls are labelled for screen
readers.

## 10. Tests

```bash
pip install -r requirements-dev.txt
pytest -q                                   # 29 checks: parsing, paths, export

npm install jsdom vis-network
python -m ontovis.cli examples/valuation.ttl -o /tmp/viewer.html
node tests/js/test_viewer_runtime.js /tmp/viewer.html        # interaction logic

python -m ontovis.cli examples/valuation.ttl -o /tmp/probe.html \
  --embed-vis node_modules/vis-network/standalone/umd/vis-network.min.js
node tests/js/layout_probe.js /tmp/probe.html \
  node_modules/vis-network/standalone/umd/vis-network.min.js  # layout & options
```

The first JavaScript suite drives the real exported file with a stub for
vis-network, and asserts the behaviours the UI promises: one node per class and
no attribute nodes at start-up, first click expands, second click restores the
exact previous node and edge counts (repeated ten times), search groups results
by element type, a found path dims everything off it, clearing removes the
dimming, and display toggles add and remove the right edges.

The second — `tests/js/layout_probe.js` — boots an export with the **real**
vis-network (canvas mocked), opens every class, and fails if vis-network
rejected any option or if any two nodes end up overlapping. It runs green
against vis-network 9.1.9 and 10.1.1 on both example ontologies, and can dump
the stabilised coordinates for offline inspection.

## 11. Known limits

* Very large ontologies (a few thousand classes) will stabilise slowly; the
  layout is force-directed, and no clustering or level-of-detail is applied yet.
* Edge labels can crowd where several properties converge on one class. The
  labels carry a background halo and the spring length leaves room for them,
  but at very high density hiding them (Display ▸ Labels on links) reads better.
* Reasoning is not performed. Only asserted axioms and directly readable
  restrictions are shown — no inferred subsumption, no property chains.
* Individuals (`owl:NamedIndividual`) are outside the scope: this is a schema
  explorer, not an instance browser.
