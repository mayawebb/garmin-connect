const COLORS = { green: "#a7d9bd", green2: "#5eaa82", gold: "#e5ad78", blue: "#94b4cf", purple: "#b7a5d4", muted: "#9aa79e", line: "#344139", panel: "#1b2520" };
const SAMPLE_URL = "sample-data.json";
let dataset = null;
let usingSample = true;

const $ = (selector) => document.querySelector(selector);
const fmtPace = (minutes) => {
  if (!Number.isFinite(minutes) || minutes <= 0) return "Unavailable";
  const seconds = Math.round(minutes * 60);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} /km`;
};
const dateOnly = (value) => String(value || "").slice(0, 10);
const asDate = (value) => new Date(`${dateOnly(value)}T12:00:00`);
const dateLabel = (value, options = { month: "short", day: "numeric" }) => asDate(value).toLocaleDateString(undefined, options);
const activityPace = (activity) => activity.distance_km > 0 && activity.duration_s > 0 ? activity.duration_s / 60 / activity.distance_km : null;
const running = (activity) => /run/i.test(activity.type || "") && !/treadmill/i.test(activity.type || "");
const median = (values) => {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  return sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
};
const average = (values) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
const isNumber = (value) => typeof value === "number" && Number.isFinite(value);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

function setPage(name) {
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === `${name}-page`));
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.page === name));
  window.location.hash = name;
  if (dataset) renderPage(name);
}

function layoutChart(id, traces, options = {}) {
  const target = document.getElementById(id);
  if (!target || !window.Plotly) {
    if (target) target.innerHTML = '<p class="chart-note">Charts need a connection to load the Plotly library.</p>';
    return;
  }
  const layout = {
    paper_bgcolor: COLORS.panel, plot_bgcolor: COLORS.panel, autosize: true, margin: { l: 48, r: 14, t: 10, b: 42 },
    font: { family: "DM Mono, monospace", size: 9, color: COLORS.muted }, hoverlabel: { bgcolor: "#25332b", bordercolor: COLORS.line, font: { color: "#edf1ec", size: 10 } },
    xaxis: { gridcolor: "transparent", linecolor: COLORS.line, tickfont: { size: 9 }, ...options.xaxis },
    yaxis: { gridcolor: COLORS.line, zerolinecolor: COLORS.line, linecolor: COLORS.line, tickfont: { size: 9 }, ...options.yaxis },
    showlegend: options.showlegend ?? true, legend: { orientation: "h", y: 1.14, x: 0, font: { size: 9 } },
  };
  window.Plotly.react(target, traces, layout, { responsive: true, displayModeBar: false });
}

function getWeeks(activities) {
  const map = new Map();
  activities.filter(running).forEach((activity) => {
    if (!activity.date) return;
    const day = asDate(activity.date);
    const mondayOffset = (day.getDay() + 6) % 7;
    day.setDate(day.getDate() - mondayOffset);
    const key = day.toISOString().slice(0, 10);
    if (!map.has(key)) map.set(key, { week: key, distance: 0, knownRuns: 0, runs: 0, paces: [], hrs: [] });
    const row = map.get(key);
    row.runs += 1;
    if (isNumber(activity.distance_km)) { row.distance += activity.distance_km; row.knownRuns += 1; }
    const pace = activityPace(activity);
    if (isNumber(pace)) row.paces.push(pace);
    if (isNumber(activity.average_hr_bpm)) row.hrs.push(activity.average_hr_bpm);
  });
  if (!map.size) return [];
  const sortedKeys = [...map.keys()].sort();
  const week = asDate(sortedKeys[0]);
  const last = asDate(sortedKeys.at(-1));
  const rows = [];
  while (week <= last) {
    const key = week.toISOString().slice(0, 10);
    rows.push(map.get(key) || { week: key, distance: 0, knownRuns: 0, runs: 0, paces: [], hrs: [] });
    week.setDate(week.getDate() + 7);
  }
  return rows.map((row, i) => ({ ...row, rolling: average(rows.slice(Math.max(0, i - 3), i + 1).map((x) => x.distance)) }));
}

function renderAnalytics() {
  const activities = dataset.activities || [];
  const runs = activities.filter(running);
  const knownDistance = runs.map((a) => a.distance_km).filter(isNumber);
  const medianPace = median(runs.map(activityPace));
  const weeks = getWeeks(activities);
  const completeWeeks = weeks.filter((week) => {
    const now = new Date();
    const currentMonday = new Date(now);
    currentMonday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
    currentMonday.setHours(0, 0, 0, 0);
    return asDate(week.week) < currentMonday;
  });
  const avgWeek = average(completeWeeks.map((w) => w.distance));
  const estimated = runs.filter((a) => a.distance_km >= 2 && isNumber(a.duration_s)).map((a) => ({ date: a.date, seconds: a.duration_s * (5 / a.distance_km) ** 1.06 }));
  const values = [
    ["Outdoor run sessions", runs.length, "recorded activities"],
    ["Run distance", knownDistance.length ? `${knownDistance.reduce((a, b) => a + b, 0).toFixed(1)} km` : "Unavailable", `${knownDistance.length} with distance`],
    ["Longest recorded run", knownDistance.length ? `${Math.max(...knownDistance).toFixed(1)} km` : "Unavailable", "distance where recorded"],
    ["Median run pace", fmtPace(medianPace), "median of run averages"],
    ["Avg per complete week", avgWeek === null ? "Unavailable" : `${avgWeek.toFixed(1)} km`, `${completeWeeks.length} complete weeks`],
  ];
  $("#analytics-metrics").innerHTML = values.map(([label, value, sub]) => `<div class="metric"><span class="metric-label">${esc(label)}</span><strong class="metric-value">${esc(value)}</strong><span class="metric-sub">${esc(sub)}</span></div>`).join("");
  const story = trainingStory(weeks, runs);
  $("#training-story .story-copy").textContent = story;

  const visibleWeeks = weeks.slice(-26);
  layoutChart("weekly-distance", [
    { type: "bar", x: visibleWeeks.map((w) => w.week), y: visibleWeeks.map((w) => w.distance), name: "Distance", marker: { color: COLORS.green2 }, hovertemplate: "Week of %{x}<br>%{y:.1f} km<extra></extra>" },
    { type: "scatter", x: visibleWeeks.map((w) => w.week), y: visibleWeeks.map((w) => w.rolling), mode: "lines", name: "4-week mean", line: { color: COLORS.gold, width: 2.5 }, hovertemplate: "4-week mean: %{y:.1f} km<extra></extra>" },
  ], { yaxis: { title: "km", rangemode: "tozero" }, xaxis: { tickformat: "%b %d", nticks: 8 } });

  const pacePoints = runs.filter((a) => isNumber(activityPace(a))).slice(-100);
  const paceSmooth = pacePoints.map((activity, index) => median(pacePoints.slice(Math.max(0, index - 4), index + 1).map(activityPace)));
  layoutChart("pace-trend", [
    { type: "scatter", x: pacePoints.map((a) => a.date), y: pacePoints.map(activityPace), mode: "markers", name: "Run", marker: { color: COLORS.blue, size: 7 }, hovertemplate: "%{x|%b %d, %Y}<br>%{customdata}<extra></extra>", customdata: pacePoints.map((a) => fmtPace(activityPace(a))) },
    { type: "scatter", x: pacePoints.map((a) => a.date), y: paceSmooth, mode: "lines", name: "5-run median", line: { color: COLORS.gold, width: 2.5 }, hovertemplate: "5-run median: %{customdata}<extra></extra>", customdata: paceSmooth.map(fmtPace) },
  ], { yaxis: { title: "min/km", autorange: "reversed", tickvals: paceTicks(pacePoints.map(activityPace)), ticktext: paceTicks(pacePoints.map(activityPace)).map(fmtPace) }, xaxis: { tickformat: "%b %Y", nticks: 6 } });
  layoutChart("race-trend", [
    { type: "scatter", x: estimated.map((a) => a.date), y: estimated.map((a) => a.seconds), mode: "markers", name: "Run equivalent", marker: { color: COLORS.purple, size: 7 }, hovertemplate: "%{x|%b %d}<br>%{customdata}<extra></extra>", customdata: estimated.map((a) => fmtDuration(a.seconds)) },
    { type: "scatter", x: estimated.map((a) => a.date), y: estimated.map((a, index) => median(estimated.slice(Math.max(0, index - 4), index + 1).map((x) => x.seconds))), mode: "lines", name: "5-run median", line: { color: COLORS.gold, width: 2.5 }, hovertemplate: "5-run median: %{customdata}<extra></extra>", customdata: estimated.map((a, index) => fmtDuration(median(estimated.slice(Math.max(0, index - 4), index + 1).map((x) => x.seconds)))) },
  ], { yaxis: { title: "5 km equivalent", autorange: "reversed", tickformat: ".0f", tickvals: timeTicks(estimated.map((a) => a.seconds)), ticktext: timeTicks(estimated.map((a) => a.seconds)).map(fmtDuration) }, xaxis: { tickformat: "%b %Y", nticks: 6 } });
  renderActivityMix(activities);
  renderActivityTable(activities);
}

function paceTicks(values) { const valid = values.filter(isNumber); if (!valid.length) return []; const min = Math.floor(Math.min(...valid) * 2) / 2; const max = Math.ceil(Math.max(...valid) * 2) / 2; const span = max - min; const step = span > 5 ? 1 : span > 2 ? .5 : .25; const ticks = []; for (let x = min; x <= max + .001; x += step) ticks.push(Number(x.toFixed(2))); return ticks; }
function timeTicks(values) { const valid = values.filter(isNumber); if (!valid.length) return []; const min = Math.floor(Math.min(...valid) / 60) * 60; const max = Math.ceil(Math.max(...valid) / 60) * 60; const step = max - min > 1200 ? 300 : max - min > 600 ? 120 : 60; const ticks = []; for (let x = min; x <= max; x += step) ticks.push(x); return ticks; }
function fmtDuration(seconds) { if (!isNumber(seconds)) return "Unavailable"; const whole = Math.round(seconds); return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`; }
function trainingStory(weeks, runs) {
  const complete = weeks.filter((week) => week.week < currentWeekKey());
  if (complete.length < 8) return `There are ${complete.length} complete calendar weeks in the visible record. Build a longer history before comparing training blocks.`;
  const recent = complete.slice(-4), prior = complete.slice(-8, -4);
  const recentKm = average(recent.map((w) => w.distance)); const priorKm = average(prior.map((w) => w.distance));
  const recentRuns = recent.reduce((sum, w) => sum + w.runs, 0); const priorRuns = prior.reduce((sum, w) => sum + w.runs, 0);
  const change = priorKm > 0 ? Math.round((recentKm / priorKm - 1) * 100) : null;
  const recentLength = recentRuns ? recent.reduce((sum, week) => sum + week.distance, 0) / recentRuns : 0;
  const priorLength = priorRuns ? prior.reduce((sum, week) => sum + week.distance, 0) / priorRuns : 0;
  const direction = change === null ? "" : change > 3 ? `up ${change}%` : change < -3 ? `down ${Math.abs(change)}%` : "about level";
  return `Across the last four complete weeks, average running volume was ${recentKm.toFixed(1)} km/week (${direction}) versus ${priorKm.toFixed(1)} km/week in the previous block. You logged ${recentRuns} runs versus ${priorRuns}; average distance per run moved from ${priorLength.toFixed(1)} to ${recentLength.toFixed(1)} km.`;
}
function currentWeekKey() { const day = new Date(); day.setHours(12, 0, 0, 0); day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); return day.toISOString().slice(0, 10); }

function renderActivityMix(activities) {
  const weeks = new Map();
  activities.filter((a) => !/treadmill/i.test(a.type || "")).forEach((a) => {
    const day = asDate(a.date); day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); const week = day.toISOString().slice(0, 10);
    const type = /run/i.test(a.type) ? "Running" : /strength/i.test(a.type) ? "Strength" : /yoga|pilates/i.test(a.type) ? "Yoga / mobility" : /cycl|cardio/i.test(a.type) ? "Cardio" : prettifyType(a.type);
    if (!weeks.has(week)) weeks.set(week, {}); weeks.get(week)[type] = (weeks.get(week)[type] || 0) + 1;
  });
  const all = [...weeks.keys()].sort().slice(-20); const types = [...new Set([...weeks.values()].flatMap((x) => Object.keys(x)))];
  const palette = [COLORS.green2, COLORS.gold, COLORS.blue, COLORS.purple, COLORS.red, "#c2c987"];
  layoutChart("activity-mix", types.map((type, index) => ({ type: "bar", x: all, y: all.map((week) => weeks.get(week)?.[type] || 0), name: type, marker: { color: palette[index % palette.length] }, hovertemplate: `${esc(type)}<br>%{y} sessions<extra></extra>` })), { barmode: "stack", yaxis: { title: "sessions", rangemode: "tozero", dtick: 1 }, xaxis: { tickformat: "%b %d", nticks: 8 } });
}
function prettifyType(type) { return String(type || "Activity").replace(/_/g, " ").replace(/\b\w/g, (x) => x.toUpperCase()); }
function renderActivityTable(activities) {
  const recent = [...activities].filter((a) => !/treadmill/i.test(a.type || "")).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 14);
  $("#activity-table").innerHTML = recent.map((a) => { const pace = running(a) ? activityPace(a) : null; return `<tr><td>${esc(dateLabel(a.date, { year: "numeric", month: "short", day: "numeric" }))}</td><td>${esc(prettifyType(a.type))}</td><td class="mono">${isNumber(a.distance_km) ? `${a.distance_km.toFixed(1)} km` : "—"}</td><td class="mono">${isNumber(a.duration_s) ? fmtDuration(a.duration_s) : "—"}</td><td class="mono">${isNumber(a.elevation_m) ? `${Math.round(a.elevation_m)} m` : "—"}</td><td class="mono">${isNumber(pace) ? esc(fmtPace(pace)) : "—"}</td><td class="mono">${isNumber(a.average_hr_bpm) ? `${Math.round(a.average_hr_bpm)} bpm` : "—"}</td></tr>`; }).join("") || '<tr><td colspan="7">No activities with usable dates in this file.</td></tr>';
}

const HEALTH_UNITS = { "Steps": "steps", "Resting heart rate": "bpm", "Daily minimum heart rate": "bpm", "Daily maximum heart rate": "bpm", "Body Battery": "score", "Body Battery charged": "score", "Average stress": "level", "Average respiration": "breaths/min", "Sleep score": "score", "Sleep duration": "hours", "Deep sleep": "hours", "REM sleep": "hours", "Average heart rate during sleep": "bpm", "Nightly HRV": "ms", "Weekly HRV average": "ms", "Average heart rate on runs": "bpm", "VO₂ max": "ml/kg/min", "VO2 max": "ml/kg/min" };
function renderHealth() {
  const health = dataset.health || [];
  const names = [...new Set(health.map((x) => x.metric).filter(Boolean))].sort((a, b) => (a === "Average heart rate on runs" ? -1 : b === "Average heart rate on runs" ? 1 : a.localeCompare(b)));
  const selector = $("#health-select"); selector.innerHTML = names.map((name) => `<option>${esc(name)}</option>`).join("");
  const cardMetrics = ["Sleep duration", "Sleep score", "Resting heart rate", "Nightly HRV", "Body Battery", "Steps"];
  $("#health-cards").innerHTML = cardMetrics.map((metric) => {
    const unit = HEALTH_UNITS[metric]; const rows = health.filter((x) => x.metric === metric && isNumber(x.value)).sort((a, b) => dateOnly(a.date).localeCompare(dateOnly(b.date)));
    const latest = rows.length ? rows.at(-1) : null; const cut = latest ? new Date(`${dateOnly(latest.date)}T12:00:00`) : null;
    const last7 = rows.filter((x) => cut && (cut - asDate(x.date)) / 86400000 >= 0 && (cut - asDate(x.date)) / 86400000 < 7);
    const prior = rows.filter((x) => cut && (cut - asDate(x.date)) / 86400000 >= 7 && (cut - asDate(x.date)) / 86400000 < 14);
    const recentMean = average(last7.map((x) => x.value)); const priorMean = average(prior.map((x) => x.value));
    const delta = recentMean !== null && priorMean !== null ? recentMean - priorMean : null;
    return `<div class="health-card"><label>${esc(metric)}</label><strong>${latest ? `${formatHealth(latest.value, metric)}` : "—"}</strong><small>${latest ? `${esc(dateLabel(latest.date))} · ${delta === null ? "no prior week" : `${delta > 0 ? "+" : ""}${delta.toFixed(metric === "Sleep duration" ? 1 : 0)} vs prior week`}` : "Not in this export"}</small></div>`;
  }).join("");
  if (names.length) { if (!names.includes(selector.value)) selector.value = names[0]; renderHealthTrend(); } else { $("#health-trend").innerHTML = '<p class="chart-note">No wellness measures are included in this export.</p>'; }

  const runHr = (dataset.activities || []).filter(running).filter((a) => isNumber(a.average_hr_bpm));
  const weeks = getWeeks(runHr);
  layoutChart("run-hr", [{ type: "scatter", x: weeks.map((w) => w.week), y: weeks.map((w) => median(w.hrs)), mode: "markers+lines", name: "Weekly median", marker: { color: COLORS.blue, size: 7 }, line: { color: COLORS.blue, width: 1.5 }, customdata: weeks.map((w) => w.hrs.length), hovertemplate: "Week of %{x}<br>%{y:.0f} bpm<br>%{customdata} run(s)<extra></extra>" }], { showlegend: false, yaxis: { title: "bpm" }, xaxis: { tickformat: "%b %d", nticks: 6 } });
  renderSleepInsight(health, dataset.activities || []);
  const vo2 = health.filter((x) => /vo.?2\s*max/i.test(x.metric || "") && isNumber(x.value));
  $("#vo2-copy").textContent = vo2.length ? `${vo2.length} recorded VO₂ max value${vo2.length === 1 ? "" : "s"} are present; latest is ${vo2.at(-1).value.toFixed(1)} ${HEALTH_UNITS[vo2.at(-1).metric] || ""} on ${dateLabel(vo2.at(-1).date, { year: "numeric", month: "short", day: "numeric" })}.` : "No VO₂ max reading is present in the uploaded export. This dashboard does not estimate or invent one.";
}
function formatHealth(value, metric) { if (metric === "Sleep duration") { const h = Math.floor(value); return `${h}h ${Math.round((value - h) * 60)}m`; } if (metric === "Steps") return Math.round(value).toLocaleString(); return `${Number(value).toFixed(metric.includes("score") || metric.includes("Battery") ? 0 : 0)} ${HEALTH_UNITS[metric] || ""}`; }
function renderHealthTrend() {
  const metric = $("#health-select").value; if (!metric) return;
  $("#health-chart-title").textContent = metric;
  const rows = (dataset.health || []).filter((x) => x.metric === metric && x.date && isNumber(x.value)).sort((a, b) => dateOnly(a.date).localeCompare(dateOnly(b.date)));
  const smooth = rows.map((row, i) => { const end = asDate(row.date); return average(rows.slice(0, i + 1).filter((x) => { const gap = (end - asDate(x.date)) / 86400000; return gap >= 0 && gap < 7; }).map((x) => x.value)); });
  const unit = rows[0]?.unit || HEALTH_UNITS[metric] || "";
  layoutChart("health-trend", [
    { type: "scatter", x: rows.map((x) => x.date), y: rows.map((x) => x.value), mode: "markers", name: "Recorded", marker: { color: "#73847a", size: 6, opacity: .6 }, hovertemplate: `%{x}<br>%{y:.1f} ${esc(unit)}<extra></extra>` },
    { type: "scatter", x: rows.map((x) => x.date), y: smooth, mode: "lines", name: "7-day mean", line: { color: COLORS.green, width: 2.5 }, hovertemplate: `%{y:.1f} ${esc(unit)} · rolling 7 days<extra></extra>` },
  ], { yaxis: { title: unit }, xaxis: { tickformat: "%b %Y", nticks: 8 } });
}
function renderSleepInsight(health, activities) {
  const scores = new Map(health.filter((x) => x.metric === "Sleep score" && isNumber(x.value)).map((x) => [dateOnly(x.date), x.value]));
  const matched = activities.filter(running).map((a) => ({ activity: a, sleep: scores.get(dateOnly(a.date)), pace: activityPace(a) })).filter((x) => isNumber(x.sleep) && isNumber(x.pace) && isNumber(x.activity.average_hr_bpm));
  if (matched.length < 4) { $("#sleep-insight").textContent = `There are ${matched.length} matched runs with same-date sleep score, pace, and heart rate. More matched data is needed for a useful comparison.`; return; }
  const threshold = median(matched.map((x) => x.sleep));
  const low = matched.filter((x) => x.sleep <= threshold); const high = matched.filter((x) => x.sleep > threshold);
  if (!low.length || !high.length) { $("#sleep-insight").textContent = "Sleep-score readings do not split into two usable groups."; return; }
  const lowP = median(low.map((x) => x.pace)); const highP = median(high.map((x) => x.pace)); const dsec = Math.round((highP - lowP) * 60);
  const paceText = dsec > 0 ? `${dsec} sec/km slower` : dsec < 0 ? `${Math.abs(dsec)} sec/km faster` : "at the same median pace";
  const lowHr = median(low.map((x) => x.activity.average_hr_bpm)); const highHr = median(high.map((x) => x.activity.average_hr_bpm)); const dhr = Math.round(highHr - lowHr);
  const hrText = dhr > 0 ? `${dhr} bpm higher` : dhr < 0 ? `${Math.abs(dhr)} bpm lower` : "the same";
  $("#sleep-insight").textContent = `Across ${matched.length} matched runs, the above-median sleep-score group was ${paceText} than the lower-score group. Its median run heart rate was ${hrText}.`;
}

const PLAN_TEMPLATES = {
  "5k": ["Easy run 30–40 min + 4 relaxed strides", "5 × 3 min comfortably hard; 2 min easy jog", "Easy run 30 min or strength session", "Long easy run 45–55 min"],
  "10k": ["Easy run 35–45 min", "3 × 8 min steady; 3 min easy jog", "Easy run 30 min + strength", "Long easy run 55–70 min"],
  half: ["Easy run 40–50 min", "4 × 6 min steady; 2 min easy jog", "Recovery jog 25–35 min + strength", "Long easy run 65–80 min"],
  easy: ["Easy conversational run 30–40 min", "Easy run 35 min; keep effort comfortable", "Strength or mobility; no hard running", "Easy run 40–50 min, relaxed finish"],
  strength: ["Full-body strength A; moderate loads", "Easy cardio 25–40 min", "Full-body strength B; leave 2 reps in reserve", "Optional mobility or easy walk"],
  recovery: ["Easy run or walk 25–35 min", "Mobility or yoga 20–30 min", "Easy conversational cardio 30–40 min", "Rest day; optional gentle walk"],
};
const PLAN_TITLES = { "5k": "5K speed foundation", "10k": "10K steady build", half: "Half-marathon base", easy: "Easier aerobic running", strength: "Consistent strength week", recovery: "Balanced training and recovery" };
let currentPlan = null;
function makePlan() {
  const goal = $("#plan-goal").value; const runs = (dataset.activities || []).filter(running); const counts = getWeeks(dataset.activities || []).slice(-4).map((w) => w.runs); const sessions = Math.max(2, Math.min(5, Math.round(average(counts) || 3)));
  const weeks = PLAN_TEMPLATES[goal].map((item, i) => ({ week: i + 1, sessions, focus: item }));
  currentPlan = { id: Date.now(), goal, title: PLAN_TITLES[goal], createdAt: new Date().toISOString(), weeks };
  renderPlan(currentPlan); $("#plan-result").hidden = false;
}
function renderPlan(plan) {
  $("#plan-result").innerHTML = `<h3>${esc(plan.title)}</h3><p>Four-week outline · based on ${((dataset.activities || []).filter(running)).length} recorded runs · adjust volume to what feels sustainable.</p><div class="week-list">${plan.weeks.map((week) => `<div class="week-card"><b>WEEK ${week.week} / ${week.sessions} SESSIONS</b><p>${esc(week.focus)}</p></div>`).join("")}</div><button class="button primary" id="save-plan">Save this plan</button>`;
  $("#save-plan").addEventListener("click", () => { const saved = readPlans(); saved.unshift(plan); localStorage.setItem("training-lab-plans", JSON.stringify(saved.slice(0, 20))); renderSavedPlans(); toast("Plan saved in this browser."); });
}
function readPlans() { try { const plans = JSON.parse(localStorage.getItem("training-lab-plans") || "[]"); return Array.isArray(plans) ? plans : []; } catch { return []; } }
function renderSavedPlans() {
  const plans = readPlans();
  $("#saved-plans").innerHTML = plans.length ? plans.map((plan) => `<article class="saved-card"><time>${esc(new Date(plan.createdAt).toLocaleDateString())}</time><h3>${esc(plan.title)}</h3><p>4-week outline · ${esc(plan.weeks?.[0]?.sessions ?? "—")} sessions per week</p><button data-delete-plan="${Number(plan.id)}">Delete plan</button></article>`).join("") : '<p class="empty-saved">No plans saved on this device yet.</p>';
  document.querySelectorAll("[data-delete-plan]").forEach((button) => button.addEventListener("click", () => { localStorage.setItem("training-lab-plans", JSON.stringify(readPlans().filter((plan) => plan.id !== Number(button.dataset.deletePlan)))); renderSavedPlans(); }));
}

function answerQuestion(question) {
  const q = question.toLowerCase(); const activities = dataset.activities || []; const runs = activities.filter(running); const weeks = getWeeks(activities); const health = dataset.health || [];
  if (/chart|graph|plot|visuali[sz]/.test(q)) {
    const metric = [...new Set(health.map((x) => x.metric).filter(Boolean))].find((name) => q.includes(name.toLowerCase()));
    if (metric) { setPage("health"); $("#health-select").value = metric; renderHealthTrend(); return `Opened the ${metric} trend in Health using the recorded dates in this export.`; }
    if (/weekly.*(run|distance)|running.*distance/.test(q)) { setPage("analytics"); return "The weekly running distance chart is shown on Analytics, with a four-week mean."; }
    if (/pace/.test(q)) { setPage("analytics"); return "The run pace chart is shown on Analytics, with pace labeled in min:sec per kilometer."; }
    if (/activity|sport|strength/.test(q)) { setPage("analytics"); return "The activity mix chart is shown on Analytics. It includes all tracked non-treadmill activity types."; }
    return "I can open a recorded health metric by name, or show the built-in weekly distance, pace, and activity mix charts. Ask for one of those.";
  }
  if (/vo.?2|max/.test(q)) { const values = health.filter((x) => /vo.?2\s*max/i.test(x.metric || "") && isNumber(x.value)); return values.length ? `The latest recorded VO₂ max in this export is ${values.at(-1).value.toFixed(1)} on ${dateLabel(values.at(-1).date)}.` : "There is no recorded VO₂ max value in this data export, so I can’t evaluate a trend or suggest a data-based target."; }
  if (/sleep|recover|recovery/.test(q)) { const name = /score/.test(q) ? "Sleep score" : /hrv/.test(q) ? "Nightly HRV" : /resting|rhr/.test(q) ? "Resting heart rate" : "Sleep duration"; const rows = health.filter((x) => x.metric === name && isNumber(x.value)); return rows.length ? `The latest ${name.toLowerCase()} is ${formatHealth(rows.at(-1).value, name)} on ${dateLabel(rows.at(-1).date)}. I can show its dated trend on the Health tab.` : `${name} is not present in this export. Missing data stays unavailable.`; }
  if (/heart|\bhr\b/.test(q)) { const rows = runs.filter((a) => isNumber(a.average_hr_bpm)); return rows.length ? `Across ${rows.length} outdoor runs with average heart rate, the median recorded value is ${median(rows.map((a) => a.average_hr_bpm)).toFixed(0)} bpm. Compare similar routes and paces before reading this as a fitness change.` : "There are no outdoor runs with recorded average heart rate in this export."; }
  if (/pace|fast|time/.test(q)) { const paces = runs.map(activityPace).filter(isNumber); return paces.length ? `Your median recorded outdoor-run pace is ${fmtPace(median(paces))} across ${paces.length} runs with distance and duration. That is the middle of your run averages, not a race target.` : "There are no runs with both distance and duration available."; }
  if (/week|distance|volume|kilometer|km/.test(q)) { const valid = weeks.filter((w) => w.week < currentWeekKey()); const recent = valid.slice(-4); return recent.length ? `Your last ${recent.length} complete weeks average ${average(recent.map((w) => w.distance)).toFixed(1)} km of running per week. ${recent.reduce((n, w) => n + w.runs, 0)} run sessions were recorded. Open Analytics for the full trend.` : "There are not enough complete weeks in this export to summarize running volume."; }
  const types = new Map(); activities.filter((a) => !/treadmill/i.test(a.type || "")).forEach((a) => types.set(prettifyType(a.type), (types.get(prettifyType(a.type)) || 0) + 1));
  if (/activity|sport|workout|strength|yoga|cycle/.test(q)) return types.size ? `Your visible activity mix is ${[...types.entries()].map(([type, count]) => `${type}: ${count}`).join("; ")}. Treadmill runs are excluded.` : "No activities are in this export.";
  return "I can summarize recorded running distance, pace, heart rate, sleep, recovery measures, activity mix, or VO₂ max availability. Try asking for one of those.";
}
function addChat(text, who) { const node = document.createElement("div"); node.className = `chat-bubble ${who}`; node.textContent = text; $("#chat-messages").append(node); $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight; }
function toast(message) { const node = $("#toast"); node.textContent = message; node.classList.add("show"); setTimeout(() => node.classList.remove("show"), 2200); }

function renderPage(name) { if (name === "analytics") renderAnalytics(); if (name === "health") renderHealth(); if (name === "plans") renderSavedPlans(); }
function validateData(data) {
  if (!data || data.schema_version !== 1 || !Array.isArray(data.activities) || !Array.isArray(data.health)) throw new Error("This file is not a supported Training Lab export (schema version 1). Download a fresh export from the local dashboard.");
  for (const activity of data.activities) if (!activity || typeof activity !== "object" || typeof activity.date !== "string" || typeof activity.type !== "string") throw new Error("An activity row is missing its date or activity type.");
  return { schema_version: 1, activities: data.activities.filter((a) => !/treadmill/i.test(a.type)).map((a) => ({ date: a.date, type: a.type, distance_km: isNumber(a.distance_km) ? a.distance_km : null, duration_s: isNumber(a.duration_s) ? a.duration_s : null, elevation_m: isNumber(a.elevation_m) ? a.elevation_m : null, average_hr_bpm: isNumber(a.average_hr_bpm) ? a.average_hr_bpm : null })), health: data.health.filter((x) => x && typeof x.metric === "string").map((x) => ({ date: x.date, metric: x.metric, value: isNumber(x.value) ? x.value : null, unit: typeof x.unit === "string" ? x.unit : "" })) };
}
async function loadSample() { const response = await fetch(SAMPLE_URL); if (!response.ok) throw new Error("Synthetic sample data could not be loaded."); dataset = validateData(await response.json()); usingSample = true; updateSource(); renderPage("analytics"); renderSavedPlans(); }
function updateSource() { $("#data-source").textContent = usingSample ? "Synthetic sample" : "Your local export"; $(".state-dot").classList.toggle("loaded", !usingSample); }

document.addEventListener("DOMContentLoaded", async () => {
  $("#today-label").textContent = new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }).toUpperCase();
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => setPage(button.dataset.page)));
  const initialPage = ["analytics", "health", "plans"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "analytics";
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.page === initialPage));
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === `${initialPage}-page`));
  try { await loadSample(); setPage(initialPage); } catch (error) { $("#data-source").textContent = "Sample unavailable"; $("#analytics-metrics").textContent = error.message; }
  $("#data-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    try { dataset = validateData(JSON.parse(await file.text())); usingSample = false; updateSource(); renderPage("analytics"); renderSavedPlans(); toast("Your export is loaded in this browser tab."); }
    catch (error) { toast(error.message || "Could not read that JSON file."); }
    event.target.value = "";
  });
  $("#reset-sample").addEventListener("click", () => loadSample().then(() => toast("Synthetic sample data restored.")).catch((error) => toast(error.message)));
  $("#health-select").addEventListener("change", renderHealthTrend);
  $("#make-plan").addEventListener("click", makePlan); renderSavedPlans();
  $("#chat-launcher").addEventListener("click", () => { $("#chat-panel").hidden = !$("#chat-panel").hidden; if (!$("#chat-panel").hidden) $("#chat-input").focus(); });
  $("#chat-close").addEventListener("click", () => { $("#chat-panel").hidden = true; });
  $("#chat-form").addEventListener("submit", (event) => { event.preventDefault(); const input = $("#chat-input"); const question = input.value.trim(); if (!question || !dataset) return; addChat(question, "user"); input.value = ""; addChat(answerQuestion(question), "assistant"); });
});
