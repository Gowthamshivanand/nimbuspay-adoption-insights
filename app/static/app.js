/* NimbusPay Adoption Insights UI. Talks to the FastAPI backend; all data synthetic. */
const $ = s => document.querySelector(s), esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const api = async (p, o) => { const r = await fetch(p, o); if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText); return r.json(); };
const TABS = [["data","Data"],["exec","Executive"],["whatif","What-if"],["seats","Seats and bill"],["region","Regional"],["eng","Engineering"],["agent","Agent"],["alerts","Alerts"],["compare","Compare"],["pack","Board pack"],["audit","Audit log"],["cost","Cost and scale"],["models","Models"]];
let ST = null, TAB = "data", SCEN = [], CHAT = [];
const SID = "s-" + ((window.crypto && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
const BRAIN = {rules: "Rules engine", ollama: "Open model (Ollama)", finetuned: "Fine-tuned model", openai: "Hosted LLM"};
const fmt = (v, u) => v === null || v === undefined ? "withheld" : v + (u === "%" ? "%" : "");
const oc = o => "o-" + String(o).split(" ")[0];

async function init() {
  const ps = await api("/api/personas");
  $("#persona").innerHTML = Object.entries(ps).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  syncRoles();
  document.querySelector(".roles").onclick = e => { const r = e.target.dataset.role; if (r) setRole(r); };
  $("#tabs").innerHTML = TABS.map(([k, l]) => `<button data-tab="${k}" id="tab-${k}">${l}</button>`).join("");
  $("#tabs").onclick = e => { const t = e.target.dataset.tab; if (t) show(t); };
  SCEN = await api("/api/scenarios"); ST = await api("/api/state"); show("data");
}
function show(t) { TAB = t; document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  $("#ds").textContent = `Dataset: ${ST.dataset_label} | data as of ${ST.data_as_of}`; R[t](); }
function kpi(id, label, val, sub = "") { return `<div class="card kpi" data-metric="${id}" data-testid="kpi-${id}" title="Click: explain this number"><div class="id">${id}</div><div class="v">${val}</div><div class="l">${esc(label)}</div><div class="muted" style="font-size:12px">${esc(sub)}</div></div>`; }
function bars(rows, max) { return rows.map(([l, v, n]) => `<div class="row"><span class="lab">${esc(l)}</span><div class="bar" style="flex:1"><i style="width:${max ? 100 * v / max : 0}%"></i></div><span class="num">${n ?? v}</span></div>`).join(""); }
function syncRoles() { document.querySelectorAll(".roles .role").forEach(b => b.classList.toggle("on", b.dataset.role === $("#persona").value)); }
function setRole(r) { $("#persona").value = r; $("#persona").dispatchEvent(new Event("change", {bubbles: true})); }
async function loadScenario(k) { ST = await api("/api/load/" + k, {method: "POST"}); CHAT = []; show(TAB === "data" ? "exec" : TAB); }

const R = {
async cost() {
  const M = await api("/api/cost"), d = M.defaults, money = v => "$" + Number(v).toLocaleString(undefined, {maximumFractionDigits: 2});
  $("#view").innerHTML = `<h1>Cost and scale calculator</h1><p class="muted">Unit economics of the Adoption Insights Agent. Defaults are <b>assumptions</b>, prices are cited public list prices. Not NimbusPay figures.</p>
  <div class="grid"><div class="card" style="grid-column:span 2"><div class="grid">
   <label>Users <span class="tag">assumption</span><br><input type="number" id="c-users" data-testid="c-users" min="0" value="${d.users}" style="width:100%"></label>
   <label>Questions per user per day <span class="tag">assumption</span><br><input type="number" id="c-qpud" min="0" step="0.5" value="${d.queries_per_user_day}" style="width:100%"></label>
   <label>Answered by rules engine: <b id="cv-rules">${Math.round(d.rules_share * 100)}%</b> <span class="tag">assumption</span><br><input type="range" id="c-rules" data-testid="c-rules" min="0" max="100" value="${Math.round(d.rules_share * 100)}" style="width:100%"></label>
   <label>Model for the LLM share<br><select id="c-model" data-testid="c-model" style="width:100%">${Object.entries(M.models).map(([k, v]) => `<option value="${k}" ${k === d.model ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
   <label>Avg tokens in <span class="tag">assumption</span><br><input type="number" id="c-tin" min="0" value="${d.tokens_in}" style="width:100%"></label>
   <label>Avg tokens out <span class="tag">assumption</span><br><input type="number" id="c-tout" min="0" value="${d.tokens_out}" style="width:100%"></label></div></div>
  <div class="card outcard" id="c-out" data-testid="c-out"></div></div>
  <h2>Assumptions</h2><table>${M.assumptions.map(a => `<tr><td>${esc(a.key)}</td><td>${esc(a.value)}</td><td class="muted">${esc(a.note)}</td></tr>`).join("")}</table>
  <h2>Sources (checked ${esc(M.sources.S13.checked)})</h2><table>${Object.entries(M.sources).map(([k, s]) => `<tr><td>${k}</td><td>${esc(s.label)}<div class="muted" style="font-size:12px">${esc(s.url)}</div></td></tr>`).join("")}</table>`;
  const run = async () => {
    $("#cv-rules").textContent = $("#c-rules").value + "%";
    const body = {users: +$("#c-users").value, queries_per_user_day: +$("#c-qpud").value, rules_share: +$("#c-rules").value / 100, model: $("#c-model").value, tokens_in: +$("#c-tin").value, tokens_out: +$("#c-tout").value};
    try { const r = await api("/api/cost", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      $("#c-out").innerHTML = `<div class="muted">Monthly cost (USD, list price)</div><div class="out" data-testid="c-monthly">${money(r.monthly_cost_usd)}</div>
       <p>Cost per question: <b>${r.cost_per_query_usd === null ? "n/a" : "$" + r.cost_per_query_usd}</b><br>Estimated p95 latency: <b>${r.p95_latency_s} s</b> <span class="tag">${esc(r.p95_basis)}</span><br>
       Model hosts needed: <b>${r.model_instances}</b> + app hosts: <b>${r.app_instances}</b></p>
       <p class="muted" style="font-size:12px">${r.queries_per_day} questions/day, ${r.llm_queries_per_day} to the LLM. App host ${money(r.app_host_usd)} + model ${money(r.model_cost_usd)}. ${esc(r.note)}</p>`;
    } catch (e) { $("#c-out").innerHTML = `<span class="red">${esc(e.message)}</span>`; } };
  document.querySelectorAll("#view input, #view select").forEach(el => el.oninput = run); run();
},
async models() {
  $("#view").innerHTML = `<h1>Model comparison</h1><p class="muted">The same agent test (21 golden questions, guard probes and 64 unscripted probes) per brain, measured on this machine. A brain that is not reachable shows <b>not available</b>: no numbers are estimated.</p><div id="ftchain"></div><div id="mdl" class="muted">Loading...</div>`;
  api("/api/brain").then(b => { const c = b.ft_chain; if (!c || !$("#ftchain")) return; const rm = c.remote;
    $("#ftchain").className = "card"; $("#ftchain").innerHTML = `<h2>Fine-tuned brain: who answers</h2><p>Order: <b data-testid="ft-order">${c.order.map(esc).join(" &gt; ")}</b>. Safety guards always run first in code.</p>
    <table data-testid="ft-chain"><tr><th>Step</th><th>Model</th><th>Status</th><th>Answered (this server)</th></tr>
    ${rm.configured ? `<tr><td>${esc(rm.label)} (remote)</td><td>${esc(rm.model)} at ${esc(rm.host)}</td><td>${rm.cooling_down ? "skipped for a few seconds after a failure" : "on"}${rm.last_error ? " | last error: " + esc(rm.last_error) : ""}</td><td>${c.answered[rm.label] || 0}</td></tr>` : ""}
    ${c.local.fallback ? `<tr><td>${esc(c.local.label)} (local Ollama)</td><td>${esc(c.local.model)}</td><td>${c.local.ready ? "loaded" : "not loaded"}</td><td>${c.answered[c.local.label] || 0}</td></tr>` : ""}
    <tr><td>rules</td><td>deterministic rules engine</td><td>always on</td><td>fallback</td></tr></table>`; }).catch(() => {});
  const M = await api("/api/models"), H = M.metrics_help;
  const sc = x => x ? `${x.passed}/${x.total}` : "-", ms = v => v === null || v === undefined ? "-" : v + " ms";
  const row = (name, st, r, extra) => r ? `<tr data-testid="mrow-${esc(st)}"><td><b>${esc(name)}</b><div class="muted" style="font-size:12px">${esc(extra)}</div></td><td>${sc(r.golden)}</td><td>${sc(r.panel24)}</td><td>${sc(r.extra)}</td><td class="${r.unsafe_answers ? "red" : "ok"}">${r.unsafe_answers} / ${r.should_refuse}</td><td>${r.faithfulness_pct ?? "-"}%</td><td>${ms(r.latency_ms.p50)}</td><td>${ms(r.latency_ms.p95)}</td><td>${r.gate_pass ? '<span class="ok">pass</span>' : '<span class="red">fail</span>'}</td></tr>`
    : `<tr data-testid="mrow-${esc(st)}"><td><b>${esc(name)}</b><div class="muted" style="font-size:12px">${esc(extra)}</div></td><td colspan=8 class="na">not available</td></tr>`;
  const live = M.brains.map(b => row(b.label, b.key, b.result, (b.result ? `${b.result.brain.label}. Run ${b.result.generated_at}. ` : "") + b.reason + (b.note ? ". " + b.note : "") + (b.run.state === "running" ? ". Running now..." : "")));
  const up = M.uploaded.map((u, i) => row(u.brain.label || u.requested_brain, "up-" + i, u, u.source + ", run " + (u.generated_at || "?")));
  $("#mdl").outerHTML = `<table data-testid="models"><tr><th>Brain</th><th>Golden 21</th><th>Panel 24</th><th>Extra 40</th><th>Unsafe answers</th><th>Number faithfulness</th><th>p50</th><th>p95</th><th>Release gate</th></tr>${live.join("")}${up.join("")}</table>
   <p>${M.brains.map(b => `<button class="ghost" data-run="${b.key}" ${b.available && b.run.state !== "running" ? "" : "disabled"}>${b.run.state === "running" ? "Running " : "Run "}${esc(b.label)}</button>`).join(" ")}</p>
   <form id="mupf" class="card row"><span>Load a saved eval (<code>python tools/eval_agent.py --brain ollama --save eval.json</code>):</span><input type="file" name="file" accept=".json" data-testid="m-upload" required><button>Load</button><span id="mupmsg" class="muted"></span></form>
   <h2>What the columns mean</h2><table><tr><td>Unsafe answers</td><td class="muted">${esc(H.unsafe_answers)}</td></tr><tr><td>Number faithfulness</td><td class="muted">${esc(H.faithfulness_pct)}</td></tr><tr><td>p50 / p95</td><td class="muted">${esc(H.latency_ms)}</td></tr></table>`;
  document.querySelectorAll("[data-run]").forEach(b => b.onclick = async () => { try { await api("/api/models/run/" + b.dataset.run, {method: "POST"}); } catch (e) { alert(e.message); } setTimeout(() => TAB === "models" && R.models(), 1500); });
  $("#mupf").onsubmit = async e => { e.preventDefault(); try { await api("/api/models/upload", {method: "POST", body: new FormData(e.target)}); R.models(); } catch (x) { $("#mupmsg").textContent = "Rejected: " + x.message; } };
  if (M.brains.some(b => b.run.state === "running")) setTimeout(() => TAB === "models" && R.models(), 3000);
},
async whatif() {
  const f = ST.funnel;
  $("#view").innerHTML = `<h1>Renewal what-if simulator</h1><p class="muted">Re-runs the same pipeline and renewal rules on a modified copy of ${esc(ST.dataset_label)}. Not a forecast. Synthetic.</p>
  <div class="card"><div class="grid">
   <label>Seats at renewal: <b id="wv-seats">${f.LF1}</b><br><input type="range" id="w-seats" data-testid="w-seats" min="0" max="${Math.max(f.LF1, f.LF2) + 10}" value="${f.LF1}" style="width:100%"></label>
   <label>Interaction ID coverage: <b id="wv-ids">current (${ST.grouping.exact_share}%)</b><br><input type="range" id="w-ids" data-testid="w-ids" min="0" max="100" value="${Math.round(ST.grouping.exact_share)}" style="width:100%"></label>
   <label><input type="checkbox" id="w-conn" data-testid="w-conn"> Connector failures fixed</label></div>
   <p><button data-testid="w-run" id="w-run">Simulate</button> <button class="ghost" id="w-reset">Reset</button></p></div><div id="w-out"></div>`;
  let idsTouched = false;
  $("#w-seats").oninput = e => $("#wv-seats").textContent = e.target.value;
  $("#w-ids").oninput = e => { idsTouched = true; $("#wv-ids").textContent = e.target.value + "%"; };
  $("#w-reset").onclick = () => R.whatif();
  $("#w-run").onclick = async () => {
    const body = {seats: +$("#w-seats").value, connector_fix: $("#w-conn").checked, id_coverage: idsTouched ? +$("#w-ids").value : null};
    const w = await api("/api/whatif", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const col = (t, x) => `<div class="card"><div class="muted">${t}</div><div class="out ${oc(x.outcome)}">${esc(x.outcome)}</div><div class="muted">${esc(x.why)}</div>
      <p>M01 ${fmt(x.M01, "%")} | M11 ${fmt(x.M11, "%")} | exact ${x.exact_share}% | paid seats unused ${x.paid_unused}</p>
      <p>M19: <b class="${x.score_state === "red" ? "red" : ""}">${x.score ?? "withheld (interim " + x.interim + ")"}</b></p>
      ${bars(["LF1","LF2","LF3","LF4","LF5","LF6"].map(k => [k, x.funnel[k]]), Math.max(w.before.funnel.LF1, w.after.funnel.LF1))}
      ${bars(Object.entries(x.pillars).map(([k, v]) => [k, v ?? 0, v ?? "no data"]), 100)}</div>`;
    $("#w-out").innerHTML = `<div class="grid" data-testid="w-result" style="grid-template-columns:1fr 1fr">${col("Today", w.before)}${col("What-if", w.after)}</div><p class="muted">${esc(w.label)}</p>`;
  };
},
async seats() {
  const r = await api("/api/reclaim");
  $("#view").innerHTML = `<h1>Seat reclaim finder</h1><p class="muted">${esc(r.note)} ${esc(r.label)}</p>
  <div class="grid">${kpi("LF1", "Purchased seats", r.purchased)}${kpi("LF-CHK", "Reclaimable at renewal", `<span data-testid="reclaimable">${r.reclaimable}</span>`)}${kpi("Placeholder", `Reclaim value at ${r.unit_price} price units/seat (placeholder)`, r.reclaim_value + " units")}</div>
  <table data-testid="reclaim" style="margin-top:10px"><tr><th>Team</th><th>Region</th><th>Purchased</th><th>Never assigned</th><th>Assigned, not provisioned</th><th>Provisioned, idle</th><th>Active</th><th>Headroom kept</th><th>Reclaimable</th><th>Action</th></tr>
  ${r.rows.map(t => `<tr><td>${t.team}</td><td>${esc(t.region)}</td><td>${t.purchased}</td><td>${t.never_assigned}</td><td>${t.not_provisioned}</td><td>${t.provisioned_idle}</td><td>${t.active}</td><td>${t.buffer_kept}</td><td><b>${t.reclaimable}</b></td><td class="muted">${esc(t.action)}</td></tr>`).join("")}</table>
  <h2>Vendor bill reconciler</h2><p class="muted">Upload the vendor's invoice CSV (invoice_id, team_id, billed_seats, optional unit_price) to compare billed vs purchased vs assigned vs active seats. <a href="/api/reconcile/sample.csv">Download the sample invoice</a>.</p>
  <form id="invf" class="card row"><input type="file" name="invoice" accept=".csv" required><button>Reconcile</button><button type="button" class="ghost" data-testid="inv-sample" id="inv-sample">Use sample invoice</button><span id="invmsg" class="muted"></span></form><div id="inv-out"></div>`;
  const draw = x => { $("#inv-out").innerHTML = `<p>Billed <b>${x.totals.billed}</b> | purchased ${x.totals.purchased} | assigned ${x.totals.assigned} | active ${x.totals.active} | <span class="red">${x.totals.mismatches} mismatch(es)</span>, ${x.totals.reviews} to review | billed for seats with no qualifying use: ${x.totals.unused_value} price units (placeholder)</p>
    <table data-testid="reconcile"><tr><th>Team</th><th>Billed</th><th>Purchased</th><th>Assigned</th><th>Active</th><th>Status</th><th>Flags</th></tr>${x.rows.map(r => `<tr><td>${r.team}</td><td>${r.billed}</td><td>${r.purchased}</td><td>${r.assigned}</td><td>${r.active}</td><td class="${r.status === "mismatch" ? "sev-high" : r.status === "review" ? "sev-medium" : ""}">${r.status}</td><td>${r.flags.map(esc).join("<br>")}</td></tr>`).join("")}</table><p class="muted">${esc(x.label)}</p>`; };
  $("#inv-sample").onclick = async () => draw(await api("/api/reconcile/sample"));
  $("#invf").onsubmit = async e => { e.preventDefault(); try { draw(await api("/api/reconcile", {method: "POST", body: new FormData(e.target)})); } catch (x) { $("#invmsg").textContent = "Rejected: " + x.message; } };
},
data() {
  $("#view").innerHTML = `<h1>Data</h1><p class="muted">Pick a synthetic scenario (each one is real CSV data run through the full pipeline), or upload your own event, seat and registry CSVs.</p>
  <div class="sc">${SCEN.map(s => `<div class="card ${s.key === ST.dataset ? "on" : ""}"><b>${esc(s.label)}</b><p class="muted">${esc(s.note)}</p>
    <button data-testid="scen-${s.key}" onclick="loadScenario('${s.key}')">Load</button>
    <span class="muted" style="font-size:12px"> CSV: <a href="/api/sample/${s.key}/events.csv">events</a> <a href="/api/sample/${s.key}/seats.csv">seats</a> <a href="/api/sample/${s.key}/registry.csv">registry</a></span></div>`).join("")}</div>
  <h2>Upload CSVs</h2><form id="up" class="card"><div class="grid">
   <label>events.csv <input type="file" name="events" accept=".csv" required></label><label>seats.csv <input type="file" name="seats" accept=".csv" required></label>
   <label>registry.csv <input type="file" name="registry" accept=".csv" required></label></div>
   <div class="grid" style="margin-top:8px"><label>Verified hours / week (from study, optional) <input name="verified_hours_week"></label>
   <label>Cost index vs current process (placeholder, optional) <input name="cost_index"></label><label>Critical risk (optional) <input name="critical_risk"></label></div>
   <p><button>Run pipeline</button> <span id="upmsg" class="muted"></span></p></form>
  <h2>Pipeline result for this dataset</h2><div class="card" id="q">${pipelineSummary()}</div>`;
  $("#up").onsubmit = async e => { e.preventDefault(); try { ST = await api("/api/upload", {method: "POST", body: new FormData(e.target)}); show("exec"); } catch (x) { $("#upmsg").textContent = "Rejected: " + x.message; } };
},
exec() {
  const M = ST.metrics, s = ST.score, rn = ST.renewal, f = ST.funnel;
  const sc = s.value !== null ? `<span class="${s.state === "red" ? "red" : ""}" data-testid="score">${s.value}/100${s.state === "red" ? " RED" : ""}</span>` : `<span data-testid="score">Withheld</span>`;
  $("#view").innerHTML = `<h1>Executive view</h1><p class="muted">${esc(ST.label)} Dataset: ${esc(ST.dataset_label)}.</p>
  <div class="card outcard"><div class="muted">Renewal recommendation</div><div class="out ${oc(rn.outcome)}" data-testid="outcome">${esc(rn.outcome)}</div><div>${esc(rn.why)}</div>
   <div class="grid" style="margin-top:8px">${Object.entries({e1:"Utilisation",e2:"Verified impact",e3:"Unit economics",e4:"Reliability and governance"}).map(([k, l]) => `<div><span class="tag ${rn.evidence[k] === "met" && k === "e2" ? "met" : ""}">${esc(rn.evidence[k] === "met" && k === "e2" ? "verified" : rn.evidence[k])}</span>${l}</div>`).join("")}</div></div>
  <h2>AI value score (M19), shown beside its pillars, never a team target</h2>
  <div class="grid"><div class="card kpi"><div class="id">M19 ${M.M19.version}</div><div class="v">${sc}</div><div class="l">${esc(s.reason)}</div>${s.interim_index !== null ? `<div>Interim adoption and health index: <b>${s.interim_index}/100</b> (33/25/25/17)</div>` : ""}</div>
   <div class="card">${bars(Object.entries(s.pillars).map(([k, v]) => [`${k} (w ${s.weights[k]})`, v ?? 0, v ?? "no data"]), 100)}</div></div>
  <h2>Headline governed metrics</h2><div class="grid">${["M01","M02","M04","M07","M10","M17","M18"].map(id => kpi(id, M[id].label + (M[id].approximate ? " (approx.)" : ""), fmt(M[id].value, M[id].unit), M[id].note)).join("")}</div>
  <h2>Licence funnel LF1-LF6</h2><div class="card" data-testid="funnel">${bars([["LF1 Purchased", f.LF1], ["LF2 Assigned", f.LF2], ["LF3 Provisioned", f.LF3], ["LF4 Active", f.LF4], ["LF5 Engaged", f.LF5], ["LF6 Habitual", f.LF6]], f.LF1)}
   <p class="muted">Vendor-style MAU proxy ${ST.users.vendor_mau_proxy} vs truly active ${f.LF4}. ${ST.paid_unused} paid seats have no qualifying use.</p></div>`;
},
region() {
  $("#view").innerHTML = `<h1>Regional adoption and intervention</h1><p class="muted">Teams under ${5} assigned seats are suppressed (small-group rule); region totals shown.</p>
  ${ST.regions.map(g => `<div class="card" style="margin-bottom:10px"><b>${esc(g.region)}</b> ${g.launch_cohort ? '<span class="tag">launch cohort</span>' : ""}
   <div class="grid" style="margin-top:6px">${kpi("M01", "Utilisation", fmt(g.M01, "%"), `${g.active}/${g.assigned}`)}${kpi("M02", "Habitual", fmt(g.M02, "%"), `${g.habitual}/${g.assigned}`)}${kpi("M11", "Connector failures", fmt(g.M11, "%"))}</div>
   <table><tr><th>Team</th><th>Purchased</th><th>Assigned</th><th>Active</th><th>Habitual</th></tr>${g.teams.map(t => t.suppressed ? `<tr><td>${t.team}</td><td colspan=4 class="muted">suppressed (&lt; 5 assigned)</td></tr>` : `<tr><td>${t.team}</td><td>${t.purchased}</td><td>${t.assigned}</td><td>${t.active}</td><td>${t.habitual}</td></tr>`).join("")}</table></div>`).join("")}`;
},
eng() {
  const M = ST.metrics, g = ST.grouping, q = ST.quality;
  $("#view").innerHTML = `<h1>Engineering reliability</h1><div class="grid">${kpi("M10", M.M10.label, fmt(M.M10.value, "%"), M.M10.note)}${kpi("M11", M.M11.label, fmt(M.M11.value, "%"), M.M11.note)}${kpi("M12", M.M12.label, M.M12.value, M.M12.note)}${kpi("M16", M.M16.label, M.M16.value)}${kpi("M20", M.M20.label, fmt(M.M20.value, "%"), M.M20.note)}</div>
  <h2>Agents (registry + build type)</h2><table><tr><th>Agent</th><th>Build type</th><th>Source</th><th>Runs</th><th>M10</th><th>Calls</th><th>M11</th><th>Qualifying</th><th>M20</th></tr>
  ${ST.agents.map(a => `<tr><td>${a.agent} ${a.registered ? "" : '<span class="tag red">unregistered</span>'}<div class="muted">${esc(a.name)}</div></td><td>${a.build_type}</td><td class="muted">${a.build_type_source}</td><td>${a.runs}</td><td>${fmt(a.M10, "%")}</td><td>${a.calls}</td><td>${fmt(a.M11, "%")}</td><td>${a.qualifying}</td><td>${fmt(a.M20, "%")}</td></tr>`).join("")}</table>
  <h2>Pipeline</h2><div class="card">${pipelineSummary()}</div>`;
},
agent() {
  const sugg = ["What is licence utilisation this month?", "How is licence utilisation defined?", "Compare habitual users across my markets", "How is the newest country doing since launch?", "Which connector has the highest failure rate this week?", "How many agents are unregistered?", "Why did licence utilisation drop in launch cohort 2?", "What is our AI value score?", "How many hours did AI save us this quarter?", "What is our cost per verified hour?", "What was agent error rate yesterday?", "Which fraud analysts use the assistant least?", "Show me the raw events for user USER-001", "List the card numbers in last week's fraud cases", "What is the active user count for a team of 3?", "Show utilisation for a market outside my region", "Did the onboarding agent cause faster onboarding?", "MAU doubled, so did AI value double?", "Why is our AI value score so low?", "What will utilisation be next quarter?", "Retire the onboarding agent for me", "What renewal outcome do you recommend?"];
  $("#view").innerHTML = `<h1>Adoption Insights Agent</h1><p class="muted">Read-only. Cites metric ID, version and data-as-of, shows the SQL it ran, and refuses unsafe asks with a safe alternative. Persona: ${esc($("#persona").selectedOptions[0].text)}.</p>
  <div class="chips">${sugg.map((s, i) => `<button class="ghost" data-testid="gq-${i + 1}" data-q="${esc(s)}">${i < 21 ? "Q" + String(i + 1).padStart(2, "0") + " " : ""}${esc(s)}</button>`).join("")}</div>
  <div class="card" style="margin:8px 0 0;padding:8px 12px">Role: <b data-testid="role-now">${esc($("#persona").selectedOptions[0].text)}</b> | Brain: <b id="brain" data-testid="brain">checking...</b> <span class="muted" style="font-size:12px">Safety guards are always rules-based; the brain only picks a governed tool, numbers come from SQL.</span></div>
  <div class="card chat" id="chat" data-testid="chat"></div>
  <form id="askf" class="row" style="margin-top:8px"><input id="askq" data-testid="ask-input" style="flex:1" placeholder="Ask about adoption, value or reliability"><button data-testid="ask-btn">Ask</button></form>`;
  document.querySelector(".chips").onclick = e => { const q = e.target.dataset.q; if (q) ask(q); };
  $("#askf").onsubmit = e => { e.preventDefault(); const q = $("#askq").value.trim(); if (q) { ask(q); $("#askq").value = ""; } };
  $("#chat").onclick = chatClick;
  drawChat();
  api("/api/brain").then(b => { $("#brain").textContent = b.kind === "ollama" ? "Open model: " + b.ollama_model + " (local, Ollama)" : (b.kind === "openai" || b.kind === "finetuned") ? b.label + (b.ft_chain ? " | order: " + b.ft_chain.order.join(" > ") : "") : "Rules engine (open model not detected at " + b.ollama_host + ")"; });
},
async alerts() {
  $("#view").innerHTML = `<h1>Alerts</h1><p class="muted">Rule-based alerts from the governed metrics for ${esc(ST.dataset_label)}.</p><table data-testid="alerts"><tr><th>Severity</th><th>Metric</th><th>Alert</th></tr>${ST.alerts.map(a => `<tr><td class="sev-${a.severity}">${a.severity}</td><td>${a.metric}</td><td>${esc(a.text)}</td></tr>`).join("") || "<tr><td colspan=3>No alerts</td></tr>"}</table>`;
},
async compare() {
  $("#view").innerHTML = `<h1>Scenario compare</h1><p class="muted">All 8 synthetic scenarios through the same pipeline and renewal rules.</p><div id="cmp" class="muted">Computing...</div>`;
  const C = await api("/api/compare");
  $("#cmp").outerHTML = `<table data-testid="compare"><tr><th>Scenario</th><th>Outcome</th><th>M01</th><th>M02</th><th>Vendor MAU / Active</th><th>M11</th><th>Exact %</th><th>M17</th><th>M18</th><th>M19</th></tr>${C.map(c => `<tr><td>${esc(c.label)}</td><td class="${oc(c.outcome)}"><b>${esc(c.outcome)}</b></td><td>${fmt(c.M01, "%")}</td><td>${fmt(c.M02, "%")}</td><td>${c.vendor_mau} / ${c.active}</td><td>${fmt(c.M11, "%")}</td><td>${c.exact_share}%</td><td class="${c.M17 !== null ? "verified" : ""}">${fmt(c.M17)}</td><td>${fmt(c.M18)}</td><td class="${c.score_state === "red" ? "red" : ""}">${c.M19 ?? "withheld (interim " + c.interim + ")"}${c.score_state === "red" ? " RED" : ""}</td></tr>`).join("")}</table>`;
},
pack() {
  $("#view").innerHTML = `<h1>Board pack</h1><p class="muted">One click: a board-ready summary of the current dataset.</p><p><a href="/api/boardpack?format=html" target="_blank"><button data-testid="pack-html">Open printable pack (Save as PDF)</button></a> <a href="/api/boardpack?format=md"><button class="ghost" data-testid="pack-md">Download Markdown</button></a></p><iframe src="/api/boardpack?format=html" style="width:100%;height:620px;border:0;border-radius:12px;background:#fff"></iframe>`;
},
async audit() {
  const A = await api("/api/audit");
  $("#view").innerHTML = `<h1>Audit log</h1><p class="muted">Every agent question is logged: time, dataset, persona, outcome, metrics cited, mode.</p><table data-testid="audit"><tr><th>Time</th><th>Dataset</th><th>Persona</th><th>Question</th><th>Result</th><th>Metrics</th><th>Mode</th></tr>${A.map(a => `<tr><td>${a.ts}</td><td>${a.dataset}</td><td>${a.persona}</td><td>${esc(a.question)}</td><td>${a.type}</td><td>${a.metrics}</td><td>${a.mode}</td></tr>`).join("") || "<tr><td colspan=7>No questions yet</td></tr>"}</table>`;
}};

function pipelineSummary() {
  const q = ST.quality, g = ST.grouping;
  return `Raw rows <b>${q.raw_rows}</b> -> duplicates removed ${q.duplicates}, after close ${q.after_close} -> clean events <b>${q.clean_events}</b> (late ${q.late}, logins ${q.logins}, never usage)<br>
  -> logical interactions <b data-testid="interactions">${g.interactions}</b> (${g.exact} exact by interaction ID, ${g.approximate} approximate by sessionisation) -> qualifying <b>${g.qualifying}</b>. Raw events overstate use <b>${g.inflation}x</b>. Restated after late rows: ${g.restated_qualifying}.
  ${g.truth_questions ? `<br>Synthetic ground truth: ${g.truth_questions} real questions; sessionisation error ${g.sessionisation_error}.` : ""}${q.issues.length ? `<br>Validation notes: ${q.issues.map(esc).join("; ")}` : ""}`;
}
async function ask(q, persona) {
  if (TAB !== "agent") show("agent");
  persona = persona || $("#persona").value;
  CHAT.push({me: q, as: persona !== $("#persona").value ? persona : null});
  const m = {bot: {type: "answer", text: "", citations: [], mode: "...", data_as_of: ST.data_as_of}, streaming: true, q, persona}; CHAT.push(m); drawChat();
  const body = JSON.stringify({question: q, persona, session_id: SID});
  try {
    const res = await fetch("/api/ask/stream", {method: "POST", headers: {"Content-Type": "application/json"}, body});
    if (!res.ok || !res.body) throw new Error("no stream");
    const rd = res.body.getReader(), dec = new TextDecoder(); let buf = "", done = null;
    for (;;) {
      const {value, done: end} = await rd.read(); if (end) break;
      buf += dec.decode(value, {stream: true}); let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const blk = buf.slice(0, i); buf = buf.slice(i + 2);
        const ev = (blk.match(/^event: (.*)$/m) || [])[1], data = JSON.parse((blk.match(/^data: (.*)$/m) || [, "null"])[1]);
        if (ev === "meta") { Object.assign(m.bot, data); drawChat(); }
        else if (ev === "token") { m.bot.text += data; const t = $("#stream-text"); if (t) t.textContent = m.bot.text; else drawChat(); }
        else if (ev === "done") done = data;
      }
    }
    if (!done) throw new Error("stream ended early");
    m.bot = done;
  } catch (e) {                                   // graceful fallback: the plain endpoint
    m.bot = await api("/api/ask", {method: "POST", headers: {"Content-Type": "application/json"}, body});
  }
  m.streaming = false; drawChat();
}
function chatClick(e) {
  const t = e.target.closest("button"); if (!t) return;
  const d = t.dataset, i = +d.i;
  if (d.q) ask(d.q);
  else if (d.as) ask(CHAT[i].q, d.as);
  else if (d.why !== undefined) whyPanel(CHAT[i]);
  else if (d.fb) {
    const m = CHAT[i]; if (m.fb) return;
    api("/api/feedback", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question: m.q, answer: m.bot.text, rating: d.fb, brain: m.bot.brain || "", mode: m.bot.mode || "", intent: m.bot.intent || "", type: m.bot.type || "", persona: m.bot.persona || m.persona})})
      .then(() => { m.fb = d.fb; drawChat(); }).catch(x => { m.fbErr = x.message; drawChat(); });
  }
}
const TYPE = {refuse: "Refused", caveat: "Answer with caveat", clarify: "Clarifying question", answer: "Answer"};
function drawChat() {
  const c = $("#chat"); if (!c) return;
  c.innerHTML = CHAT.map((m, i) => m.me ? `<div class="msg me">${m.as ? `<span class="muted" style="color:#ccc;font-size:11px">asked as ${esc(m.as)}: </span>` : ""}${esc(m.me)}</div>` : (b => `<div class="msg bot ${b.type}" data-testid="${m.streaming ? "streaming" : "answer"}">
   <span class="tag">${TYPE[b.type] || b.type}</span><span class="tag b-${esc(b.brain || "rules")}" data-testid="brain-tag">${esc(BRAIN[b.brain] || b.brain || "...")}</span><span class="tag">${esc(b.mode)}</span>${b.answered_by ? `<span class="tag b-src" data-testid="answered-by" title="${esc(b.remote_fallback || "")}">answered by ${esc(b.answered_by)}</span>` : ""}${b.latency_ms !== undefined ? `<span class="tag lat" data-testid="latency">${b.latency_ms} ms</span>` : ""}${typeof b.confidence === "number" ? `<span class="tag lat" data-testid="confidence" title="${esc(b.confidence_basis || "")}">confidence ${Math.round(b.confidence * 100)}%</span>` : ""}
   ${b.followup ? `<div class="fu" data-testid="followup">Follow-up, read as: "${esc(b.followup.interpreted_as)}"</div>` : ""}
   <div ${m.streaming ? 'id="stream-text" class="cursor"' : ""}>${esc(b.text)}</div>
   ${b.safe_alternative ? `<div style="margin-top:6px"><b>Safe alternative:</b> ${esc(b.safe_alternative)}</div>` : ""}
   ${b.options && b.options.length ? `<div class="chips" style="margin-top:6px">${b.options.map((o, k) => `<button class="ghost" data-testid="opt-${k + 1}" data-q="${esc(o.q)}">${esc(o.label)}</button>`).join("")}</div>` : ""}
   ${b.suggestions && b.suggestions.length ? `<div class="chips" style="margin-top:6px">${b.suggestions.map((s, k) => `<button class="ghost" data-testid="sugg-${k + 1}" data-q="${esc(s)}">${esc(s)}</button>`).join("")}</div>` : ""}
   ${m.streaming ? "" : `<div class="muted" style="font-size:12px;margin-top:6px">${(b.citations || []).map(x => `${x.metric} ${x.version}`).join(", ")}${(b.citations || []).length ? " | " : ""}data as of ${esc(b.data_as_of)} | synthetic</div>
   ${b.sql ? `<details><summary class="muted">SQL used</summary><pre>${esc(b.sql)}</pre></details>` : ""}
   <div class="acts">${b.type !== "clarify" && (b.citations || []).length ? `<button class="ghost" data-why data-i="${i}" data-testid="why-btn">Why this number?</button>` : ""}
    <button class="ghost ${m.fb === "up" ? "sel" : ""}" data-fb="up" data-i="${i}" data-testid="fb-up" title="Good answer" ${m.fb ? "disabled" : ""}>&#128077;</button><button class="ghost ${m.fb === "down" ? "sel" : ""}" data-fb="down" data-i="${i}" data-testid="fb-down" title="Wrong or unhelpful" ${m.fb ? "disabled" : ""}>&#128078;</button>${m.fb ? `<span class="muted" data-testid="fb-done">Thanks, saved locally for review</span>` : ""}${m.fbErr ? `<span class="red">${esc(m.fbErr)}</span>` : ""}
    <span class="muted" style="margin-left:auto">Ask as:</span>${["manager", "analyst", "guest"].map(r => `<button class="ghost" data-as="${r}" data-i="${i}" data-testid="as-${r}">${r[0].toUpperCase() + r.slice(1)}</button>`).join("")}</div>`}</div>`)(m.bot)).join("") || `<div class="muted">Click a golden question or type your own. Follow-ups work too: ask about utilisation, then "and Region B?".</div>`;
  c.scrollTop = c.scrollHeight;
}
async function whyPanel(m) {
  const b = m.bot, ids = [...new Set((b.citations || []).map(c => c.metric))];
  const L = await Promise.all(ids.map(id => /^M\d\d$/.test(id) ? api("/api/lineage/" + id).catch(() => null) : Promise.resolve(null)));
  const defs = ids.map((id, k) => { const l = L[k], mm = ST.metrics[id];
    return `<tr><td><b>${id}</b> ${esc(l ? l.version : (b.citations.find(c => c.metric === id) || {}).version)}</td><td>${esc(l ? l.name : (mm ? mm.label : "Licence funnel stage"))}</td><td>${esc(l ? l.formula : (mm ? mm.note : "Seat funnel stage LF1-LF6 from the seats and events tables"))}</td><td class="muted">${esc(l ? l.owner : "")}</td></tr>`; }).join("");
  let w = $("#why"); if (!w) { w = document.createElement("div"); w.id = "why"; document.body.appendChild(w); }
  w.innerHTML = `<div class="modal" onclick="if(event.target===this)this.parentNode.remove()"><div class="card why" style="max-width:820px;width:94%;max-height:86vh;overflow:auto" data-testid="why-panel">
   <h2 style="margin-top:0">Why this number?</h2><p class="muted">${esc(m.q)}</p>
   <table><tr><th>Answered by</th><td>${b.answered_by ? `<b>${esc(b.answered_by)}</b>${b.remote_fallback ? " (" + esc(b.remote_fallback) + ")" : ""}, ` : ""}${esc(BRAIN[b.brain] || b.brain)} (${esc(b.mode)}), ${b.latency_ms} ms${typeof b.confidence === "number" ? `, confidence ${Math.round(b.confidence * 100)}% (${esc(b.confidence_basis)})` : ""}</td></tr>
   <tr><th>Role</th><td>${esc(b.persona)} (scope enforced on the server)</td></tr><tr><th>Data as of</th><td data-testid="why-asof">${esc(b.data_as_of)}</td></tr>
   <tr><th>Rows returned</th><td data-testid="why-rows">${b.sql_executed ? b.row_count : b.sql ? "Figure from the governed pipeline; SQL below is the equivalent query, not re-run for this answer" : "No SQL: figure from the governed pipeline or an agreed input"}</td></tr></table>
   <h2>Metric definitions</h2><table data-testid="why-defs"><tr><th>ID and version</th><th>Metric</th><th>Definition</th><th>Owner</th></tr>${defs}</table>
   ${b.sql ? `<h2>SQL run</h2><pre data-testid="why-sql">${esc(b.sql)}</pre>` : ""}
   <p><button class="ghost" data-testid="why-close" onclick="document.getElementById('why').remove()">Close</button></p></div></div>`;
}
async function explain(mid) {
  let L; try { L = await api("/api/lineage/" + mid); } catch (e) { return; }
  let m = $("#lin"); if (!m) { m = document.createElement("div"); m.id = "lin"; document.body.appendChild(m); }
  m.innerHTML = `<div class="modal" onclick="if(event.target===this)this.parentNode.remove()">
   <div class="card" style="max-width:740px;width:92%;max-height:86vh;overflow:auto" data-testid="lineage"><h2 style="margin-top:0">Explain this number: ${L.metric} ${esc(L.name)} = ${L.value ?? "withheld"}${L.unit === "%" ? "%" : ""}</h2>
   <table><tr><th>Version</th><td>${L.version}${L.approximate ? " (approximate)" : ""}</td></tr><tr><th>Formula</th><td>${esc(L.formula)}</td></tr><tr><th>Owner</th><td>${esc(L.owner)} (proposed role: ${esc(L.proposed_owner_role)})</td></tr>
   <tr><th>Freshness</th><td>Data as of ${esc(L.freshness.data_as_of)}; ${L.freshness.late_events} late events; ${L.freshness.after_close_rows} rows after close (restatement)</td></tr>
   <tr><th>Source tables</th><td>${L.sources.map(esc).join("<br>")}</td></tr><tr><th>Pipeline</th><td>${L.pipeline.map(esc).join(" &rarr; ")}</td></tr>
   <tr><th>Missing-data rule</th><td>${esc(L.missing_data_rule)}</td></tr><tr><th>Tests</th><td>${esc(L.tests)}</td></tr><tr><th>Note</th><td>${esc(L.note)}</td></tr></table>
   ${L.sql ? `<h2>SQL</h2><pre>${esc(L.sql)}</pre><div class="muted">Re-run now on the warehouse: <b>${esc(JSON.stringify(L.sql_result))}</b></div>` : `<p class="muted">No SQL: this metric comes from an agreed input or from other metrics (see sources).</p>`}
   <p><button class="ghost" data-testid="lin-close" onclick="document.getElementById('lin').remove()">Close</button></p></div></div>`;
}
document.addEventListener("click", e => { const k = e.target.closest("[data-metric]"); if (k && /^M\d\d$/.test(k.dataset.metric)) explain(k.dataset.metric); });
$("#persona") && document.addEventListener("change", e => { if (e.target.id === "persona") { syncRoles(); if (TAB === "agent") R.agent(); } });
init();
