/* Boots an exported visualisation with the REAL vis-network inside jsdom,
 * using a mocked 2D canvas context (jsdom has no canvas).
 *
 * It reports any option-validation complaints from vis-network and dumps the
 * stabilised node positions, so the layout can be inspected offline.
 *
 *   node tests/js/layout_probe.js <exported.html> <path/to/vis-network.min.js> <out.json>
 */
const fs = require("fs");
const {JSDOM} = require("jsdom");

const [htmlPath, visPath, outPath] = process.argv.slice(2);
if (!htmlPath || !visPath) {
  console.error("usage: node layout_probe.js <exported.html> <vis-network.min.js> [out.json]");
  process.exit(2);
}

const html = fs.readFileSync(htmlPath, "utf8");
const complaints = [];

/* jsdom has no canvas and reports zero-sized elements, so everything the
 * renderer needs is mocked in before the document's own scripts run. */
function installMocks(window) {
  const ctx = new Proxy({}, {
    get(target, prop) {
      if (prop === "measureText") {
        return (text) => ({width: String(text).length * 7.2,
                           actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 3});
      }
      if (prop === "canvas") return {width: 1280, height: 820};
      if (prop === "createLinearGradient" || prop === "createPattern") {
        return () => ({addColorStop() {}});
      }
      if (prop === "getImageData") return () => ({data: new Uint8ClampedArray(4)});
      if (prop in target) return target[prop];
      return () => undefined;
    },
    set(target, prop, value) { target[prop] = value; return true; }
  });
  window.HTMLCanvasElement.prototype.getContext = () => ctx;
  ["clientWidth", "offsetWidth"].forEach((prop) =>
    Object.defineProperty(window.HTMLElement.prototype, prop, {get: () => 1280}));
  ["clientHeight", "offsetHeight"].forEach((prop) =>
    Object.defineProperty(window.HTMLElement.prototype, prop, {get: () => 820}));
  window.HTMLElement.prototype.getBoundingClientRect = () => ({
    x: 0, y: 0, top: 0, left: 0, right: 1280, bottom: 820, width: 1280, height: 820
  });
  ["error", "warn", "log"].forEach((level) => {
    window.console[level] = (...args) => {
      const text = args.map(String).join(" ");
      if (/Problem|Unknown|deprecat|invalid|Error/i.test(text)) complaints.push(level + ": " + text);
    };
  });
}

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  pretendToBeVisual: true,
  beforeParse: installMocks
});
const {window} = dom;

/* The export must have been built with --embed-vis, so the library is already
 * inside the document and the viewer boots itself during parsing. */
if (!window.vis || !window.vis.Network) {
  console.error("no vis-network in the document — build the export with --embed-vis");
  process.exit(1);
}

setTimeout(() => {
  const api = window.ontovis;
  if (!api) {
    console.error("viewer did not boot; complaints:\n" + complaints.join("\n"));
    process.exit(1);
  }
  const {network, nodes, edges, payload} = api;

  // Open every class through the real control: a fan that only works for one
  // class is not a working fan.
  window.document.getElementById("btn-expand-all").click();

  setTimeout(() => {
    const positions = network.getPositions();
    const dump = {
      complaints,
      nodes: nodes.get().map((n) => ({
        id: n.id, label: String(n.label), group: n.group, owner: n.owner || null,
        x: positions[n.id] ? positions[n.id].x : null,
        y: positions[n.id] ? positions[n.id].y : null
      })),
      edges: edges.get().map((e) => ({
        from: e.from, to: e.to, group: e.group, label: e.label || ""
      }))
    };
    if (outPath) fs.writeFileSync(outPath, JSON.stringify(dump, null, 1));
    console.log("nodes:", dump.nodes.length, "edges:", dump.edges.length);
    console.log("complaints:", complaints.length ? "\n  " + complaints.join("\n  ") : "none");

    /* Layout assertions: nothing may sit on top of anything else. Class boxes
       are measured from their label; attribute diamonds carry a label below. */
    const CH = 7.2;
    const box = (n) => {
      const w = n.group === "class" ? Math.max(70, String(n.label).length * CH + 30) : 30;
      const h = n.group === "class" ? 38 : 46;
      return {label: n.label, x1: n.x - w / 2, y1: n.y - h / 2, x2: n.x + w / 2, y2: n.y + h / 2};
    };
    const boxes = dump.nodes.map(box);
    const clashes = [];
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2) {
          clashes.push(`${String(a.label).split("\n")[0]} ↔ ${String(b.label).split("\n")[0]}`);
        }
      }
    }
    console.log("overlapping nodes:", clashes.length ? "\n  " + clashes.join("\n  ") : "none");
    process.exit(complaints.length || clashes.length ? 1 : 0);
  }, 6000);
}, 1500);
