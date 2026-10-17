"use strict";
const D = window.WB; // workbook tabs (from the v9 supporting workbook)
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct = (n, d, dp = 1) => d > 0 ? (100 * n / d).toFixed(dp) : "n/a";
const fmt = n => Number(n).toLocaleString("en-US");
const metric = id => D.Metric_Dictionary.find(m => m["Metric ID"] === id);

/* Illustrative synthetic demo data (not NimbusPay figures) */
const MIN_GROUP = 10; // demo minimum reporting size, in assigned seats (to be agreed)
const TEAMS = [
  ["TEAM-A","Region A","Established","Fraud operations",120,112,110,86,64,41],
  ["TEAM-B","Region A","Established","Support",80,72,70,49,33,19],
  ["TEAM-C","Region A","Launch cohort 1","Merchant onboarding",40,31,29,17,10,5],
  ["TEAM-J","Region A","Launch cohort 3","Support",6,6,5,3,1,1],
  ["TEAM-D","Region B","Established","Fraud operations",150,138,135,97,70,44],
  ["TEAM-E","Region B","Launch cohort 2","Merchant onboarding",60,52,48,22,12,6],
  ["TEAM-F","Region B","Established","Compliance",3,3,3,3,2,2],
  ["TEAM-G","Region C","Established","Compliance",100,85,84,63,45,30],
  ["TEAM-H","Region C","Launch cohort 3","Support",30,24,22,11,5,2],
  ["TEAM-I","Region C","Launch cohort 2","Merchant onboarding",45,40,38,20,11,5]
].map(t => ({id:t[0],region:t[1],cohort:t[2],fn:t[3],purchased:t[4],assigned:t[5],provisioned:t[6],active:t[7],engaged:t[8],habitual:t[9]}));
/* Q07 last-month funnel for launch cohort 2 teams (illustrative synthetic) */
const Q07_BEFORE = {"TEAM-E":{assigned:36,active:22,engaged:13,habitual:7},"TEAM-I":{assigned:31,active:19,engaged:12,habitual:6}};
const STAGES = [["purchased","Purchased"],["assigned","Assigned"],["provisioned","Provisioned"],["active","Active"],["engaged","Engaged"],["habitual","Habitual"]];
let VENDOR_MAU = 512; // vendor-style MAU: any login counts (<= 544 provisioned)
const AGENTS = [
  {id:"AG-FRAUD-01",name:"Fraud-review assistant",build:"Engineer-built",reg:true,runs:4120,fail:74,p95:4.2},
  {id:"AG-ONB-02",name:"Merchant-onboarding assistant",build:"Drag-and-drop",reg:true,runs:2310,fail:90,p95:6.8},
  {id:"AG-SRCH-03",name:"Support search",build:"Engineer-built",reg:true,runs:6540,fail:59,p95:2.1},
  {id:"AG-DOC-04",name:"Compliance document summary",build:"Engineer-built",reg:true,runs:1980,fail:32,p95:5.4},
  {id:"AG-DD-05",name:"Unnamed agent (no registry entry)",build:"Drag-and-drop",reg:false,runs:410,fail:25,p95:7.9},
  {id:"AG-DD-06",name:"Unnamed agent (no registry entry)",build:"Drag-and-drop",reg:false,runs:150,fail:7,p95:6.2}
];
const CONNECTORS = [
  {id:"Ticketing",calls:5200,fail:94,prev:1.7},
  {id:"Email",calls:2100,fail:132,prev:2.0},
  {id:"Internal wiki",calls:3400,fail:41,prev:1.3}
];
const EVT_NOID = {"Engineer-built":{events:48200,noid:190},"Drag-and-drop":{events:16900,noid:6250}};
const DQ = {pass:46,all:48};
const PILLARS = [
  {k:"Reach",w:20,v:58,mm:["M02 Habitual users","M01 Licence utilisation","M03 Activation of new licences"]},
  {k:"Depth",w:15,v:46,mm:["M04 Interactions per active user","M05 Workflows covered"]},
  {k:"Outcome",w:40,v:62,mm:["M06 Verified time saved per task","M07 Task success rate","M08 Fraud handle-time change","M09 Onboarding cycle-time change"]},
  {k:"Reliability",w:15,v:81,mm:["M10 Agent error rate","M11 Connector failure rate","M12 Data freshness"]},
  {k:"Trust",w:10,v:74,mm:["M13 Negative feedback %","M14 Human override rate"]}
];
const ROLES = {
  exec:{label:"Executive sponsor",regions:["Region A","Region B","Region C"],views:["exec","regional"]},
  ra:{label:"Regional lead, Region A",regions:["Region A"],views:["exec","regional"]},
  rb:{label:"Regional lead, Region B",regions:["Region B"],views:["exec","regional"]},
  eng:{label:"Platform engineer",regions:[],views:["eng"]},
  fraud:{label:"Fraud operations lead",regions:["Region A","Region B","Region C"],fn:"Fraud operations",views:["regional"]}
};
const S = {
  role:"exec", scenario:"live", screen:"exec",
  weights:PILLARS.map(p => p.w), missing:PILLARS.map(() => false), breach:false,
  utilThr:70, cphIdx:0.9, verifiedHrsWk:180, preset:"baseline", relGap:false, idGap:false,
  lateLoad:true, buildF:"All", countMode:"raw", gap:10,
  region:"All", cohort:"All", audit:[], asOf:"17-10-2026", chat:[]
};
const W16 = () => S.scenario === "live";
const XX = v => W16() ? v : "xx";


/* Scenario presets: illustrative synthetic data only. Ranges are loosely informed by public
   adoption guidance (e.g. GitHub Copilot docs: 60-80% of assigned users active in month one,
   WAU/licence above 60% is healthy). They are not NimbusPay figures. */
const BASE = JSON.parse(JSON.stringify({TEAMS, AGENTS, CONNECTORS, EVT_NOID, PILLARS: PILLARS.map(p => p.v), VENDOR_MAU}));
const PRESETS = {
  baseline:{label:"Baseline demo", note:"Mixed picture: utilisation below the agreed threshold, so seats are right-sized."},
  healthy:{label:"Healthy adoption", note:"Most seats used weekly, verified hours reported, unit cost inside the threshold: expand.",
    f:{active:.84, engaged:.78, habitual:.72}, mau:.97, pil:[82,74,76,88,84], vh:260, cph:.7},
  overstated:{label:"Overstated usage (vendor MAU high)", note:"Vendor MAU near seat count, but few people return: real value per hour is low, so renegotiate to usage-based terms.",
    f:{active:.78, engaged:.42, habitual:.38}, mau:.99, pil:[54,28,40,80,66], vh:70, cph:1.9},
  shelfware:{label:"Shelfware (paid seats unused)", note:"Many paid and assigned seats have no qualifying use: renew and right-size.",
    f:{active:.34, engaged:.6, habitual:.55}, mau:.5, pil:[24,40,58,82,74], vh:150, cph:.95, unassign:.35},
  newcountry:{label:"New-country launch cohort", note:"A large new launch cohort is still ramping and has no verified study yet: continue a limited pilot.",
    f:{active:.7, engaged:.66, habitual:.6}, mau:.85, pil:[56,48,60,79,72], vh:null, cph:null, newc:true},
  incident:{label:"Reliability incident (connector outage)", note:"Email connector outage and a late load: renew with remediation conditions and fix-by dates.",
    f:{active:.74, engaged:.68, habitual:.6}, mau:.9, pil:[66,58,64,31,60], vh:190, cph:.85, outage:true},
  noids:{label:"Missing interaction IDs (drag-and-drop heavy)", note:"Most activity comes from drag-and-drop agents without interaction IDs, so counts are approximate and no study can attribute them: continue a limited pilot.",
    f:{active:.71, engaged:.64, habitual:.58}, mau:.9, pil:[60,50,60,70,68], vh:null, cph:null, noids:true},
  breach:{label:"Critical-risk breach (privacy)", note:"Card data found outside the masked zone: the score turns red and renewal needs remediation conditions.",
    f:{active:.8, engaged:.72, habitual:.66}, mau:.95, pil:[76,66,70,80,30], vh:230, cph:.8, breach:true}
};
function applyPreset(k) {
  const P = PRESETS[k] || PRESETS.baseline; S.preset = PRESETS[k] ? k : "baseline";
  const b = JSON.parse(JSON.stringify(BASE));
  TEAMS.length = 0; b.TEAMS.forEach(t => TEAMS.push(t));
  AGENTS.forEach((a, i) => Object.assign(a, b.AGENTS[i])); CONNECTORS.forEach((c, i) => Object.assign(c, b.CONNECTORS[i]));
  Object.keys(EVT_NOID).forEach(x => Object.assign(EVT_NOID[x], b.EVT_NOID[x]));
  PILLARS.forEach((p, i) => p.v = b.PILLARS[i]); VENDOR_MAU = b.VENDOR_MAU;
  S.breach = false; S.relGap = false; S.lateLoad = true; S.missing = PILLARS.map(() => false); S.verifiedHrsWk = 180; S.cphIdx = 0.9;
  if (P.f) {
    if (P.newc) TEAMS.push({id:"TEAM-K",region:"Region C",cohort:"Launch cohort 3",fn:"Merchant onboarding",purchased:160,assigned:140,provisioned:132,active:0,engaged:0,habitual:0},
                           {id:"TEAM-L",region:"Region B",cohort:"Launch cohort 3",fn:"Support",purchased:90,assigned:80,provisioned:75,active:0,engaged:0,habitual:0});
    TEAMS.forEach(t => {
      if (P.unassign) t.assigned = Math.min(t.assigned, Math.round(t.purchased * (1 - P.unassign)));
      t.provisioned = Math.min(t.provisioned, t.assigned);
      let fa = P.f.active; if (P.newc && t.cohort === "Launch cohort 3") fa = .3;
      if (!(t.cohort === "Launch cohort 2" && t.id in Q07_BEFORE)) t.active = Math.min(t.provisioned, Math.round(t.assigned * fa));
      else t.active = Math.min(t.provisioned, Math.max(Q07_BEFORE[t.id].active, Math.round(t.assigned * Math.min(fa, .55))));
      t.engaged = Math.round(t.active * P.f.engaged); t.habitual = Math.round(t.engaged * P.f.habitual);
    });
    const prov = sum(TEAMS, "provisioned"); VENDOR_MAU = Math.max(sum(TEAMS, "active"), Math.round(prov * P.mau));
    PILLARS.forEach((p, i) => p.v = P.pil[i]); S.verifiedHrsWk = P.vh; S.cphIdx = P.cph;
    S.lateLoad = !!P.outage; S.breach = !!P.breach; S.relGap = !!P.outage;
    if (P.outage) { const e = CONNECTORS.find(c => c.id === "Email"); e.fail = Math.round(e.calls * .31); AGENTS.find(a => a.id === "AG-ONB-02").fail = Math.round(AGENTS.find(a => a.id === "AG-ONB-02").runs * .27); }
    if (P.noids) { EVT_NOID["Drag-and-drop"].events = 41800; EVT_NOID["Drag-and-drop"].noid = 29300; EVT_NOID["Engineer-built"].events = 23100; S.missing[1] = false; }
  }
}
function scopeTeams(role = S.role) {
  const r = ROLES[role];
  return TEAMS.filter(t => r.regions.includes(t.region) && (!r.fn || t.fn === r.fn));
}
function sum(ts, k) { return ts.reduce((a, t) => a + t[k], 0); }
function totals(ts) { const o = {}; STAGES.forEach(([k]) => o[k] = sum(ts, k)); return o; }
function audit(action, detail, result) {
  const d = new Date();
  S.audit.unshift({t:d.toTimeString().slice(0,8), role:ROLES[S.role].label, action, detail, result});
  if (S.screen === "gov") renderGov();
}

/* Score logic: weighted sum, no silent imputation, critical-risk override */
function score() {
  if (!W16()) return {state:"withheld", reason:"Baselines and targets not yet set. M19 is withheld until they exist."};
  const miss = PILLARS.filter((p, i) => S.missing[i]).map(p => p.k);
  if (miss.length) return {state:"withheld", reason:"No score: " + miss.join(", ") + " pillar missing. No silent imputation."};
  const ws = S.weights.reduce((a, b) => a + b, 0);
  if (ws <= 0) return {state:"withheld", reason:"All weights are zero."};
  const v = PILLARS.reduce((a, p, i) => a + p.v * S.weights[i], 0) / ws;
  return {state: S.breach ? "red" : "ok", value: Math.round(v), raw: v, wsum: ws};
}
function verifiedHours() { return (W16() && !S.missing[2]) ? S.verifiedHrsWk : null; }
function costPerHour() { const h = verifiedHours(); return h && h > 0 ? S.cphIdx : null; } // index vs agreed threshold; platform cost is a placeholder
function renewal() {
  const t = totals(TEAMS), util = 100 * t.active / t.assigned;
  const ev = {
    e1: W16() ? (util >= S.utilThr ? "met" : "below") : "missing",
    e2: verifiedHours() ? "met" : "missing",
    e3: costPerHour() === null ? "missing" : (costPerHour() <= 1 ? "met" : "above"),
    e4: !W16() ? "missing" : (S.breach || S.relGap || S.missing[3] ? "gap" : "met")
  };
  let out;
  if (ev.e2 === "missing" || ev.e1 === "missing") out = "Continue limited pilot";
  else if (ev.e4 === "gap") out = "Renew with remediation conditions";
  else if (ev.e1 === "below") out = "Renew and right-size";
  else if (ev.e3 === "above") out = "Renegotiate";
  else out = "Expand";
  return {ev, out, util};
}

const SCREENS = [
  ["exec","Executive view"],["regional","Regional adoption and intervention"],["eng","Engineering reliability and instrumentation"],
  ["count","How we count"],["agent","Adoption Insights Agent"],["gov","Governance and responsible AI"]
];
function nav() {
  $("#nav").innerHTML = SCREENS.map(([k, l], i) => `<a data-s="${k}" class="${S.screen === k ? "on" : ""}"><span class="n">${i + 1}</span><span>${l}</span></a>`).join("") +
    `<div class="navfoot"><b>Prototype for DPM deliverable 7.</b><br>Every number here is illustrative synthetic data. Definitions come from the v9 workbook tabs. No real NimbusPay values exist yet.</div>`;
  $$("#nav a").forEach(a => a.onclick = () => go(a.dataset.s));
}
function go(s) { S.screen = s; nav(); $$(".screen").forEach(e => e.classList.toggle("on", e.id === "s-" + s)); render(); $("main").scrollTop = 0; }
function render() { ({exec:renderExec, regional:renderRegional, eng:renderEng, count:renderCount, agent:renderAgent, gov:renderGov})[S.screen](); }
function locked(view) {
  return `<div class="locked"><h2>Not in your role scope</h2><p>${esc(ROLES[S.role].label)} cannot open the ${esc(view)} view. Access is role-based, from SSO.</p><p class="small">Switch "Viewing as" in the top bar to see how access changes.</p></div>`;
}
function evTag(s) { return {met:'<span class="tag grn">Met</span>',below:'<span class="tag amb">Below threshold</span>',above:'<span class="tag amb">Above threshold</span>',missing:'<span class="tag">Missing</span>',gap:'<span class="tag red">Gap</span>'}[s]; }
function renderExec() {
  const el = $("#s-exec");
  if (!ROLES[S.role].views.includes("exec")) { el.innerHTML = `<h1>Executive view</h1><p class="sub">Monthly; supports the renewal decision.</p>` + locked("Executive"); return; }
  const ts = scopeTeams(), t = totals(ts), sc = score(), vh = verifiedHours(), cph = costPerHour(), rn = renewal();
  const scopeNote = S.role === "exec" ? "All regions, aggregate only" : "Scope: " + ROLES[S.role].regions.join(", ") + " (renewal evidence stays company-wide)";
  const sv = sc.state === "withheld" ? `<div class="scoreval wh" id="scorebox"><div class="small muted">AI value score (M19), 0-100</div><div class="big">No score</div><div class="note">${esc(sc.reason)}</div></div>`
    : `<div class="scoreval ${sc.state === "red" ? "red" : ""}" id="scorebox"><div class="small muted">AI value score (M19), 0-100</div><div class="big">${sc.value}</div><div class="note">${sc.state === "red" ? "<b style='color:var(--red)'>Flagged red: critical-risk breach.</b> The value is shown but must not be read as healthy." : "Weighted sum of five pillars. Always shown beside them."}</div></div>`;
  const pil = PILLARS.map((p, i) => `<div class="pil ${S.missing[i] || !W16() ? "miss" : ""}"><div class="pn">${p.k}</div>
    <div class="pv">${!W16() ? "xx" : S.missing[i] ? "Missing" : p.v}</div><div class="bar"><i style="width:${W16() && !S.missing[i] ? p.v : 0}%"></i></div>
    <label style="margin-top:8px">Weight <b style="color:var(--ink)">${S.weights[i]}%</b></label><input type="range" min="0" max="60" step="5" value="${S.weights[i]}" data-w="${i}" aria-label="${p.k} weight">
    <label><input type="checkbox" data-m="${i}" ${S.missing[i] ? "checked" : ""}> Simulate missing</label>
    <div class="mm">${p.mm.join("<br>")}</div></div>`).join("");
  const ws = S.weights.reduce((a, b) => a + b, 0);
  el.innerHTML = `<h1>Executive view</h1><div class="note" id="scen-note" style="margin:4px 0 8px"><b>Scenario: ${esc(PRESETS[S.preset].label)}.</b> ${esc(PRESETS[S.preset].note)} <span class="muted">(illustrative synthetic data)</span></div><p class="sub">Monthly. Supports the renewal decision: expand, right-size, renegotiate, continue a limited pilot, or renew with remediation. ${esc(scopeNote)}.</p>
  <div class="card" id="exec-score"><div class="row" style="justify-content:space-between;margin-bottom:10px"><h2 style="margin:0">AI value score beside its five pillars</h2>
   <div class="row"><label class="small"><input type="checkbox" id="breach" ${S.breach ? "checked" : ""}> Simulate critical-risk breach</label><button class="btn sm" id="wreset">Reset provisional weights</button></div></div>
   <div class="scorebox">${sv}<div class="pillars">${pil}</div></div>
   <div class="wsum ${ws !== 100 ? "fail" : "muted"}">Weights total ${ws}%${ws !== 100 ? ": the score is normalised by the total, but published weights must sum to 100 and be agreed with owners" : " (provisional: Reach 20, Depth 15, Outcome 40, Reliability 15, Trust 10)"}.</div></div>
  <div class="grid g5" style="margin-top:14px" id="exec-kpis">
   <div class="card kpi"><div class="lab">Habitual users (M02)</div><div class="val">${XX(pct(t.habitual, t.assigned))}%</div><div class="meta">${XX(fmt(t.habitual))} of ${XX(fmt(t.assigned))} assigned seats; active 3+ of 4 weeks</div></div>
   <div class="card kpi"><div class="lab">Verified hours per week (M17)</div><div class="val">${vh ? fmt(vh) : "xx"}</div><div class="meta">${vh ? "From approved holdout and staggered-rollout studies only" : "Not reported without a controlled comparison"}</div></div>
   <div class="card kpi"><div class="lab">Licence utilisation (M01)</div><div class="val">${XX(pct(t.active, t.assigned))}%</div><div class="meta">${XX(fmt(t.active))} active / ${XX(fmt(t.assigned))} assigned; login-only excluded</div></div>
   <div class="card kpi"><div class="lab">Cost per verified hour (M18)</div><div class="val">${cph ? cph.toFixed(1) + "× threshold" : "Not calculated"}</div><div class="meta">${cph ? "Index vs the agreed threshold. Platform cost is a placeholder, not set in this prototype. Kept outside the score" : "Not calculated when verified hours are missing, zero or negative"}</div></div>
   <div class="card kpi p" id="mau"><div class="lab">Vendor MAU (activity only)</div><div class="val" style="color:var(--gr)">${XX(fmt(VENDOR_MAU))}</div><div class="meta">Any login counts. Shown for contrast; not used for decisions</div></div>
  </div>
  <div class="card" style="margin-top:14px" id="renewal"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Renewal recommendation</h2><span class="tag or">Demo thresholds: agree in advance with Finance, Procurement, Risk and business owners</span></div>
   <div class="grid g2" style="margin-top:10px;grid-template-columns:1fr 1.6fr">
    <div>${[["Evidence 1: Licence utilisation","e1",`${XX(rn.util.toFixed(1))}% vs threshold <input type="number" id="uthr" value="${S.utilThr}" style="width:52px"> %`],
      ["Evidence 2: Verified business impact","e2", vh ? vh + " verified hours per week" : "No approved study result"],
      ["Evidence 3: Unit economics","e3", cph ? cph.toFixed(1) + "× the agreed threshold (placeholder cost)" : "Not calculated"],
      ["Evidence 4: Reliability and governance","e4", S.breach ? "Critical-risk breach open (privacy)" : S.relGap ? "Connector outage: reliability below agreed limits" : (W16() ? (S.missing[3] ? "Reliability pillar missing" : "Error and connector rates within limits; audit in place") : "Baselines pending")]]
      .map(([n, k, d]) => `<div class="ev"><span><b>${n}</b><br><span class="small muted">${d}</span></span><span>${evTag(rn.ev[k])}</span></div>`).join("")}</div>
    <div><div class="outcomes">${D.Renewal_Criteria.filter(r => r.Type === "Outcome").map(r => `<div class="oc ${r.Item === rn.out ? "on" : ""}"><b>${esc(r.Item)}</b>${esc(r.Description)}</div>`).join("")}</div>
    <p class="note">Rule order in this demo: no verified impact gives a limited pilot; a reliability or governance gap gives remediation conditions; low utilisation gives right-size; high unit cost gives renegotiate; otherwise expand. Try the toggles and thresholds.</p></div>
   </div></div>`;
  $$("[data-w]", el).forEach(r => r.oninput = () => { S.weights[+r.dataset.w] = +r.value; renderExec(); $(`[data-w="${r.dataset.w}"]`).focus(); });
  $$("[data-m]", el).forEach(c => c.onchange = () => { S.missing[+c.dataset.m] = c.checked; audit("Score simulation", PILLARS[+c.dataset.m].k + " pillar " + (c.checked ? "missing" : "restored"), score().state === "withheld" ? "Score withheld" : "Score shown"); renderExec(); });
  $("#breach").onchange = e => { S.breach = e.target.checked; audit("Score simulation", "Critical-risk breach " + (S.breach ? "on" : "off"), S.breach ? "Score flagged red" : "Flag cleared"); renderExec(); };
  $("#wreset").onclick = () => { S.weights = PILLARS.map(p => p.w); renderExec(); };
  const u = $("#uthr"); if (u) u.onchange = () => { S.utilThr = +u.value; renderExec(); };
}

function heat(f) {
  if (!W16()) return `<td class="h" style="background:#f6f6f4">xx%</td>`;
  const a = Math.max(0.08, Math.min(1, f));
  return `<td class="h" style="background:rgba(242,140,40,${(a * 0.85).toFixed(2)});color:${a > 0.8 ? "#fff" : "var(--ink)"}">${(100 * f).toFixed(0)}%</td>`;
}
function renderRegional() {
  const el = $("#s-regional");
  if (!ROLES[S.role].views.includes("regional")) { el.innerHTML = `<h1>Regional adoption and intervention</h1><p class="sub">Weekly; for regional and business leads.</p>` + locked("Regional adoption"); return; }
  const r = ROLES[S.role];
  const allRegions = ["Region A","Region B","Region C"], cohorts = ["Established","Launch cohort 1","Launch cohort 2","Launch cohort 3"];
  const ts = scopeTeams().filter(t => (S.region === "All" || t.region === S.region) && (S.cohort === "All" || t.cohort === S.cohort));
  const shown = ts.filter(t => t.assigned >= MIN_GROUP), small = ts.filter(t => t.assigned < MIN_GROUP);
  const tot = totals(ts);
  const rows = (keyF, keys) => keys.map(k => {
    const g = ts.filter(t => keyF(t) === k); if (!g.length) return "";
    const s = totals(g); if (s.assigned < MIN_GROUP) return `<tr class="lock"><td>${k}</td><td colspan="5">Hidden: below the minimum reporting size</td></tr>`;
    return `<tr><td>${k}</td><td class="num">${XX(fmt(s.purchased))}</td>${["assigned","active","engaged","habitual"].map(x => heat(x === "assigned" ? s.assigned / s.purchased : s[x] / s.assigned)).join("")}</tr>`;
  }).join("");
  const lockedRegions = allRegions.filter(x => !r.regions.includes(x)).map(x => `<tr class="lock"><td>${x}</td><td colspan="5">Hidden by row-level security for ${esc(r.label)}</td></tr>`).join("");
  const maxv = tot.purchased || 1;
  const funnel = STAGES.map(([k, l]) => `<div class="fr"><span>${l}</span><div class="fb"><i style="width:${W16() ? 100 * tot[k] / maxv : 0}%"></i></div><span class="num">${XX(fmt(tot[k]))}${k !== "purchased" ? ' <span class="muted small">' + XX(pct(tot[k], tot.purchased, 0)) + "%</span>" : ""}</span></div>`).join("");
  const mono = STAGES.every((s, i) => i === 0 || tot[STAGES[i - 1][0]] >= tot[s[0]]);
  const interv = shown.map(t => {
    const unused = t.assigned - t.active, unassigned = t.purchased - t.assigned;
    let a = null;
    if (unused / t.assigned > 0.4) a = ["Reassign or train", `${unused} paid and assigned seats with no qualifying use`];
    else if (unassigned / t.purchased > 0.15) a = ["Right-size", `${unassigned} purchased seats never assigned`];
    else if (t.habitual / t.active < 0.5) a = ["Train for habit", `Only ${pct(t.habitual, t.active, 0)}% of active users are habitual`];
    return a ? `<tr><td>${t.id}</td><td>${t.region}</td><td>${t.cohort}</td><td>${t.fn}</td><td><span class="tag or">${a[0]}</span></td><td class="small">${a[1]}</td></tr>` : "";
  }).join("");
  el.innerHTML = `<h1>Regional adoption and intervention</h1><p class="sub">Weekly. Where to train, reassign seats or slow rollout. New countries are tracked as launch cohorts. Row-level security: each lead sees their own region; groups below ${MIN_GROUP} assigned seats are hidden (demo value).</p>
  <div class="filters"><span class="tag ${S.role === "exec" ? "" : "or"}">Viewing as: ${esc(r.label)}</span>
   Region <select id="fr"><option>All</option>${allRegions.filter(x => r.regions.includes(x)).map(x => `<option ${S.region === x ? "selected" : ""}>${x}</option>`).join("")}</select>
   Launch cohort <select id="fc"><option>All</option>${cohorts.map(x => `<option ${S.cohort === x ? "selected" : ""}>${x}</option>`).join("")}</select>
   <span class="muted">Funnel check: ${mono ? '<span class="pass">monotonic, each stage no larger than the one above</span>' : '<span class="fail">not monotonic</span>'}</span></div>
  <div class="grid g2" style="grid-template-columns:1fr 1.25fr">
   <div class="card" id="funnel"><h2>Licence funnel (LF1 to LF6)</h2><div class="small muted" style="margin-top:-6px">Count, then % of purchased seats</div><div class="funnel">${funnel}</div>
    <p class="note">Active: 1+ qualifying interaction in 28 days (login-only excluded). Engaged: active on 2+ distinct days in 28. Habitual: active in 3+ of 4 weeks.</p>
    <div class="ev"><span>Paid but unused seats (three-way check, LF-CHK)</span><b>${XX(fmt(tot.assigned - tot.active))}</b></div>
    <div class="ev"><span>Purchased, never assigned</span><b>${XX(fmt(tot.purchased - tot.assigned))}</b></div></div>
   <div class="card"><h2>Funnel heatmap by region and launch cohort</h2>
    <table class="heat"><thead><tr><th>Group</th><th class="num">Purchased</th><th>Seats assigned</th><th>Active</th><th>Engaged</th><th>Habitual</th></tr></thead>
    <tbody><tr><td colspan="6" class="small muted"><b>By region</b></td></tr>${rows(t => t.region, allRegions)}${S.region === "All" ? lockedRegions : ""}
    <tr><td colspan="6" class="small muted"><b>By launch cohort</b></td></tr>${rows(t => t.cohort, cohorts)}
    <tr><td colspan="6" class="small muted"><b>By team</b></td></tr>${shown.map(t => `<tr><td>${t.id} <span class="small muted">${t.fn}</span></td><td class="num">${XX(t.purchased)}</td>${heat(t.assigned / t.purchased)}${heat(t.active / t.assigned)}${heat(t.engaged / t.assigned)}${heat(t.habitual / t.assigned)}</tr>`).join("")}
    ${small.map(t => `<tr class="lock"><td>${t.id}</td><td colspan="5">Hidden: below the minimum reporting size</td></tr>`).join("")}</tbody></table>
    <p class="note">Seats assigned as % of purchased; other stages as % of assigned seats. Hidden groups still count inside the totals of larger groups.</p></div>
  </div>
  <div class="grid g2" style="margin-top:14px;grid-template-columns:1fr 2fr">
   <div class="card"><h2>Agent mix by build type</h2><div class="ev"><span>Engineer-built</span><b>${XX("68%")}</b></div><div class="ev"><span>Drag-and-drop</span><b>${XX("32%")}</b></div><p class="note">Share of logical interactions in scope. Drag-and-drop counts are approximate until interaction IDs are validated (Gate 1, week 6).</p></div>
   <div class="card" id="interv"><h2>Intervention list</h2><table><thead><tr><th>Team</th><th>Region</th><th>Cohort</th><th>Function</th><th>Action</th><th>Why</th></tr></thead><tbody>${W16() ? (interv || '<tr><td colspan="6" class="muted">No interventions in scope</td></tr>') : '<tr><td colspan="6" class="muted">xx: available once instrumentation lands</td></tr>'}</tbody></table></div>
  </div>`;
  $("#fr").onchange = e => { S.region = e.target.value; renderRegional(); };
  $("#fc").onchange = e => { S.cohort = e.target.value; renderRegional(); };
}

function renderEng() {
  const el = $("#s-eng");
  if (!ROLES[S.role].views.includes("eng")) { el.innerHTML = `<h1>Engineering reliability and instrumentation</h1><p class="sub">Daily, with alerts; for platform engineering.</p>` + locked("Engineering reliability"); return; }
  const ag = AGENTS.filter(a => S.buildF === "All" || a.build === S.buildF);
  const runs = sum(ag, "runs"), fails = sum(ag, "fail");
  const cc = CONNECTORS.map(c => ({...c, rate: 100 * c.fail / c.calls})).sort((a, b) => b.rate - a.rate);
  const unreg = ag.filter(a => !a.reg);
  const fresh = S.lateLoad ? 26 : 3;
  const noidKeys = S.buildF === "All" ? Object.keys(EVT_NOID) : [S.buildF];
  const ne = noidKeys.reduce((a, k) => a + EVT_NOID[k].events, 0), nn = noidKeys.reduce((a, k) => a + EVT_NOID[k].noid, 0);
  const k = (lab, id, val, meta, st) => `<div class="card kpi"><div class="row" style="justify-content:space-between"><span class="lab">${lab} (${id})</span>${st ? `<span class="tag ${st[0]}">${st[1]}</span>` : ""}</div><div class="val">${val}</div><div class="meta">${meta}</div></div>`;
  el.innerHTML = `<h1>Engineering reliability and instrumentation</h1><p class="sub">Daily, with alerts. What to fix first; which agents to retire or register. Alert limits are demo values, to agree with metric owners.</p>
  <div class="filters">Build type <select id="fb">${["All","Engineer-built","Drag-and-drop"].map(x => `<option ${S.buildF === x ? "selected" : ""}>${x}</option>`).join("")}</select>
   <label><input type="checkbox" id="late" ${S.lateLoad ? "checked" : ""}> Simulate a late warehouse load</label></div>
  <div class="grid g4" id="eng-kpis">
   ${k("Agent error rate","M10",XX(pct(fails, runs, 1)) + "%",`${XX(fmt(fails))} failed / ${XX(fmt(runs))} runs`, W16() ? (fails / runs > 0.03 ? ["amb","Above 3%"] : ["grn","Within 3%"]) : null)}
   ${k("p95 latency","M15",XX(S.buildF === "Drag-and-drop" ? "7.1" : S.buildF === "Engineer-built" ? "4.6" : "5.1") + " s","Slowest 5% of responses; outside the score",null)}
   ${k("Connector failure rate","M11",XX(pct(sum(CONNECTORS, "fail"), sum(CONNECTORS, "calls"))) + "%",`Highest: ${XX(cc[0].id)} at ${XX(cc[0].rate.toFixed(1))}%`, W16() ? ["amb", cc[0].id + " above 5%"] : null)}
   ${k("Unregistered agents","M16",XX(unreg.length),"Agents with no registry entry (risk R4)", W16() && unreg.length ? ["red","Register or retire"] : null)}
   ${k("Data freshness","M12",XX(fresh) + " h","Time since last good load; window 24 h (demo)", W16() ? (S.lateLoad ? ["red","Late load"] : ["grn","Fresh"]) : null)}
   ${k("Events without interaction ID","M20",XX(pct(nn, ne)) + "%",`${XX(fmt(nn))} of ${XX(fmt(ne))} events; drag-and-drop ${XX(pct(EVT_NOID["Drag-and-drop"].noid, EVT_NOID["Drag-and-drop"].events))}%`, W16() ? (nn / ne > 0.05 ? ["red","Risk R1"] : ["grn","OK"]) : null)}
   ${k("Data-quality tests passing","M21",XX(pct(DQ.pass, DQ.all, 0)) + "%",`${XX(DQ.pass)} of ${XX(DQ.all)} tests in the metrics layer`, W16() ? ["amb", (DQ.all - DQ.pass) + " failing"] : null)}
   <div class="card"><h2>Alerts</h2>${W16() ? `${S.lateLoad ? '<div class="alert">Warehouse load is late (26 h). Agent answers carry a freshness warning.</div>' : '<div class="alert ok">All loads within window.</div>'}<div class="alert amb">Email connector failures rose to ${cc[0].rate.toFixed(1)}% (was ${cc[0].prev.toFixed(1)}% last week).</div><div class="alert">${AGENTS.filter(a => !a.reg).length} agents published without registry entries.</div>` : '<p class="muted">xx</p>'}</div>
  </div>
  <div class="grid" style="margin-top:14px;grid-template-columns:1fr">
   <div class="card"><h2>Agents</h2><table><thead><tr><th>Agent ID</th><th>Name</th><th>Build type</th><th>Registry</th><th class="num">Runs</th><th class="num">Error rate</th><th class="num">p95</th></tr></thead><tbody>
    ${ag.map(a => `<tr><td>${a.id}</td><td>${a.name}</td><td>${a.build}</td><td>${a.reg ? '<span class="tag grn">Registered</span>' : '<span class="tag red">Unregistered</span>'}</td><td class="num">${XX(fmt(a.runs))}</td><td class="num">${XX(pct(a.fail, a.runs))}%</td><td class="num">${XX(a.p95)} s</td></tr>`).join("")}</tbody></table></div>
   </div><div class="grid g2" style="margin-top:14px"><div class="card"><h2>Connectors</h2><table><thead><tr><th>Connector</th><th class="num">Calls</th><th class="num">Failure rate</th><th class="num">Last week</th></tr></thead><tbody>
    ${cc.map(c => `<tr><td>${c.id}</td><td class="num">${XX(fmt(c.calls))}</td><td class="num"><b>${XX(c.rate.toFixed(1))}%</b></td><td class="num">${XX(c.prev.toFixed(1))}%</td></tr>`).join("")}</tbody></table>
    </div><div class="card"><h2>How engineering metrics stay separate</h2><div class="ctl"><span class="ck">&#10003;</span><span>Errors are kept apart from usage: a failed run is never counted as adoption.</span></div><div class="ctl"><span class="ck">&#10003;</span><span>Every agent needs a registry entry with an owner and build type before it is published (risk R4).</span></div><div class="ctl"><span class="ck">&#10003;</span><span>Drag-and-drop events without an interaction ID fall back to sessionisation and are labelled approximate (risk R1, Gate 1).</span></div><div class="ctl"><span class="ck">&#10003;</span><span>A late load puts a freshness warning on every agent answer that uses the data.</span></div></div>
  </div>`;
  $("#fb").onchange = e => { S.buildF = e.target.value; renderEng(); };
  $("#late").onchange = e => { S.lateLoad = e.target.checked; renderEng(); };
}
/* How we count: grouping rules run live on Golden_Events */
function tsec(s) { const m = /T\+(\d+)s/.exec(s); return m ? +m[1] : null; }
function groupEvents(gap) {
  const ev = D.Golden_Events, groups = [], assign = {};
  const byId = {};
  ev.filter(e => e["Grouping method"] === "Interaction ID").forEach(e => (byId[e["Interaction ID"]] = byId[e["Interaction ID"]] || []).push(e));
  Object.entries(byId).forEach(([id, es]) => { groups.push({key:id, method:"exact", events:es}); es.forEach(e => assign[e["Event ID"]] = id); });
  let cur = null, n = 0;
  ev.filter(e => e["Grouping method"].startsWith("Sessionisation")).forEach(e => {
    const t = tsec(e["Relative time"]);
    if (cur && cur.user === e["User ID"] && cur.agent === e["Agent ID"] && t - cur.last <= gap) { cur.events.push(e); cur.last = t; }
    else { n++; cur = {key:"SESS-" + n, method:"approximate", user:e["User ID"], agent:e["Agent ID"], last:t, events:[e]}; groups.push(cur); }
    assign[e["Event ID"]] = cur.key;
  });
  groups.forEach(g => { const ty = g.events.map(e => e["Event type"]); g.qual = ty.includes("agent_run") && ty.includes("response"); });
  ev.filter(e => e["Event type"] === "login").forEach(e => assign[e["Event ID"]] = "LOGIN");
  return {groups, assign};
}
function countResults(gap) {
  const ev = D.Golden_Events, {groups, assign} = groupEvents(gap);
  const q = groups.filter(g => g.qual);
  const users = new Set(q.flatMap(g => g.events.map(e => e["User ID"])));
  return {raw: ev.length, inter: q.length, exact: q.filter(g => g.method === "exact").length, approx: q.filter(g => g.method === "approximate").length, users, groups, assign, ratio: q.length ? ev.length / q.length : null};
}
function expectedChecks(gap) {
  const r = countResults(gap), g1 = r.groups.find(g => g.key === "INT-0001");
  return [
    ["ER1", "5 raw events = 1 logical interaction (INT-0001) and 1 run; exact", !!g1 && g1.events.length === 5 && g1.qual && new Set(g1.events.map(e => e["Run ID"])).size === 1],
    ["ER2", "3 raw events = 1 logical interaction (INT-0002); approximate", r.groups.filter(g => g.method === "approximate").length === 1 && r.approx === 1],
    ["ER3", "Login only: 0 interactions; USER-003 not Active", !r.users.has("USER-003")],
    ["ER4", "9 raw events = 2 logical interactions; 4.5x overstatement", r.raw === 9 && r.inter === 2 && r.ratio === 4.5],
    ["ER5", "USER-001 and USER-002 Active; USER-003 not Active", r.users.has("USER-001") && r.users.has("USER-002") && !r.users.has("USER-003")],
    ["ER6", "Engineer-built 1 (exact); drag-and-drop 1 (approximate)", r.exact === 1 && r.approx === 1]
  ];
}
function renderCount() {
  const el = $("#s-count"), r = countResults(S.gap), raw = S.countMode === "raw";
  const col = {"INT-0001":"#F28C28"}, sesCol = ["#5B7FA6","#A65B8F","#7AA65B","#A6935B"]; let sc = 0;
  r.groups.forEach(g => { if (!col[g.key]) col[g.key] = sesCol[sc++ % 4]; });
  const checks = expectedChecks(S.gap), allPass = checks.every(c => c[2]);
  el.innerHTML = `<h1>How we count: raw events vs logical interactions</h1><p class="sub">The grouping rules (Interaction_Rules IR1 to IR8) run live in the browser on the nine synthetic rows of the Golden_Events tab, then are checked against Expected_Results.</p>
  <div class="row" style="margin-bottom:12px"><div class="seg" id="cmode"><button data-c="raw" class="${raw ? "on" : ""}">Raw-event counting (vendor style)</button><button data-c="logical" class="${!raw ? "on" : ""}">Logical-interaction counting</button></div>
   <span class="small muted" style="margin-left:10px">Sessionisation gap (IR6, to be agreed and tested) <input type="range" id="gap" min="1" max="30" value="${S.gap}" style="vertical-align:middle;accent-color:var(--or)" aria-label="Sessionisation gap"> <b>${S.gap} s</b></span></div>
  <div class="grid g4" id="count-kpis">
   <div class="card kpi"><div class="lab">${raw ? "Usage as counted by raw events" : "Logical interactions (IR3)"}</div><div class="bigcount" style="color:${raw ? "var(--gr)" : "var(--or)"}">${raw ? r.raw : r.inter}</div><div class="meta">${raw ? "Every logged row counted, including the login" : r.exact + " exact (interaction ID), " + r.approx + " approximate (sessionisation)"}</div></div>
   <div class="card kpi"><div class="lab">Overstatement on this sample</div><div class="bigcount">${r.ratio ? r.ratio.toFixed(1) + "x" : "n/a"}</div><div class="meta">${r.raw} raw events / ${r.inter} logical interactions</div></div>
   <div class="card kpi"><div class="lab">Active users (LF4)</div><div class="bigcount">${raw ? 3 : r.users.size}</div><div class="meta">${raw ? "USER-001, 002 and 003: a login is counted as use" : [...r.users].join(", ") + "; USER-003 is login-only, not counted"}</div></div>
   <div class="card kpi"><div class="lab">Expected_Results checks</div><div class="bigcount ${allPass ? "pass" : "fail"}">${checks.filter(c => c[2]).length}/6</div><div class="meta">${allPass ? "All pass at this gap" : "Fails at this gap: the gap value must be tested"}</div></div>
  </div>
  <div class="grid" style="grid-template-columns:1fr 270px;margin-top:14px">
   <div class="card" id="evt-table"><h2>Golden_Events (synthetic)</h2><div style="overflow-x:auto"><table class="evt"><thead><tr><th>Event ID</th><th>Time</th><th>Team</th><th>User</th><th>Event type</th><th>Agent</th><th>Build type</th><th>${raw ? "Counted as" : "Grouped into"}</th></tr></thead><tbody>
   ${D.Golden_Events.map(e => { const g = r.assign[e["Event ID"]], grp = r.groups.find(x => x.key === g);
     const lab = raw ? "1 usage event" : g === "LOGIN" ? '<span class="tag">Not counted: login only</span>' : `<span class="gpill" style="background:${col[g]}"></span>${g === "INT-0001" ? "INT-0001, exact" : g + ", approximate"}${grp && !grp.qual ? ' <span class="tag red">not qualifying</span>' : ""}`;
     const bg = raw || g === "LOGIN" ? "" : `background:${col[g]}22`;
     return `<tr style="${bg}"><td>${e["Event ID"]}</td><td>${e["Relative time"]}</td><td>${e["Team ID"]}</td><td>${e["User ID"]}</td><td>${e["Event type"]}</td><td>${e["Agent ID"]}</td><td>${e["Agent build type"]}</td><td>${lab}</td></tr>`; }).join("")}</tbody></table></div>
   <p class="note">IR5: events group by interaction ID only once the ID is validated for both agent types (Gate 1, week 6). IR6: otherwise same user + same agent + time gap, and the metric is labelled approximate. IR7: an interaction qualifies only with an agent_run and a response.</p></div>
   <div class="card tests" id="er-checks"><h2>Expected_Results</h2>${checks.map(c => `<div><span class="${c[2] ? "pass" : "fail"}">${c[2] ? "Pass" : "Fail"}</span> <b>${c[0]}</b> ${esc(c[1])}</div>`).join("")}
    <p class="note">Drag the gap below 2 s: the onboarding interaction splits into fragments that no longer qualify, so ER2, ER4 and ER6 fail and the build is blocked. That is why the gap is tested before any metric uses it.</p></div>
  </div>`;
  $$("#cmode button").forEach(b => b.onclick = () => { S.countMode = b.dataset.c; renderCount(); });
  $("#gap").oninput = e => { S.gap = +e.target.value; renderCount(); $("#gap").focus(); };
}

/* Adoption Insights Agent */
const VIEW_OF = id => { const m = metric(id); if (!m) return null; const v = m["Dashboard view"];
  return v.startsWith("Engineering") ? "eng" : v.startsWith("Executive") ? "exec" : v.startsWith("Regional") ? "regional" : "exec"; };
function cite(id, label) { const m = metric(id);
  return m ? {id, name:m.Metric, ver:"v1 (proposed)", owner:m.Owner, def:m.Formula, miss:m["Missing-data rule"], tests:m.Tests} : {id:label || id, name:"", ver:"v1 (proposed)", owner:"To be named", def:""}; }
function sqlFor(ids, scope, extra) {
  const sc = scope && scope.length ? `\n  AND region IN (${scope.map(x => "'" + x + "'").join(", ")})  -- row-level security from the SSO role` : "";
  return ids.map(id => `-- Governed metrics API (read-only); no raw events or PII\nSELECT metric_id, value, numerator, denominator,\n       definition_version, data_as_of\nFROM metrics.${id.toLowerCase()}_governed\nWHERE period = :current_period${extra || ""}${sc}\n  AND group_size >= ${MIN_GROUP};  -- small groups suppressed`).join("\n\n");
}
function ans(kind, text, ids, o = {}) { return {kind, text, cites:(ids || []).map(i => cite(i)).concat(o.label ? [cite(null, o.label)] : []), sql:o.sql, steps:o.steps, reason:o.reason, alt:o.alt}; }
function answerFor(qid) {
  const role = ROLES[S.role], q = D.Agent_Test_Questions.find(x => x["Question ID"] === qid);
  const t = totals(scopeTeams()), scope = role.regions, scopeTxt = S.role === "exec" ? "all regions" : role.regions.join(", ") || "no regions";
  const metricIds = q["Governed metric reference"].match(/M\d\d/g) || [];
  const outOfRole = metricIds.slice(0, 1).find(id => !role.views.includes(VIEW_OF(id)) && !(role.views.includes("regional") && ["M01","M02","M03","M04"].includes(id)));
  const viewNames = {exec:"executive", regional:"regional adoption", eng:"engineering reliability"};
  const refuseRole = () => ans("refuse", `This is outside your role scope. As ${role.label} you can ask about ${role.views.map(v => viewNames[v]).join(" and ")} metrics only.`, metricIds.slice(0, 1),
    {reason:"Outside the user's role-based access", alt: role.views.includes("eng") ? "I can show the reliability metrics instead: agent error rate (M10) and connector failure rate (M11)." : "I can show your adoption metrics: licence utilisation (M01) and habitual users (M02) in your scope."});
  const late = S.lateLoad ? ` Warning: the latest load is late, so this is the last good value (data as of ${W16() ? "16-10-2026, synthetic" : "17-10-2026 (illustrative; values pending)"}).` : "";
  switch (qid) {
    case "Q01": if (outOfRole) return refuseRole(); return ans("answer", `Licence utilisation is ${XX(pct(t.active, t.assigned))}% this month (${XX(fmt(t.active))} active users / ${XX(fmt(t.assigned))} assigned seats) for ${scopeTxt}. Active means 1+ qualifying interaction in 28 days; login-only users are excluded.`, ["M01"], {sql:sqlFor(["M01"], scope)});
    case "Q02": return ans("answer", `Licence utilisation (M01) = active users (LF4: 1+ qualifying interaction in 28 days) / assigned seats (LF2: seats given to named people). Owner: to be named. Version v1 (proposed). Missing-data rule: ${metric("M01")["Missing-data rule"].toLowerCase()}.`, ["M01"], {sql:"-- Definition lookup in the metric catalogue\nGET /catalogue/metrics/M01?version=current\n\nM01 = COUNT(DISTINCT pseudonymised_user\n            WHERE qualifying_interactions_28d >= 1)\n    / COUNT(assigned_seats)"});
    case "Q03": { if (outOfRole) return refuseRole();
      const regs = scope.map(rg => { const s = totals(TEAMS.filter(x => x.region === rg && (!role.fn || x.fn === role.fn))); return s.assigned >= MIN_GROUP ? `${rg}: ${XX(pct(s.habitual, s.assigned))}% habitual (${XX(s.habitual)} of ${XX(s.assigned)} seats)` : `${rg}: hidden, below minimum size`; });
      const hid = scopeTeams().filter(x => x.assigned < MIN_GROUP).length;
      return ans("answer", `Habitual users by market in your scope:<br>${regs.join("<br>")}${hid ? `<br>${hid} team${hid > 1 ? "s" : ""} below the minimum reporting size ${hid > 1 ? "are" : "is"} hidden.` : ""}`, ["M02"], {sql:sqlFor(["M02"], scope)}); }
    case "Q04": { if (outOfRole) return refuseRole(); const c = scopeTeams().filter(x => x.cohort === "Launch cohort 3"), s = totals(c);
      if (!c.length || s.assigned < MIN_GROUP) return ans("refuse", "The newest country (launch cohort 3) is below the minimum reporting size within your scope.", [], {label:"LF1-LF6 funnel", reason:"Group below minimum size is suppressed", alt:"I can show the funnel for your whole region instead."});
      return ans("answer", `Launch cohort 3, from the cohort's first day: purchased ${XX(s.purchased)}, assigned ${XX(s.assigned)}, provisioned ${XX(s.provisioned)}, active ${XX(s.active)}, engaged ${XX(s.engaged)}, habitual ${XX(s.habitual)}. Utilisation is ${XX(pct(s.active, s.assigned, 0))}%, against ${XX(pct(t.active, t.assigned, 0))}% for your scope overall.`, ["M01","M03"], {sql:sqlFor(["M03"], scope, "\n  AND launch_cohort = 'Launch cohort 3'")}); }
    case "Q05": if (outOfRole) return refuseRole(); { const w = CONNECTORS.map(c => ({...c, r: 100 * c.fail / c.calls})).sort((a, b) => b.r - a.r)[0]; return ans("answer", `The ${w.id.toLowerCase()} connector has the highest failure rate this week: ${XX(w.r.toFixed(1))}% (${XX(fmt(w.fail))} failed / ${XX(fmt(w.calls))} calls).${late}`, ["M11","M12"], {sql:sqlFor(["M11"])}); }
    case "Q06": if (outOfRole) return refuseRole(); return ans("answer", `${XX(2)} agents have no registry entry: ${W16() ? "AG-DD-05 and AG-DD-06, both drag-and-drop" : "xx"}. Definition: agents without a registry entry, reconciled to the source register.`, ["M16"], {sql:sqlFor(["M16"])});
    case "Q07": { if (outOfRole) return refuseRole(); const c = scopeTeams().filter(x => x.cohort === "Launch cohort 2"), s = totals(c);
      if (!c.length) return ans("refuse", "Launch cohort 2 has no teams in your scope.", ["M01"], {reason:"Outside the user's role-based access", alt:"I can show utilisation for your own markets."});
      const shownT = c.filter(x => x.assigned >= MIN_GROUP), b = {assigned:0,active:0,engaged:0,habitual:0};
      c.forEach(x => { const o = Q07_BEFORE[x.id]; Object.keys(b).forEach(k => b[k] += o[k]); });
      const gap = x => (x.assigned - Q07_BEFORE[x.id].assigned) - (x.active - Q07_BEFORE[x.id].active);
      const tot = shownT.reduce((a, x) => a + Math.max(0, gap(x)), 0) || 1;
      const ranked = shownT.slice().sort((x, y) => gap(y) - gap(x)), top = ranked[0];
      const pp = (n, d) => d > 0 ? Math.round(100 * n / d) : 0, d = (a, b2) => { const v = a - b2; return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v) + " pts"; };
      const rowsF = [["Assigned seats (LF2)", XX(b.assigned), XX(s.assigned), XX((s.assigned - b.assigned >= 0 ? "+" : "") + (s.assigned - b.assigned) + " seats")],
        ["Active (LF4) / assigned", XX(pp(b.active,b.assigned)+"%"), XX(pp(s.active,s.assigned)+"%"), "<b>"+XX(d(pp(s.active,s.assigned), pp(b.active,b.assigned)))+"</b>"],
        ["Engaged (LF5) / active", XX(pp(b.engaged,b.active)+"%"), XX(pp(s.engaged,s.active)+"%"), XX(d(pp(s.engaged,s.active), pp(b.engaged,b.active)))],
        ["Habitual (LF6) / engaged", XX(pp(b.habitual,b.engaged)+"%"), XX(pp(s.habitual,s.engaged)+"%"), XX(d(pp(s.habitual,s.engaged), pp(b.habitual,b.engaged)))]];
      const tbl = (h, r) => `<table class="q7"><tr>${h.map(x => `<th>${x}</th>`).join("")}</tr>${r.map(x => `<tr>${x.map(y => `<td>${y}</td>`).join("")}</tr>`).join("")}</table>`;
      const teamRows = c.map(x => x.assigned < MIN_GROUP ? [`${x.id} · ${x.region}`, `<i class="muted">hidden (&lt; ${MIN_GROUP} seats)</i>`, "Shown at region level only"] :
        [`${x.id} · ${x.region}`, "<b>" + XX(pp(Math.max(0, gap(x)), tot) + "%") + "</b>", `${XX(x.assigned - Q07_BEFORE[x.id].assigned)} seats assigned this month, ${XX(x.active - Q07_BEFORE[x.id].active)} of them now active${x.fn === "Merchant onboarding" ? "; onboarding agent email connector failures " + XX("6.3%") + " (M11)" : ""}`]);
      const txt = `Licence utilisation (M01) in launch cohort 2 fell from <b>${XX(pp(b.active,b.assigned)+"%")}</b> last month to <b>${XX(pp(s.active,s.assigned)+"%")}</b> this month. Here is where the drop sits, using governed metrics only:
        ${tbl(["Funnel step","Last month","This month","Change"], rowsF)}${tbl(["Team (cohort 2)","Share of the drop","What changed"], teamRows)}
        <div style="margin-top:8px"><b>Biggest contributor (descriptive):</b> ${top ? `new seats assigned in ${top.id} (${top.region}) that are not yet active. Existing users kept using the agent; engagement and habit moved far less than activation.` : "not shown: all teams are below the minimum reporting size."}</div>
        <div style="margin-top:6px"><b>Caveat:</b> these moved together in time. That is correlation, not proven cause.</div>
        <div style="margin-top:6px"><b>Next steps:</b> the intervention list (activation nudge and training for ${top ? top.id : "the team"}, email connector fix by the platform owner), or the approved study design (staggered rollout, readout when the study reports.</div>
        <button class="btn sm" data-drill="Launch cohort 2" style="margin-top:8px">Open cohort 2 funnel in Regional view →</button>`;
      return ans("caveat", txt, ["M01","M03","M11"], {steps:["Treat a \"why\" question as a breakdown, not speculation: funnel stage first, then team.","Compare last month with this month on the governed licence funnel (LF2, LF4 to LF6), within your role scope.","Rank teams by new seats not yet active; suppress any team below " + MIN_GROUP + " assigned seats.","No causal claim without an approved study result (see Q17)."],
        sql:`-- Governed metrics API (read-only); no raw events or PII\nWITH f AS (\n  SELECT team_id, period, assigned_seats, active_users, engaged_users, habitual_users\n  FROM metrics.licence_funnel_governed\n  WHERE launch_cohort = 'Launch cohort 2'\n    AND period IN (:last_month, :this_month)${scope.length ? "\n    AND region IN (" + scope.map(x => "'" + x + "'").join(", ") + ")  -- row-level security" : ""}\n    AND group_size >= ${MIN_GROUP}  -- small groups suppressed\n)\nSELECT team_id,\n  SUM(CASE WHEN period = :this_month THEN assigned_seats ELSE -assigned_seats END) AS new_seats,\n  SUM(CASE WHEN period = :this_month THEN active_users ELSE -active_users END) AS new_active\nFROM f GROUP BY team_id\nORDER BY new_seats - new_active DESC;`}); }
    case "Q08": case "Q19": { if (outOfRole) return refuseRole(); const sc = score();
      if (sc.state === "withheld") return ans("refuse", qid === "Q19" ? "Correction: no AI value score has been published, so it is neither low nor high." : "No AI value score is published yet.", ["M19"], {reason:sc.reason, alt:"The five pillars with their status: " + PILLARS.map((p, i) => `${p.k} ${!W16() ? "baseline pending" : S.missing[i] ? "missing" : p.v}`).join(", ") + "."});
      return ans(sc.state === "red" || qid === "Q19" ? "caveat" : "answer", `${qid === "Q19" ? "Correction: no target makes the score low or high yet; read the pillars instead. " : ""}The AI value score is ${sc.value} of 100${sc.state === "red" ? ", flagged red because a critical-risk breach is open" : ""}. Pillars: ${PILLARS.map(p => `${p.k} ${p.v}`).join(", ")}. The lowest pillar is Depth.`, ["M19"], {sql:sqlFor(["M19"])}); }
    case "Q09": { if (outOfRole) return refuseRole(); const h = verifiedHours();
      if (!h) return ans("refuse", "No verified figure exists until a controlled comparison reports.", ["M17"], {reason:"No approved study result yet", alt:"Study status: designs in approval; readout when the study reports."});
      return ans("answer", `Verified hours saved: ${h} per week across the approved studies (fraud holdout and onboarding staggered rollout), ${fmt(h * 6)} over the six-week study window. Each case is counted once, in one workflow.`, ["M17"], {sql:sqlFor(["M17"])}); }
    case "Q10": { if (outOfRole) return refuseRole(); const c = costPerHour();
      if (!c) return ans("refuse", "Cost per verified hour is not calculated.", ["M18"], {reason:"Verified hours saved is missing, zero or negative", alt:"Platform cost is a placeholder in this prototype; the metric is calculated once a study reports verified hours."});
      return ans("answer", `Cost per verified hour is ${c.toFixed(1)}× the agreed threshold (platform cost / ${verifiedHours()} verified hours per week; the cost figure is a placeholder). It sits beside the score, never inside it.`, ["M18","M17"], {sql:sqlFor(["M18"])}); }
    case "Q11": if (outOfRole) return refuseRole(); return ans(S.lateLoad ? "caveat" : "answer", `Agent error rate yesterday was ${XX("2.0")}%.${late || " Data is within the freshness window."}`, ["M10","M12"], {sql:sqlFor(["M10","M12"])});
    case "Q12": return ans("refuse", "Reports are by team and agent, not named people.", ["M01"], {reason:"Named individuals are not reported", alt:`Fraud-review assistant use by team: ${W16() ? (TEAMS.filter(x => x.fn === "Fraud operations" && scope.includes(x.region)).map(x => `${x.id} ${pct(x.active, x.assigned, 0)}% utilisation`).join(", ") || "none in your scope") : "xx"}.`});
    case "Q13": return ans("refuse", "I read governed metrics only. Raw events and user-level records are never exposed.", [], {label:"Not applicable", reason:"No raw events or personal data are exposed", alt:"I can show aggregate metrics for your team."});
    case "Q14": return ans("refuse", "Card data is masked at ingestion and never reaches me.", [], {label:"Not applicable", reason:"Card and personal data out of scope", alt:"I can show fraud handle-time metrics by team (M08), once a study reports."});
    case "Q15": return ans("refuse", `That group is below the minimum reporting size (${MIN_GROUP} assigned seats in this demo), so its count is suppressed.`, [], {label:"LF4 Active", reason:"Group below minimum size is suppressed", alt:scope[0] ? `At the next level up, ${scope.length > 1 ? "all your regions have" : scope[0] + " has"} ${XX(fmt(t.active))} active users.` : "Your role has no regional scope."});
    case "Q16": if (S.role === "exec") return ans("answer", `As Executive sponsor you can see all regions. Licence utilisation: ${["Region A","Region B","Region C"].map(rg => { const s = totals(TEAMS.filter(x => x.region === rg)); return `${rg} ${XX(pct(s.active, s.assigned))}%`; }).join(", ")}.`, ["M01"], {sql:sqlFor(["M01"], ["Region A","Region B","Region C"])});
      if (outOfRole) return refuseRole();
      return ans("refuse", `Markets outside ${scopeTxt} are not in your role scope.`, ["M01"], {reason:"Outside the user's role-based access", alt:`Utilisation for your own markets: ${XX(pct(t.active, t.assigned))}%.`});
    case "Q17": return ans("refuse", "I cannot say the onboarding agent caused faster onboarding. Causal claims need an approved study result; observational data cannot prove cause.", ["M09"], {reason:"No study result yet; observational data cannot prove cause", alt:"Design B, a staggered rollout by market, is in approval; readout at the study readout."});
    case "Q18": if (outOfRole) return refuseRole(); return ans("caveat", `Correction: vendor MAU counts activity, not value. Any login counts, so MAU (${XX(VENDOR_MAU)}) sits far above active users (${XX(t.active)}) and habitual users (${XX(t.habitual)}). Utilisation is ${XX(pct(t.active, t.assigned))}% and habitual use ${XX(pct(t.habitual, t.assigned))}%. Value needs verified outcomes, not more logins.`, ["M01","M02","M19"], {sql:sqlFor(["M01","M02"], scope)});
    case "Q20": return ans("refuse", "Forecasts are outside the governed metric set.", ["M01"], {reason:"No forecasts outside governed metrics", alt:`Utilisation trend to date: ${W16() ? "54%, 58%, 63%, " + pct(totals(TEAMS).active, totals(TEAMS).assigned, 0) + "% (last four months, synthetic)" : "xx"}.`});
    case "Q21": return ans("refuse", "I am read-only. I take no actions on agents or workflows.", [], {label:"Not applicable", reason:"Agent is read-only", alt:`Onboarding agent health, for its owner to decide: error rate ${XX("3.9")}%, p95 ${XX("6.8")} s, email connector failures ${XX("6.3")}%.`});
  }
}
function matchQuestion(text) {
  const s = text.toLowerCase();
  if (/\b\d{12,19}\b|card number|\bpan\b|cvv/.test(s)) return "Q14";
  if (/user-\d+|raw event|email address|phone number/.test(s)) return "Q13";
  if (/which (analyst|people|person|employee)s?|who (uses|is)|named|by name|individual/.test(s)) return "Q12";
  if (/retire|delete|disable|turn off|send |email them/.test(s)) return "Q21";
  if (/next quarter|forecast|predict/.test(s)) return "Q20";
  if (/caused?\b/.test(s)) return "Q17";
  const words = s.replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(w => w.length > 3);
  let best = null, bs = 0;
  D.Agent_Test_Questions.forEach(q => { const qw = q.Question.toLowerCase(); const sc = words.filter(w => qw.includes(w)).length; if (sc > bs) { bs = sc; best = q["Question ID"]; } });
  return bs >= 2 ? best : null;
}
function ask(input) {
  const isId = /^Q\d\d$/.test(input), qid = isId ? input : matchQuestion(input);
  const qtext = isId ? D.Agent_Test_Questions.find(q => q["Question ID"] === input).Question : input;
  const a = qid ? answerFor(qid) : ans("refuse", "I can only answer questions about the governed adoption, reliability and value metrics.", [], {reason:"Out of scope for the governed metric set", alt:"Try a golden question on the right, such as \"What is licence utilisation this month?\""});
  const q = qid ? D.Agent_Test_Questions.find(x => x["Question ID"] === qid) : null;
  S.chat.push({you:qtext}); S.chat.push({a, qid, cat: q ? q.Category : "Out of scope"});
  audit("Agent question", (qid ? qid + ": " : "") + qtext, a.kind === "refuse" ? "Refused, safe alternative offered" : a.kind === "caveat" ? "Answered with caveat" : "Answered");
  if (S.screen === "agent") { renderAgent(); scrollNewest(); }
}
function scrollNewest() { const m = $("#msgs"); if (!m) return; const you = $$(".msg.you", m).pop(); m.scrollTop = you ? you.offsetTop - 6 : 0; }
function renderAgent() {
  const el = $("#s-agent");
  const byCat = {}; D.Agent_Test_Questions.forEach(q => (byCat[q.Category] = byCat[q.Category] || []).push(q));
  const msgs = S.chat.map((m, i) => {
    if (m.you) return `<div class="msg you"><div class="who">You</div>${esc(m.you)}</div>`;
    const a = m.a, asOf = !W16() ? "17-10-2026 (illustrative; values pending)" : S.lateLoad ? "16-10-2026 (synthetic; latest load late)" : S.asOf + " (synthetic)";
    const cites = a.cites.map(c => `<span class="cite"><b>${esc(c.id)}</b>${c.name ? " " + esc(c.name) + ", " + c.ver : ""}</span>`).join("") + (a.cites.length ? `<span class="cite">Owner: ${esc(a.cites[0].owner)}</span><span class="cite">As of ${asOf}</span>` : "");
    const defs = a.cites.filter(c => c.def).map(c => `${c.id} ${c.name} (${c.ver})\n  Definition: ${c.def}\n  Owner: ${c.owner}\n  Missing-data rule: ${c.miss}\n  Tests: ${c.tests}`).join("\n\n");
    return `<div class="msg ${a.kind === "refuse" ? "ref" : "ag"}" data-i="${i}"><div class="who">Agent${a.kind === "refuse" ? ": cannot answer" : a.kind === "caveat" ? ": answer with caveat" : ""} <span class="tag" style="font-weight:normal">${m.qid || "Free text"} · ${esc(m.cat)}</span></div>${a.text}
      ${a.reason ? `<div class="note"><b>Reason:</b> ${esc(a.reason)}</div>` : ""}${a.alt ? `<div style="margin-top:6px"><b>Safe alternative:</b> ${esc(a.alt)}</div>` : ""}
      ${cites ? `<div class="cites">${cites}</div>` : ""}
      ${(a.sql || defs) ? `<details><summary>Show reasoning, SQL and definition</summary>${a.steps ? `<ol class="small">${a.steps.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : `<ol class="small"><li>Matched to golden question ${m.qid || "(free text)"}; category ${esc(m.cat)}.</li><li>Role scope applied: ${esc(ROLES[S.role].label)}.</li><li>${a.kind === "refuse" ? "Policy check failed: refuse and offer the safe alternative." : "Policy checks passed: governed metrics only, aggregate, small groups suppressed."}</li></ol>`}${defs ? `<pre>${esc(defs)}</pre>` : ""}${a.sql ? `<pre>${esc(a.sql)}</pre>` : ""}</details>` : ""}
      <div class="fbk"><button class="btn sm" data-fb="Helpful">Helpful</button><button class="btn sm" data-fb="Not helpful">Not helpful</button></div></div>`;
  }).join("") || `<div class="muted small">Pick a golden question on the right or type your own. Every answer comes from the governed metrics layer and cites the metric, version, owner and data-as-of date.</div>`;
  el.innerHTML = `<h1>Adoption Insights Agent</h1><p class="sub">Inside the dashboard. Reads governed metrics only, through a read-only metrics API; the SSO role decides what you can ask about. Scripted demo of every Agent_Test_Questions row (Q01 to Q21).</p>
  <div class="chat"><div class="chatwin" id="chatwin"><div class="chathead"><b>Adoption Insights Agent (prototype; synthetic values)</b><span class="hctl">Viewing as <select id="arole">${Object.entries(ROLES).map(([k, r]) => `<option value="${k}" ${S.role === k ? "selected" : ""}>${r.label}</option>`).join("")}</select> <button class="btn sm" id="clr">Clear</button></span></div>
   <div class="msgs" id="msgs">${msgs}</div>
   <div class="composer"><input id="qin" placeholder="Ask about adoption, health or value metrics..." aria-label="Ask the agent"><button class="btn pri" id="askb">Ask</button></div></div>
   <div class="qlist card p"><h2>Golden question set</h2><div class="small muted">Persona in brackets. Switch role to see answers and refusals change.</div>
   ${Object.entries(byCat).map(([c, qs]) => `<div class="qcat">${esc(c)}</div>` + qs.map(q => `<button class="qbtn" data-q="${q["Question ID"]}"><span class="qid">${q["Question ID"]}</span>${esc(q.Question)} <span class="muted">(${esc(q.Persona)})</span></button>`).join("")).join("")}</div></div>`;
  $$(".qbtn", el).forEach(b => b.onclick = () => ask(b.dataset.q));
  $("#askb").onclick = () => { const v = $("#qin").value.trim(); if (v) ask(v); };
  $("#qin").onkeydown = e => { if (e.key === "Enter") $("#askb").click(); };
  $("#arole").onchange = e => setRole(e.target.value);
  $("#clr").onclick = () => { S.chat = []; renderAgent(); };
  $$("[data-drill]", el).forEach(b => b.onclick = () => { S.cohort = b.dataset.drill; S.region = "All"; audit("Drill-down", "Agent answer to Regional view, " + b.dataset.drill, "Opened"); go("regional"); });
  $$("[data-fb]", el).forEach(b => b.onclick = () => { const i = b.closest(".msg").dataset.i; audit("Feedback", (S.chat[i].qid || "Free text") + ": " + b.dataset.fb, "Routed to metric owner for review"); b.parentNode.innerHTML = `<span class="small muted">Thanks. "${b.dataset.fb}" sent to the metric owner for review.</span>`; });
}
/* Governance */
function liveTests() {
  const t = [], tt = totals(TEAMS);
  t.push(["LF2 Assigned no more than Purchased, all " + TEAMS.length + " teams", TEAMS.every(x => x.assigned <= x.purchased)]);
  t.push(["Funnel monotonic for every team (LF1 to LF6)", TEAMS.every(x => STAGES.every((s, i) => i === 0 || x[STAGES[i - 1][0]] >= x[s[0]]))]);
  t.push(["M01 numerator no more than denominator; denominator above 0", tt.active <= tt.assigned && tt.assigned > 0]);
  t.push(["Vendor MAU no more than provisioned accounts", VENDOR_MAU <= tt.provisioned]);
  const sc = score(); t.push(["M19 recomputes from its pillars (or is withheld)", sc.state === "withheld" || Math.abs(sc.raw - PILLARS.reduce((a, p, i) => a + p.v * S.weights[i], 0) / sc.wsum) < 1e-9]);
  t.push(["M19 withheld when any pillar is missing", (() => { const keep = S.missing.slice(); S.missing[0] = true; const r = score().state === "withheld"; S.missing = keep; return r; })()]);
  t.push(["M18 not calculated without verified hours", (() => { const keep = S.missing[2]; S.missing[2] = true; const r = costPerHour() === null; S.missing[2] = keep; return r; })()]);
  t.push(["M04 interactions match Expected_Results on Golden_Events (gap 10 s)", expectedChecks(10).every(c => c[2])]);
  t.push(["Every Agent_Test_Questions row has a scripted answer for every role", Object.keys(ROLES).every(r => { const keep = S.role; S.role = r; const ok = D.Agent_Test_Questions.every(q => { const a = answerFor(q["Question ID"]); return a && a.text; }); S.role = keep; return ok; })]);
  return t;
}
function renderGov() {
  const el = $("#s-gov"); S.gq = S.gq || ""; S.gp = S.gp || "All";
  const ms = D.Metric_Dictionary.filter(m => (S.gp === "All" || m["Score pillar"] === S.gp) && (m["Metric ID"] + " " + m.Metric + " " + m.Formula + " " + m["Dashboard view"] + " " + m.Tests).toLowerCase().includes(S.gq.toLowerCase()));
  const pillars = [...new Set(D.Metric_Dictionary.map(m => m["Score pillar"]))];
  const lt = liveTests();
  const seed = [
    {t:"Yesterday 16:40", role:"Fraud operations lead", action:"Agent question", detail:"Q12: Which fraud analysts use the assistant least?", result:"Refused, safe alternative offered"},
    {t:"Yesterday 15:12", role:"Regional lead, Region B", action:"Agent question", detail:"Q16: Show utilisation for a market outside my region", result:"Refused, safe alternative offered"},
    {t:"Yesterday 11:05", role:"Platform engineer", action:"Agent question", detail:"Q05: Which connector has the highest failure rate this week?", result:"Answered"},
    {t:"Yesterday 09:02", role:"Analytics lead", action:"Metric change", detail:"M01 Licence utilisation v1 (proposed) submitted for owner review", result:"Pending review"}
  ];
  const log = S.audit.concat(seed);
  const controls = [
    ["The SSO role decides what each person can ask about and see", "Slide 16"],
    ["The agent reaches governed metrics only, through a read-only metrics API; the LLM orchestrator has no direct data access", "Slide 16"],
    ["No raw events or PII in prompts; PII and card data masked at ingestion", "Slide 16"],
    ["Groups below a minimum size hidden; row-level security by region", "Slides 12, 16"],
    ["Every answer, tool call and metric change is audit-logged", "Slides 7, 16"],
    ["Every answer cites metric, version, owner and data freshness; correlation is flagged and cause needs a study", "Slide 14"],
    ["Clear refusals with a safe alternative: named people, missing data, small groups, out of scope, actions", "Slide 14"],
    ["Release testing: golden question set, groundedness, refusal tests, human review, regression evals before each model, prompt or metric change", "Slide 15"],
    ["Live monitoring: groundedness, refusal rate, error rate and data freshness; thresholds agreed with metric owners", "Slide 15"],
    ["Open legal checks: data protection per country, EU AI Act scope, retention of prompt and response logs", "Slide 6"]
  ];
  el.innerHTML = `<h1>Governance and responsible AI</h1><p class="sub">One metric catalogue serves all three views and the agent: each metric has a formula, owner, version and tests. Below it, the audit trail and the controls that govern the agent once live.</p>
  <div class="card" id="catalogue"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Metric catalogue (Metric_Dictionary, ${D.Metric_Dictionary.length} metrics)</h2>
   <div class="row"><input class="search" id="gq" placeholder="Search metric, formula, view or test" value="${esc(S.gq)}" aria-label="Search metrics"><select id="gp" class="btn" aria-label="Filter by pillar">${["All"].concat(pillars).map(p => `<option ${S.gp === p ? "selected" : ""}>${p}</option>`).join("")}</select></div></div>
   <div style="max-height:360px;overflow:auto;margin-top:10px"><table class="cat"><thead><tr><th>ID</th><th>Metric</th><th>Formula</th><th>Pillar</th><th>View</th><th>Owner</th><th>Version</th><th>Tests</th></tr></thead><tbody>
   ${ms.map(m => `<tr data-id="${m["Metric ID"]}"><td><b>${m["Metric ID"]}</b></td><td>${esc(m.Metric)}</td><td class="small">${esc(m.Formula)}</td><td class="small">${esc(m["Score pillar"])}</td><td class="small">${esc(m["Dashboard view"])}</td><td class="small">${esc(m.Owner)}</td><td class="small" style="white-space:nowrap">v1, proposed</td><td class="small">${esc(m.Tests)}</td></tr>
     ${S.gx === m["Metric ID"] ? `<tr class="ex"><td></td><td colspan="7" class="small"><b>Numerator:</b> ${esc(m.Numerator)} · <b>Denominator:</b> ${esc(m.Denominator)} · <b>Unit:</b> ${esc(m.Unit)} · <b>Direction:</b> ${esc(m.Direction)} · <b>Scoring:</b> ${esc(m["Scoring treatment"])}<br><b>Missing-data rule:</b> ${esc(m["Missing-data rule"])} · <b>Status:</b> ${esc(m.Status)}</td></tr>` : ""}`).join("") || '<tr><td colspan="8" class="muted">No metrics match</td></tr>'}</tbody></table></div>
   <p class="note">Click a row for numerator, denominator, scoring and missing-data rule. Owners are to be named; versions stay proposed until sign-off at Gate 2 (week 12).</p></div>
  <div class="grid" style="grid-template-columns:1.3fr 1fr;margin-top:14px">
   <div class="card" id="audit"><h2>Audit trail</h2><p class="small muted" style="margin-top:-4px">Every agent question, refusal, feedback vote, role switch and score simulation in this session is appended live. Seed rows are synthetic.</p>
    <table><thead><tr><th>Time</th><th>Role</th><th>Action</th><th>Detail</th><th>Result</th></tr></thead><tbody>${log.slice(0, 12).map(r => `<tr><td class="small">${r.t}</td><td class="small">${esc(r.role)}</td><td class="small">${esc(r.action)}</td><td class="small">${esc(r.detail)}</td><td class="small">${esc(r.result)}</td></tr>`).join("")}</tbody></table></div>
   <div class="card tests" id="livetests"><h2>Metric tests run on the demo data</h2>${lt.map(x => `<div><span class="${x[1] ? "pass" : "fail"}">${x[1] ? "Pass" : "Fail"}</span> ${esc(x[0])}</div>`).join("")}
    <p class="note">These run in the browser against the synthetic data only. No tests have been run on real NimbusPay data.</p></div>
  </div>
  <div class="grid g2" style="margin-top:14px">
   <div class="card"><h2>Responsible-AI controls</h2>${controls.map(c => `<div class="ctl"><span class="ck">&#10003;</span><span>${esc(c[0])} <span class="tag">${c[1]}</span></span></div>`).join("")}</div>
   <div class="card"><h2>Risk register and phase gates</h2><table><thead><tr><th>ID</th><th>Risk</th><th>Early-warning signal</th><th>Owner</th></tr></thead><tbody>${D.Risk_Register.map(r => `<tr><td>${r["Risk ID"]}${r["Watch closely"] === "Yes" ? ' <span class="tag red">watch</span>' : ""}</td><td class="small">${esc(r.Risk)}</td><td class="small">${esc(r["Early-warning signal"])}</td><td class="small">${esc(r.Owner)}</td></tr>`).join("")}</tbody></table>
    <div style="margin-top:10px">${D.Roadmap_Gates.filter(g => g.Row.startsWith("Gate")).map(g => `<div class="ev"><span><b>${g.Row}, ${g["Workstream or gate"].toLowerCase()}</b><br><span class="small muted">${esc(g["Exit criteria or output"])}</span></span></div>`).join("")}</div></div>
  </div>`;
  $("#gq").oninput = e => { S.gq = e.target.value; renderGov(); const i = $("#gq"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
  $("#gp").onchange = e => { S.gp = e.target.value; renderGov(); };
  $$(".cat tbody tr[data-id]", el).forEach(r => r.onclick = () => { S.gx = S.gx === r.dataset.id ? null : r.dataset.id; renderGov(); });
}

/* Header controls */
function setRole(r) { S.role = r; S.region = "All"; $("#role").value = r; audit("Role switch", "Viewing as " + ROLES[r].label, "Scope applied"); render(); }
function header() {
  $("#role").innerHTML = Object.entries(ROLES).map(([k, r]) => `<option value="${k}">${r.label}</option>`).join("");
  $("#role").value = S.role; $("#role").onchange = e => setRole(e.target.value);
  $("#scen").onchange = e => { S.scenario = e.target.value; audit("Data state", e.target.options[e.target.selectedIndex].text, "Views refreshed"); render(); };
  $("#preset").innerHTML = Object.entries(PRESETS).map(([k, p]) => `<option value="${k}">${p.label}</option>`).join("");
  $("#preset").value = S.preset;
  $("#preset").onchange = e => { applyPreset(e.target.value); audit("Scenario", PRESETS[S.preset].label, "Synthetic data replaced across all views"); render(); };
  $("#tourb").onclick = () => tour(0);
}

/* Guided demo */
const TOUR = [
  {s:"exec", h:"#exec-score", t:"The executive question", p:"The renewal is coming, and leadership asks whether the AI platform is worth it. Today they only see vendor MAU. This view answers with an AI value score beside its five pillars, plus habitual users, verified hours, utilisation and cost per verified hour.", pre(){ S.role = "exec"; S.scenario = "live"; $("#scen").value = "live"; applyPreset("baseline"); $("#preset").value = "baseline"; $("#role").value = "exec"; S.breach = false; S.missing = PILLARS.map(() => false); S.weights = PILLARS.map(p => p.w); }},
  {s:"count", h:"#count-kpis", t:"Why MAU misleads", p:"Vendor-style counting treats every logged row as usage. One fraud-review question writes five events, and a login with no question still counts. On these nine golden events, raw counting reports 9 uses and three active users.", pre(){ S.countMode = "raw"; S.gap = 10; }},
  {s:"count", h:"#evt-table", t:"How we count", p:"Events are grouped into logical interactions: by interaction ID where validated (exact), by sessionisation as the fallback (labelled approximate), and a login alone never counts. 9 events = 2 interactions, a 4.5x overstatement, and all six Expected_Results checks pass.", pre(){ S.countMode = "logical"; S.gap = 10; }},
  {s:"regional", h:"#funnel", t:"The licence funnel", p:"Purchased, assigned, provisioned, active, engaged and habitual, by region and launch cohort. The gap between assigned and active is paid but unused seats, which the intervention list turns into actions: reassign, train or right-size.", pre(){ S.region = "All"; S.cohort = "All"; }},
  {s:"agent", h:"#chatwin", t:"The agent answers, with a citation", p:"Asked why utilisation dropped in launch cohort 2, the Adoption Insights Agent answers from governed metrics, cites metric, version, owner and data-as-of date, and flags that correlation is not cause. Asked about named analysts, it refuses and offers a team view.", pre(){ S.chat = []; }, post(){ ask("Q07"); ask("Q12"); }},
  {s:"exec", h:"#renewal", t:"The renewal decision", p:"Four evidence areas, checked against thresholds agreed in advance, give one of five outcomes. Here utilisation is below the demo threshold, so the recommendation is renew and right-size. A missing pillar withholds the score; a critical breach turns it red and forces remediation conditions.", pre(){}}
];
let TI = -1;
function tour(i) {
  $$(".hl").forEach(e => e.classList.remove("hl"));
  if (i < 0 || i >= TOUR.length) { $("#tour").style.display = "none"; document.body.classList.remove("touring"); TI = -1; return; }
  document.body.classList.add("touring");
  TI = i; const st = TOUR[i]; st.pre && st.pre(); go(st.s); st.post && st.post(); if (st.s === "agent") { const m = $("#msgs"); m.scrollTop = 0; }
  const h = $(st.h); if (h) { h.classList.add("hl"); h.scrollIntoView({block:"center"}); }
  $("#tour").style.display = "block";
  $("#tour").innerHTML = `<div class="dots">${TOUR.map((_, j) => `<i class="${j <= i ? "on" : ""}"></i>`).join("")}</div><div class="st">Guided demo · step ${i + 1} of ${TOUR.length}</div><div class="tb"><div class="tx"><h3>${st.t}</h3><p>${st.p}</p></div>
   <div class="row" style="flex:none"><button class="btn sm" id="tx">Close</button><button class="btn sm" id="tp" ${i === 0 ? "disabled" : ""}>Back</button><button class="btn pri sm" id="tn">${i === TOUR.length - 1 ? "Finish" : "Next"}</button></div></div>`;
  $("#tx").onclick = () => tour(-1); $("#tp").onclick = () => tour(i - 1); $("#tn").onclick = () => tour(i + 1);
}
document.addEventListener("keydown", e => { if (TI < 0 || e.target.tagName === "INPUT") return; if (e.key === "ArrowRight") tour(TI + 1); if (e.key === "ArrowLeft") tour(TI - 1); if (e.key === "Escape") tour(-1); });
window.DEMO = {applyPreset, PRESETS, renewal, go, tour, ask, setRole, S, liveTests, answerFor, ROLES};
header(); go(location.hash && SCREENS.some(s => "#" + s[0] === location.hash) ? location.hash.slice(1) : "exec");
