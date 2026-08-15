# JavaScript tests

The viewer runs in the browser, so it is tested in jsdom. Two suites, two jobs.

## 1. Interaction logic — `test_viewer_runtime.js`

Drives a real exported file with a stub standing in for vis-network, so the
assertions are about *our* logic rather than the rendering library.

```bash
npm install jsdom
python -m ontovis.cli examples/valuation.ttl -o /tmp/viewer.html
node tests/js/test_viewer_runtime.js /tmp/viewer.html
```

Covers: one node per class and no attribute nodes at start-up; first click
expands and second click restores the exact previous node *and* edge counts
(repeated ten times); search grouping by element type; path highlighting and
dimming, and their removal; every Display toggle adding and removing the right
elements.

## 2. Layout — `layout_probe.js`

Boots an export with the **real** vis-network inside jsdom (canvas and element
sizing are mocked in before the document's scripts run), opens every class,
lets the layout settle, then fails if vis-network complained about any option
or if any two nodes overlap.

```bash
npm install jsdom vis-network
python -m ontovis.cli examples/valuation.ttl -o /tmp/probe.html \
  --embed-vis node_modules/vis-network/standalone/umd/vis-network.min.js
node tests/js/layout_probe.js /tmp/probe.html \
  node_modules/vis-network/standalone/umd/vis-network.min.js /tmp/layout.json
```

`/tmp/layout.json` holds the stabilised coordinates, which is handy for
plotting the layout offline when you want to look at spacing rather than assert
on it. Both suites exit non-zero on failure, so they drop straight into CI.

Verified against vis-network **9.1.9** (the version the CDN URLs pin) and
**10.1.1**, on both bundled example ontologies.
