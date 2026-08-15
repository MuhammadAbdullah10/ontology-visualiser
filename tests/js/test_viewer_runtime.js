/* Headless checks for the viewer runtime.
 *
 *   python -m ontovis.cli examples/valuation.ttl -o /tmp/viewer.html
 *   node tests/js/test_viewer_runtime.js /tmp/viewer.html
 *
 * vis-network is replaced by tests/js/vis-network-stub.js, so this exercises
 * the application logic — expand/collapse, search, path finding, dimming —
 * rather than the rendering library.
 */
const fs = require("fs");
const path = require("path");
const {JSDOM} = require("jsdom");

const htmlPath = process.argv[2];
if (!htmlPath) {
  console.error("usage: node test_viewer_runtime.js <exported.html>");
  process.exit(2);
}

let failures = 0;
function check(name, condition, extra) {
  if (condition) {
    console.log("  ok   " + name);
  } else {
    failures++;
    console.log("  FAIL " + name + (extra ? "  → " + extra : ""));
  }
}

const stub = fs.readFileSync(path.join(__dirname, "vis-network-stub.js"), "utf8");
let html = fs.readFileSync(htmlPath, "utf8");
// Inject the stub before the runtime, and start immediately instead of
// fetching vis-network from a CDN.
html = html.replace("<script>\n/* ====", "<script>" + stub + "</script>\n<script>\n/* ====");
html = html.replace("loadVis(0);", "start();");

const dom = new JSDOM(html, {runScripts: "dangerously", pretendToBeVisual: true});
const {window} = dom;
const doc = window.document;

setTimeout(() => {
  const payload = window.__ONTOLOGY_PAYLOAD__;
  const {network, nodes, edges} = window.ontovis;
  const classId = payload.classes.find((c) => c.label === "Company").id;
  const methodId = payload.classes.find((c) => c.label === "Valuation Method").id;

  console.log("\nGraph construction");
  check("one node per class", nodes.length === payload.classes.length,
        `${nodes.length} vs ${payload.classes.length}`);
  check("no attribute nodes before expansion",
        nodes.get().every((n) => n.group === "class"));
  check("edges match visible relations", edges.length === payload.relations.length);
  check("statistics rendered", doc.getElementById("stats").textContent.includes("Classes"));

  console.log("\nExpand / collapse");
  network.emit("click", {nodes: [classId], edges: []});
  const afterExpand = nodes.length;
  check("first click adds attribute nodes", afterExpand > payload.classes.length,
        `${afterExpand}`);
  check("attribute nodes are diamonds",
        nodes.get().filter((n) => n.group === "attribute").every((n) => n.shape === "diamond"));
  check("attribute nodes carry their owner",
        nodes.get().filter((n) => n.group === "attribute").every((n) => n.owner === classId));
  check("selection panel shows the class",
        doc.getElementById("details").textContent.includes("Company"));
  network.emit("click", {nodes: [classId], edges: []});
  check("second click restores the previous node count", nodes.length === payload.classes.length,
        `${nodes.length}`);
  check("second click restores the previous edge count", edges.length === payload.relations.length);

  // Repeat several times: collapse must stay reliable.
  let stable = true;
  for (let i = 0; i < 5; i++) {
    network.emit("click", {nodes: [classId], edges: []});
    network.emit("click", {nodes: [classId], edges: []});
    if (nodes.length !== payload.classes.length || edges.length !== payload.relations.length) stable = false;
  }
  check("toggling five more times leaves no residue", stable);

  console.log("\nSearch");
  const input = doc.getElementById("search");
  input.value = "valuation";
  input.dispatchEvent(new window.Event("input"));

  setTimeout(() => {
    const results = doc.getElementById("search-results");
    check("search panel opens", !doc.getElementById("panel-search").hidden);
    check("classes group present", results.textContent.includes("Classes"));
    check("object properties group present", results.textContent.includes("Object properties"));
    check("case-insensitive match on Valuation", results.textContent.includes("Valuation"));
    const buttons = results.querySelectorAll("[data-idx]");
    check("results are clickable", buttons.length > 0);
    buttons[0].click();
    check("clicking a result focuses the graph", !!network.lastFocus || !!network.lastFit);

    console.log("\nPath finding");
    doc.getElementById("path-source").value = classId;
    doc.getElementById("path-target").value = methodId;
    doc.getElementById("btn-find").click();
    const output = doc.getElementById("path-output").textContent;
    check("path chain lists the source", output.includes("Company"));
    check("path chain lists the intermediate class", output.includes("Valuation"));
    check("path chain names the properties",
          output.includes("hasValuation") && output.includes("usesMethod"));

    const dimmed = nodes.get().filter((n) => n.color && n.color.border === "#D5DDE3");
    check("off-path nodes are dimmed", dimmed.length > 0, `${dimmed.length}`);
    const pathEdges = edges.get().filter((e) => e.color && e.color.color === "#C0405E");
    check("path edges are highlighted", pathEdges.length === 2, `${pathEdges.length}`);

    // Company reaches Report two ways (via Valuation and via Funding Round).
    const reportId = payload.classes.find((c) => c.label === "Report").id;
    doc.getElementById("path-target").value = reportId;
    doc.getElementById("mode-all").click();
    doc.getElementById("btn-find").click();
    const routes = doc.getElementById("path-output").querySelectorAll("[data-path]");
    check("all-routes mode lists every alternative", routes.length >= 2, `${routes.length}`);
    routes[1].click();
    check("selecting an alternative route re-highlights",
          doc.getElementById("path-output").querySelector('[aria-pressed="true"]') !== null);

    doc.getElementById("btn-clear-path").click();
    const stillDim = nodes.get().filter((n) => n.color && n.color.border === "#D5DDE3");
    check("clearing the path removes dimming", stillDim.length === 0, `${stillDim.length}`);

    console.log("\nControls");
    doc.getElementById("btn-expand-all").click();
    check("open-all expands every class with attributes",
          nodes.get().filter((n) => n.group === "attribute").length > 20);
    doc.getElementById("btn-collapse-all").click();
    check("close-all returns to the class-only graph", nodes.length === payload.classes.length);

    doc.getElementById("opt-subclass").checked = false;
    doc.getElementById("opt-subclass").dispatchEvent(new window.Event("change"));
    const subclassEdges = edges.get().filter((e) => e.group === "subclass");
    check("subclass links can be hidden", subclassEdges.length === 0);
    doc.getElementById("opt-subclass").checked = true;
    doc.getElementById("opt-subclass").dispatchEvent(new window.Event("change"));
    check("subclass links come back",
          edges.get().filter((e) => e.group === "subclass").length ===
          payload.relations.filter((r) => r.kind === "subclass").length);

    doc.getElementById("opt-inherited").checked = false;
    doc.getElementById("opt-inherited").dispatchEvent(new window.Event("change"));
    network.emit("click", {nodes: [classId], edges: []});
    const inheritedShown = nodes.get().filter(
      (n) => n.group === "attribute" && String(n.label).startsWith("↑")).length;
    check("inherited attributes can be switched off", inheritedShown === 0, `${inheritedShown}`);

    console.log(failures ? `\n${failures} check(s) failed` : "\nAll checks passed");
    process.exit(failures ? 1 : 0);
  }, 260);
}, 120);
