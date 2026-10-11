// Waypoint UI. Every server string reaches the page through textContent; no HTML parsing sinks.
"use strict";

const $ = (id) => document.getElementById(id);
const DEFAULT_ASKER = "ZV-1042";
let cy = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

async function getJSON(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try { body = await res.json(); } catch (_) { /* non-JSON error page */ }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    if (body && typeof body.detail === "string") msg = body.detail;
    else if (body && Array.isArray(body.detail)) msg = body.detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
    throw new Error(msg);
  }
  return body;
}

async function loadEmployees() {
  const select = $("asker");
  try {
    const people = await getJSON("/employees");
    for (const p of people) {
      const opt = el("option", "", `${p.name} (${p.id}) · ${p.title}${p.department ? ", " + p.department : ""}`);
      opt.value = p.id;
      select.appendChild(opt);
    }
    if (people.some((p) => p.id === DEFAULT_ASKER)) select.value = DEFAULT_ASKER;
  } catch (e) {
    addMessage("err", `Could not load employees: ${e.message}`);
  }
}

async function checkHealth() {
  const badge = $("health");
  try {
    await getJSON("/health");
    badge.textContent = "Neo4j up";
    badge.className = "health up";
  } catch (_) {
    badge.textContent = "Neo4j down";
    badge.className = "health down";
  }
}

function addMessage(kind, text, who) {
  const box = el("div", `msg ${kind}`);
  if (who) box.appendChild(el("div", "who", who));
  box.appendChild(el("div", "text", text));
  $("log").appendChild(box);
  box.scrollIntoView({ block: "end" });
  return box;
}

function citationChip(c) {
  if (c.type === "policy") {
    const label = c.section !== null && c.section !== undefined ? `${c.id} §${c.section}` : c.id;
    return el("span", "chip policy", label);
  }
  if (c.type === "graph") return el("span", "chip graph", c.path);
  if (c.type === "chunk") {
    const chip = el("span", "chip chunk", c.id);
    chip.title = c.id;
    return chip;
  }
  return el("span", "chip", JSON.stringify(c));
}

function renderAnswer(box, data) {
  box.textContent = "";
  box.className = "msg a";
  box.appendChild(el("div", "who", "Waypoint"));
  box.appendChild(el("div", "text", data.answer));
  if (data.citations && data.citations.length) {
    const chips = el("div", "chips");
    data.citations.forEach((c) => chips.appendChild(citationChip(c)));
    box.appendChild(chips);
  }
  const foot = el("div", "footer");
  const u = data.usage || {};
  foot.appendChild(el("span", "", `route: ${data.route}`));
  foot.appendChild(el("span", "", `confidence: ${Number(data.confidence).toFixed(2)}`));
  foot.appendChild(el("span", "", `tokens: ${u.input_tokens || 0} in / ${u.output_tokens || 0} out`));
  foot.appendChild(el("span", "", `latency: ${(Number(data.latency_ms) / 1000).toFixed(1)} s`));
  foot.appendChild(el("span", "", `as of ${data.as_of}`));
  if (data.cached) foot.appendChild(el("span", "badge", "cached"));
  box.appendChild(foot);
  box.addEventListener("click", () => selectAnswer(box, data));
  selectAnswer(box, data);
}

function selectAnswer(box, data) {
  document.querySelectorAll(".msg.a.selected").forEach((m) => m.classList.remove("selected"));
  box.classList.add("selected");
  drawGraph(data.subgraph || { nodes: [], edges: [] }, data.citations || []);
}

// "ZV-1041 -REPORTS_TO-> ZV-1017 -REPORTS_TO-> ZV-1001" -> edge keys "source|TYPE|target"
function citedEdges(citations) {
  const keys = new Set();
  for (const c of citations) {
    if (c.type !== "graph") continue;
    const parts = c.path.split(" ");
    for (let i = 0; i + 2 < parts.length; i += 2) {
      const m = /^-(\w+)->$/.exec(parts[i + 1]);
      if (m) keys.add(`${parts[i]}|${m[1]}|${parts[i + 2]}`);
    }
  }
  return keys;
}

// Policy citations {id, section} -> PolicySection ids as in the graph ("ZEN-POL-002#4").
function citedSections(citations) {
  return new Set(citations.filter((c) => c.type === "policy" && c.section !== null && c.section !== undefined)
    .map((c) => `${c.id}#${c.section}`));
}

function showDetail(node) {
  const box = $("node-detail");
  if (!node) { box.textContent = ""; return; }
  const d = node.data();
  const head = `${d.label} (${d.kind} ${d.id})`;
  box.textContent = d.detail ? `${head}\nWaypoint reasoning (derived, not stored in the graph): ${d.detail}` : head;
}

function drawGraph(subgraph, citations) {
  const note = $("graph-note");
  if (cy) { cy.destroy(); cy = null; }
  showDetail(null);
  if (typeof cytoscape !== "function") {
    note.textContent = "Cytoscape.js did not load (offline or blocked CDN); the subgraph cannot be drawn.";
    return;
  }
  const ids = new Set(subgraph.nodes.map((n) => n.id));
  const cited = citedEdges(citations);
  const sections = citedSections(citations);
  const hot = new Set();
  const elements = subgraph.nodes.map((n) => ({
    data: { id: n.id, label: n.name || n.id, kind: n.label, detail: n.detail || "" },
  }));
  const seen = new Set();
  let highlighted = 0;
  for (const e of subgraph.edges) {
    const key = `${e.source}|${e.type}|${e.target}`;
    if (!ids.has(e.source) || !ids.has(e.target) || seen.has(key)) continue;
    seen.add(key);
    const classes = [];
    const isCited = cited.has(key) || (e.derived && sections.has(e.target));
    if (isCited || e.role === "decisive") classes.push(e.role === "checked" ? "checked" : "cited");
    else if (e.role === "checked") classes.push("checked");
    if (e.derived) classes.push("derived");
    if (classes.includes("cited")) { hot.add(e.source); hot.add(e.target); highlighted += 1; }
    const label = e.derived ? "derived (rule case)" : e.type;
    elements.push({ data: { id: key, source: e.source, target: e.target, label }, classes: classes.join(" ") });
  }
  elements.forEach((x) => {
    if (!x.data.source && (hot.has(x.data.id) || sections.has(x.data.id))) x.classes = "cited";
  });
  note.textContent = subgraph.nodes.length
    ? `${subgraph.nodes.length} nodes, ${seen.size} edges; ${highlighted} cited or decisive edge(s) highlighted.`
    : "No graph evidence for this answer (policy text, a refusal or not found).";
  if (!subgraph.nodes.length) return;
  cy = cytoscape({
    container: $("graph"),
    elements,
    layout: { name: "cose", animate: false, padding: 30, nodeRepulsion: 9000, idealEdgeLength: 110 },
    style: [
      { selector: "node", style: { label: "data(label)", "font-size": 11, "text-valign": "bottom", "text-margin-y": 4,
        "background-color": "#9aa6c8", width: 22, height: 22, "text-wrap": "wrap", "text-max-width": 120 } },
      { selector: "node[kind = 'Employee']", style: { "background-color": "#6b8fe0" } },
      { selector: "node[kind = 'Department']", style: { "background-color": "#e0a15a", shape: "round-rectangle" } },
      { selector: "node[kind = 'Project'], node[kind = 'Product']", style: { "background-color": "#7cc08a", shape: "hexagon" } },
      { selector: "node[kind = 'Policy']", style: { "background-color": "#c58ad6", shape: "round-rectangle" } },
      { selector: "node[kind = 'PolicySection']", style: { "background-color": "#e7c6f0", shape: "rectangle" } },
      { selector: "node[detail != '']", style: { "border-width": 2, "border-style": "dashed", "border-color": "#7a4d00" } },
      { selector: "edge", style: { label: "data(label)", "font-size": 9, color: "#6b7385", width: 1.5,
        "line-color": "#c3c9d6", "target-arrow-color": "#c3c9d6", "target-arrow-shape": "triangle",
        "curve-style": "bezier", "text-rotation": "autorotate", "text-background-color": "#fcfcfd", "text-background-opacity": 1 } },
      { selector: "edge.checked", style: { width: 2.5, "line-color": "#e8a33d", "target-arrow-color": "#e8a33d" } },
      { selector: "edge.cited", style: { width: 4, "line-color": "#d6453d", "target-arrow-color": "#d6453d", color: "#9b1c1c" } },
      { selector: "edge.derived", style: { "line-style": "dashed", "font-style": "italic" } },
      { selector: "node.cited", style: { "border-width": 3, "border-style": "solid", "border-color": "#d6453d" } },
    ],
  });
  cy.on("tap", "node", (evt) => showDetail(evt.target));
  cy.on("tap", (evt) => { if (evt.target === cy) showDetail(null); });
}

async function onAsk(event) {
  event.preventDefault();
  const input = $("question");
  const question = input.value.trim();
  if (!question) return;
  const send = $("send");
  const askerSelect = $("asker");
  const who = askerSelect.selectedOptions.length ? askerSelect.selectedOptions[0].textContent : askerSelect.value;
  addMessage("q", question, `${who} · as of ${$("as-of").value}`);
  input.value = "";
  send.disabled = true;
  input.disabled = true;
  const pending = addMessage("loading", "Thinking… (free-tier rate limits can take a minute)");
  try {
    const url = $("fresh").checked ? "/ask?fresh=1" : "/ask";
    const body = { question, asker_id: askerSelect.value };
    if ($("as-of").value) body.as_of = $("as-of").value;
    const data = await getJSON(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderAnswer(pending, data);
  } catch (e) {
    pending.className = "msg err";
    pending.textContent = `Error: ${e.message}`;
  } finally {
    send.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("ask-form").addEventListener("submit", onAsk);
  loadEmployees();
  checkHealth();
});
