import { buildRunningWeeks, buildTrainingPlan, classifyTrainingQuestion, dashboardApiUrl, deriveRunBaseline, formatPace, normalizeChatResponse, normalizeDashboardData, parseFinishTime, parsePace, privateApiErrorMessage } from "./dashboard-logic.mjs";

const COLORS = { green: "#a7d9bd", green2: "#5eaa82", gold: "#e5ad78", blue: "#94b4cf", purple: "#b7a5d4", muted: "#9aa79e", line: "#344139", panel: "#1b2520" };
const SAMPLE_URL = "sample-data.json";
let dataset = null;
let usingSample = true;
let backendMode = false;
let chatHistory = [];
let previousIntent = null;

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
const isNumber = (value) => typeof value === "number" && Number.isFinite(value);
const average = (values) => { const valid = values.filter(isNumber); return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null; };
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

const getWeeks = buildRunningWeeks;

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
  const knownWeeks = completeWeeks.filter((week) => isNumber(week.distance));
  const avgWeek = average(knownWeeks.map((w) => w.distance));
  const estimated = runs.filter((a) => a.distance_km >= 2 && isNumber(a.duration_s)).map((a) => ({ date: a.date, seconds: a.duration_s * (5 / a.distance_km) ** 1.06 }));
  const values = [
    ["Outdoor run sessions", runs.length, "recorded activities"],
    ["Recorded run distance", knownDistance.length ? `${knownDistance.reduce((a, b) => a + b, 0).toFixed(1)} km` : "Unavailable", `${knownDistance.length} runs with distance`],
    ["Longest recorded run", knownDistance.length ? `${Math.max(...knownDistance).toFixed(1)} km` : "Unavailable", "distance where recorded"],
    ["Median run pace", fmtPace(medianPace), "median of run averages"],
    ["Avg per complete week", avgWeek === null ? "Unavailable" : `${avgWeek.toFixed(1)} km`, `${knownWeeks.length} complete weeks with known distance`],
  ];
  $("#analytics-metrics").innerHTML = values.map(([label, value, sub]) => `<div class="metric"><span class="metric-label">${esc(label)}</span><strong class="metric-value">${esc(value)}</strong><span class="metric-sub">${esc(sub)}</span></div>`).join("");
  const story = trainingStory(weeks, runs);
  $("#training-story .story-copy").textContent = story;
  $("#source-notice").textContent = dataSourceNote();
  $("#source-notice").classList.toggle("loaded", !usingSample);
  renderRunSuggestions(weeks, runs);

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
  const recentKeys = new Set(recent.map((week) => week.week)); const priorKeys = new Set(prior.map((week) => week.week));
  const weekKey = (activity) => { const day = asDate(activity.date); day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); return day.toISOString().slice(0, 10); };
  const meanRunDistance = (keys) => average(runs.filter((activity) => keys.has(weekKey(activity)) && isNumber(activity.distance_km)).map((activity) => activity.distance_km));
  const recentLength = meanRunDistance(recentKeys); const priorLength = meanRunDistance(priorKeys);
  const direction = change === null ? "" : change > 3 ? `up ${change}%` : change < -3 ? `down ${Math.abs(change)}%` : "about level";
  const recentWeekCount = recent.filter((week) => isNumber(week.distance)).length;
  const priorWeekCount = prior.filter((week) => isNumber(week.distance)).length;
  const volumeText = recentKm === null || priorKm === null
    ? "There are not enough complete weeks with known distance to compare running volume."
    : `Across the last four complete weeks, recorded volume averaged ${recentKm.toFixed(1)} km/week (${direction}) over ${recentWeekCount} weeks with known totals, versus ${priorKm.toFixed(1)} km/week over ${priorWeekCount} weeks in the previous block.`;
  const runDistanceText = recentLength === null || priorLength === null
    ? "Average distance per run is unavailable because some runs lack distance."
    : `Among runs with distance recorded, mean distance per run moved from ${priorLength.toFixed(1)} to ${recentLength.toFixed(1)} km.`;
  return `${volumeText} You logged ${recentRuns} runs versus ${priorRuns}; ${runDistanceText}`;
}
function currentWeekKey() { const day = new Date(); day.setHours(12, 0, 0, 0); day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); return day.toISOString().slice(0, 10); }

function renderRunSuggestions(weeks, runs) {
  const complete = weeks.filter((week) => week.week < currentWeekKey());
  const recent = complete.slice(-4); const previous = complete.slice(-8, -4);
  const recentKm = average(recent.map((week) => week.distance)); const previousKm = average(previous.map((week) => week.distance));
  let volumeAdvice = "Build consistency first: keep a repeatable weekly schedule before adding more distance.";
  if (recentKm !== null && previousKm !== null) {
    const change = previousKm ? Math.round((recentKm / previousKm - 1) * 100) : null;
    volumeAdvice = `Your last complete block averaged ${recentKm.toFixed(1)} km/week versus ${previousKm.toFixed(1)} km/week before it. ${change > 0 ? "If that increase felt comfortable, hold this level before adding more." : change < 0 ? "If that reduction was intentional, rebuild gradually when you feel recovered." : "A steady block gives you room to work on consistency."}`;
  }
  const matched = runs.filter((activity) => isNumber(activityPace(activity)) && isNumber(activity.average_hr_bpm));
  const hr = median(matched.map((activity) => activity.average_hr_bpm));
  $("#run-suggestions").innerHTML = [
    ["Keep easy days easy", "Use the talk test for most runs. If breathing or heart rate drifts up, slow down or add a short walk; don’t force your usual pace every day."],
    ["Progress volume patiently", volumeAdvice],
    ["Add speed with recovery", "If you already run consistently and feel rested, use one controlled tempo or interval workout in a week. Keep the other runs easy and leave a recovery day after hard efforts."],
  ].map(([title, body]) => `<div class="suggestion"><h3>${esc(title)}</h3><p>${esc(body)}</p></div>`).join("");
  if (hr === null && !usingSample) $("#run-suggestions").insertAdjacentHTML("beforeend", '<div class="suggestion"><h3>Track effort consistently</h3><p>Average run heart rate is missing for these records, so compare pace trends only until more heart-rate data is available.</p></div>');
}

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
  const sourceNote = dataSourceNote();
  $("#health-source-note").textContent = sourceNote;
  $("#health-source-note").classList.toggle("loaded", !usingSample);
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
  renderHealthSuggestions(health);
  const vo2 = health.filter((x) => /vo.?2\s*max/i.test(x.metric || "") && isNumber(x.value));
  $("#vo2-copy").textContent = vo2.length
    ? `${vo2.length} recorded VO₂ max value${vo2.length === 1 ? "" : "s"} are present; latest is ${vo2.at(-1).value.toFixed(1)} ${HEALTH_UNITS[vo2.at(-1).metric] || ""} on ${dateLabel(vo2.at(-1).date, { year: "numeric", month: "short", day: "numeric" })}.`
    : backendMode
      ? "No VO₂ max value is present in the Garmin records synced to this local database. The current Personal API sync does not return one, so this dashboard leaves it unavailable instead of estimating it."
      : "No VO₂ max reading is present in the loaded data. This dashboard does not estimate or invent one.";
}
function renderHealthSuggestions(health) {
  const cardMean = (metric, from, to, latestDate) => {
    const rows = health.filter((item) => item.metric === metric && isNumber(item.value));
    const end = asDate(latestDate);
    const values = rows.filter((item) => { const age = (end - asDate(item.date)) / 86400000; return age >= from && age < to; }).map((item) => item.value);
    return average(values);
  };
  const dates = health.filter((item) => item.metric !== "Average heart rate on runs" && item.date && isNumber(item.value)).map((item) => dateOnly(item.date)).sort();
  let first = ["Use trends, not one-day changes", "Compare sleep, resting heart rate, and HRV across several days. A single reading is not enough to change a training plan."];
  if (dates.length) {
    const latest = dates.at(-1);
    const sleepRecent = cardMean("Sleep duration", 0, 7, latest); const sleepPrior = cardMean("Sleep duration", 7, 14, latest);
    const rhrRecent = cardMean("Resting heart rate", 0, 7, latest); const rhrPrior = cardMean("Resting heart rate", 7, 14, latest);
    if (sleepRecent !== null && sleepPrior !== null && rhrRecent !== null && rhrPrior !== null) {
      const sleepDelta = sleepRecent - sleepPrior; const rhrDelta = rhrRecent - rhrPrior;
      if (sleepDelta <= -0.5 && rhrDelta >= 2) first = ["Give recovery some room", `Recent sleep averaged ${Math.abs(sleepDelta).toFixed(1)} hours less while resting heart rate was ${rhrDelta.toFixed(0)} bpm higher than the previous week. Consider making the next hard session easy if you also feel unusually tired; recheck the trend over several days.`];
      else first = ["Recovery signals are mixed", `Sleep changed ${sleepDelta >= 0 ? "+" : ""}${sleepDelta.toFixed(1)} hours and resting heart rate changed ${rhrDelta >= 0 ? "+" : ""}${rhrDelta.toFixed(0)} bpm versus the previous week. Keep your routine steady and watch whether the pattern continues.`];
    }
  }
  const hrCount = (dataset.activities || []).filter((activity) => running(activity) && isNumber(activity.average_hr_bpm)).length;
  const sourceLine = usingSample ? "These example suggestions use synthetic data." : "These checks use the measurements in your local export.";
  $("#health-suggestions").innerHTML = [
    first,
    ["Check run effort under similar conditions", hrCount ? `${hrCount} runs include average heart rate. Compare similar easy routes and weather; heat, hills, hydration, and sensor fit can shift the number.` : "No outdoor run has average heart rate in this export. Sync more activity detail before comparing run effort."],
  ].map(([title, body]) => `<div class="suggestion"><h3>${esc(title)}</h3><p>${esc(body)}</p></div>`).join("") + `<p class="chart-note">${esc(sourceLine)}</p>`;
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

let currentPlan = null;
function makePlan() {
  const error = $("#plan-error"); error.hidden = true; error.textContent = "";
  const goal = $("#plan-goal").value;
  const eventDate = $("#plan-event-date").value || null;
  const startDate = nextPlanMonday();
  let durationWeeks = Number($("#plan-weeks").value);
  if (eventDate) {
    const race = new Date(`${eventDate}T00:00:00`); const start = new Date(`${startDate}T00:00:00`);
    const daysUntilRace = Math.floor((race - start) / 86400000);
    if (daysUntilRace < 0) { error.textContent = "Choose a race date on or after the next plan start date."; error.hidden = false; return; }
    durationWeeks = Math.floor(daysUntilRace / 7) + 1;
  }
  const baselinePace = parsePace($("#plan-pace").value);
  const targetFinishSeconds = parseFinishTime($("#plan-finish-time").value);
  const isRaceGoal = ["5k", "10k", "half"].includes(goal);
  if (isRaceGoal && $("#plan-finish-time").value.trim() && !targetFinishSeconds) {
    error.textContent = "Enter a finish time as mm:ss or hh:mm:ss."; error.hidden = false; return;
  }
  try {
    currentPlan = buildTrainingPlan({
      goal,
      weeklySessions: Number($("#plan-sessions").value),
      availableDays: [...document.querySelectorAll(".day-options input:checked")].map((input) => input.value),
      longRunDay: $("#plan-long-day").value,
      durationWeeks,
      weeklyDistanceKm: Number($("#plan-weekly-km").value),
      medianPaceMinKm: baselinePace,
      targetFinishSeconds: isRaceGoal && $("#plan-finish-time").value.trim() ? targetFinishSeconds : null,
      eventDate,
      startDate,
    });
  } catch (reason) {
    error.textContent = reason.message || "Check the plan settings and try again."; error.hidden = false; return;
  }
  renderPlan(currentPlan); $("#plan-result").hidden = false;
}
function nextPlanMonday(now = new Date()) {
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  monday.setDate(monday.getDate() + ((8 - monday.getDay()) % 7));
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
}
function populatePlanInputs() {
  const baseline = deriveRunBaseline(dataset?.activities || []);
  if (Number.isFinite(baseline.weeklyDistanceKm) && baseline.weeklyDistanceKm > 0) $("#plan-weekly-km").value = String(Math.round(baseline.weeklyDistanceKm * 2) / 2);
  else $("#plan-weekly-km").value = "";
  if (Number.isFinite(baseline.medianPaceMinKm) && baseline.medianPaceMinKm > 0) $("#plan-pace").value = formatPace(baseline.medianPaceMinKm).replace("/km", "");
  else $("#plan-pace").value = "";
  updateGoalFields();
}
function updateGoalFields() {
  const goal = $("#plan-goal").value;
  const raceGoal = ["5k", "10k", "half"].includes(goal);
  const finishField = $("#plan-finish-time").closest("label");
  const raceDateField = $("#plan-event-date-field");
  finishField.hidden = !raceGoal;
  raceDateField.hidden = !raceGoal;
  if (!raceGoal) $("#plan-event-date").value = "";
  $("#plan-weeks").disabled = Boolean($("#plan-event-date").value);
}
function renderPlan(plan) {
  const endLine = plan.eventDate ? ` · race day ${esc(plan.eventDate)}` : ` · starts ${esc(plan.weeks[0]?.starting || "")}`;
  $("#plan-result").innerHTML = `<div class="plan-result-head"><div><p class="eyebrow">YOUR PERSONAL TRAINING BLOCK</p><h3>${esc(plan.title)}</h3><p>${plan.durationWeeks} weeks · ${plan.weeklySessions} sessions/week · long run ${esc(plan.longRunDay)} · ${plan.baselineWeeklyKm.toFixed(1)} km/week starting volume${endLine}</p><p class="pace-note">${esc(plan.paceNote)}</p></div><button class="button primary" id="save-plan">Save this plan</button></div><div class="week-list">${plan.weeks.map((week) => `<section class="week-card"><div class="week-card-head"><b>WEEK ${week.week}</b><span>${week.totalDistanceKm.toFixed(1)} km</span></div><time>${esc(week.starting)} · ${week.sessions.length} sessions</time><p>${esc(week.focus)}</p><div class="workout-list">${week.sessions.map((session) => `<article><b>${esc(session.day)} · ${esc(session.title)}</b><span>${session.distanceKm.toFixed(1)} km · ${esc(session.paceTarget)}</span><small>${esc(session.details)}</small></article>`).join("")}</div></section>`).join("")}</div>`;
  $("#save-plan").addEventListener("click", () => { const saved = readPlans(); saved.unshift(plan); localStorage.setItem("training-lab-plans", JSON.stringify(saved.slice(0, 20))); renderSavedPlans(); toast("Plan saved in this browser."); });
}
function readPlans() { try { const plans = JSON.parse(localStorage.getItem("training-lab-plans") || "[]"); return Array.isArray(plans) ? plans : []; } catch { return []; } }
function renderSavedPlans() {
  const plans = readPlans();
  $("#saved-plans").innerHTML = plans.length ? plans.map((plan) => `<article class="saved-card"><time>${esc(new Date(plan.createdAt).toLocaleDateString())}</time><h3>${esc(plan.title)}</h3><p>${plan.durationWeeks ?? plan.weeks?.length ?? "—"} weeks · ${plan.weeklySessions ?? plan.weeks?.[0]?.sessions ?? "—"} sessions per week${Number.isFinite(plan.baselineWeeklyKm) ? ` · starting at ${plan.baselineWeeklyKm.toFixed(1)} km/week` : ""}</p><button data-delete-plan="${Number(plan.id)}">Delete plan</button></article>`).join("") : '<p class="empty-saved">No plans saved on this device yet.</p>';
  document.querySelectorAll("[data-delete-plan]").forEach((button) => button.addEventListener("click", () => { localStorage.setItem("training-lab-plans", JSON.stringify(readPlans().filter((plan) => plan.id !== Number(button.dataset.deletePlan)))); renderSavedPlans(); }));
}

function answerQuestion(question) {
  const q = question.toLowerCase();
  const intent = classifyTrainingQuestion(question, previousIntent);
  if (intent !== "follow_up") previousIntent = intent;
  const activities = dataset.activities || [];
  const runs = activities.filter(running);
  const weeks = getWeeks(activities);
  const health = dataset.health || [];
  const sourceNote = usingSample ? "You’re currently viewing the synthetic demo, not your Garmin history. Load your Garmin export to personalize this. " : "";

  if (intent === "follow_up") {
    if (previousIntent === "heart_rate_pace_goal") return `${sourceNote}I mean: don't try to run faster on every run. Keep most runs easy enough to speak in full sentences; slow down or take a short walk if your heart rate drifts up. Build easy running consistently, then use one controlled faster workout a week if you are recovering well.`;
    return "I only have local, rule-based answers here. Try asking a complete question about one metric or goal, such as “compare my recent run pace and heart rate.”";
  }

  if (intent === "heart_rate_pace_goal" || intent === "heart_rate_pace") {
    const matched = runs.filter((activity) => isNumber(activityPace(activity)) && isNumber(activity.average_hr_bpm));
    const medianPace = median(matched.map(activityPace));
    const medianHr = median(matched.map((activity) => activity.average_hr_bpm));
    const comparison = compareRecentRunEffort(runs, weeks);
    const baseline = matched.length
      ? `${matched.length} outdoor runs with both measures have an overall median of ${fmtPace(medianPace)} and ${medianHr.toFixed(0)} bpm.`
      : "There are not enough outdoor runs with both pace and average heart rate to calculate a baseline.";
    return `${sourceNote}${comparison || baseline} These are mixed workouts, not a controlled comparison. To move both in the right direction: 1) Run most sessions at conversational effort and let pace be slower when needed. 2) Build easy weekly distance gradually, only while recovery is good. 3) If you run regularly and feel recovered, add one controlled tempo or interval session per week; keep other runs easy. 4) Compare similar routes and weather, since heat, hills, sleep, hydration, and wrist-sensor fit can shift heart rate.`;
  }

  if (intent === "visualize") {
    const metric = [...new Set(health.map((x) => x.metric).filter(Boolean))].find((name) => q.includes(name.toLowerCase()));
    if (metric) { setPage("health"); $("#health-select").value = metric; renderHealthTrend(); return `Opened the ${metric} trend in Health using the data currently loaded in this tab.`; }
    if (/weekly.*(run|distance)|running.*distance/.test(q)) { setPage("analytics"); return "The weekly running distance chart is shown on Analytics, with a four-week mean."; }
    if (/pace/.test(q)) { setPage("analytics"); return "The run pace chart is shown on Analytics, with pace labeled in min:sec per kilometer."; }
    if (/activity|sport|strength/.test(q)) { setPage("analytics"); return "The activity mix chart is shown on Analytics. It includes tracked non-treadmill activities."; }
    return "I can open a health metric by name, or show the weekly distance, pace, and activity mix charts. Which would you like?";
  }
  if (intent === "vo2") { const values = health.filter((x) => /vo.?2\s*max/i.test(x.metric || "") && isNumber(x.value)); return values.length ? `${sourceNote}The latest recorded VO₂ max is ${values.at(-1).value.toFixed(1)} on ${dateLabel(values.at(-1).date)}.` : `${sourceNote}There is no recorded VO₂ max value in the loaded data, so I can’t evaluate its trend or suggest a data-based target.`; }
  if (intent === "recovery") { const name = /score/.test(q) ? "Sleep score" : /hrv/.test(q) ? "Nightly HRV" : /resting|rhr/.test(q) ? "Resting heart rate" : "Sleep duration"; const rows = health.filter((x) => x.metric === name && isNumber(x.value)); return rows.length ? `${sourceNote}The latest ${name.toLowerCase()} is ${formatHealth(rows.at(-1).value, name)} on ${dateLabel(rows.at(-1).date)}. I can show its dated trend on the Health tab.` : `${sourceNote}${name} is not present in the loaded data. Missing data stays unavailable.`; }
  if (intent === "heart_rate") { const rows = runs.filter((a) => isNumber(a.average_hr_bpm)); return rows.length ? `${sourceNote}Across ${rows.length} outdoor runs with average heart rate, the median recorded value is ${median(rows.map((a) => a.average_hr_bpm)).toFixed(0)} bpm. Compare similar routes and paces before reading this as a fitness change.` : `${sourceNote}There are no outdoor runs with recorded average heart rate in this data.`; }
  if (intent === "pace") { const paces = runs.map(activityPace).filter(isNumber); return paces.length ? `${sourceNote}Your median recorded outdoor-run pace is ${fmtPace(median(paces))} across ${paces.length} runs with distance and duration. That is the middle of your run averages, not a race target.` : `${sourceNote}There are no runs with both distance and duration available.`; }
  if (intent === "distance") { const valid = weeks.filter((w) => w.week < currentWeekKey()); const recent = valid.slice(-4); const known = recent.filter((week) => isNumber(week.distance)); return known.length ? `${sourceNote}Across the last ${known.length} complete weeks with known distance, average outdoor running volume was ${average(known.map((w) => w.distance)).toFixed(1)} km/week. ${recent.reduce((n, w) => n + w.runs, 0)} run sessions were recorded in the last four complete weeks.` : `${sourceNote}There are not enough complete weeks with known distance to summarize running volume.`; }
  if (intent === "activity_mix") { const types = new Map(); activities.filter((a) => !/treadmill/i.test(a.type || "")).forEach((a) => types.set(prettifyType(a.type), (types.get(prettifyType(a.type)) || 0) + 1)); return types.size ? `${sourceNote}Your visible activity mix is ${[...types.entries()].map(([type, count]) => `${type}: ${count}`).join("; ")}. Treadmill runs are excluded.` : `${sourceNote}No activities are in this data.`; }
  return "I can summarize running distance, pace, heart rate, sleep, recovery, activity mix, or VO₂ max availability. I can also explain ways to improve run pace and heart rate. Try a complete question about one of those.";
}

function compareRecentRunEffort(runs, weeks) {
  const complete = weeks.filter((week) => week.week < currentWeekKey());
  if (complete.length < 8) return null;
  const recent = complete.slice(-4); const prior = complete.slice(-8, -4);
  const keysFor = (block) => new Set(block.map((week) => week.week));
  const keyFor = (activity) => { const day = asDate(activity.date); day.setDate(day.getDate() - ((day.getDay() + 6) % 7)); return day.toISOString().slice(0, 10); };
  const summary = (keys) => {
    const paired = runs.filter((activity) => keys.has(keyFor(activity)) && isNumber(activityPace(activity)) && isNumber(activity.average_hr_bpm));
    return { count: paired.length, pace: median(paired.map(activityPace)), hr: median(paired.map((activity) => activity.average_hr_bpm)) };
  };
  const current = summary(keysFor(recent)); const previous = summary(keysFor(prior));
  if (current.count < 2 || previous.count < 2) return null;
  const paceDelta = Math.round((current.pace - previous.pace) * 60);
  const paceText = paceDelta < 0 ? `${Math.abs(paceDelta)} sec/km faster` : paceDelta > 0 ? `${paceDelta} sec/km slower` : "at the same median pace";
  return `In the last four complete weeks, ${current.count} runs with both measures had median pace ${fmtPace(current.pace)} and median average HR ${current.hr.toFixed(0)} bpm. In the previous four-week block, ${previous.count} comparable records were ${fmtPace(previous.pace)} and ${previous.hr.toFixed(0)} bpm (${paceText}).`;
}
function addChat(text, who) { const node = document.createElement("div"); node.className = `chat-bubble ${who}`; node.textContent = text; $("#chat-messages").append(node); $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight; }
function toast(message) { const node = $("#toast"); node.textContent = message; node.classList.add("show"); setTimeout(() => node.classList.remove("show"), 2200); }

function renderPage(name) { if (name === "analytics") renderAnalytics(); if (name === "health") renderHealth(); if (name === "plans") renderSavedPlans(); }
function validateData(data) {
  try { return normalizeDashboardData(data); }
  catch (error) { throw new Error(`This is not a supported Training Lab export: ${error.message}`); }
}
async function loadSample() { const response = await fetch(SAMPLE_URL); if (!response.ok) throw new Error("Synthetic sample data could not be loaded."); dataset = validateData(await response.json()); usingSample = true; backendMode = false; $("#sync-data").hidden = true; updateSource(); renderPage("analytics"); renderSavedPlans(); }
async function loadBackendData() {
  const response = await fetch(dashboardApiUrl("dashboard-data"), { headers: { Accept: "application/json" } });
  if (!response.ok) return false;
  const payload = validateData(await response.json());
  if (payload.source !== "garmin_sqlite") return false;
  dataset = payload; usingSample = false; backendMode = true; $("#sync-data").hidden = false;
  updateSource(); renderPage("analytics"); renderSavedPlans();
  return true;
}
function dateRangeLabel() {
  const range = dataset?.metadata?.date_range;
  if (!range?.start || !range?.end) return "no dated activities";
  return range.start === range.end ? `through ${range.end}` : `${range.start} to ${range.end}`;
}
function wellnessRangeLabel() {
  const range = dataset?.metadata?.wellness_date_range;
  if (!range?.start || !range?.end) return "no wellness date range";
  return range.start === range.end ? `on ${range.end}` : `${range.start} to ${range.end}`;
}
function dataSourceNote() {
  if (usingSample) return "Synthetic sample data is showing—not your Garmin history. Use “Load my Garmin export” to view the records saved from your Garmin sync.";
  if (backendMode) return `Garmin Connect Personal API records, read from the local SQLite database. ${dataset.metadata?.activity_count ?? 0} activities (${dateRangeLabel()}); ${dataset.metadata?.wellness_point_count ?? 0} wellness readings (${wellnessRangeLabel()}).`;
  return "Using a Garmin export uploaded into this browser tab. This is the last data saved from Garmin, not a live connection.";
}
function updateSource() {
  const label = usingSample ? "Synthetic sample" : backendMode ? "Your Garmin API data · local DB" : "Your Garmin export";
  $("#data-source").textContent = label;
  $("#data-source-top").textContent = usingSample ? "SYNTHETIC SAMPLE" : backendMode ? `GARMIN API DATA · ${dateRangeLabel()}` : "GARMIN EXPORT · BROWSER";
  $(".state-dot").classList.toggle("loaded", !usingSample);
  $(".chat-welcome").textContent = usingSample
    ? "This page is using synthetic sample data. Load your Garmin export to ask about your own metrics."
    : backendMode ? "Your synced Garmin activity and health data is loaded. Ask a question or request a chart."
      : "Your Garmin export is loaded in this tab. Ask about your metrics.";
  $(".chat-foot").textContent = backendMode
    ? "OpenAI receives your question and a compact summary of this data. The API key and Garmin database stay on this Mac."
    : usingSample ? "Demo answers use synthetic sample data and local rules. The public GitHub Pages site cannot access your .env key."
      : "This uploaded export stays in this browser tab. Answers use local rules and are not sent to OpenAI.";
}

async function sendBackendChat(question) {
  const history = chatHistory.slice(-8);
  chatHistory.push({ role: "user", content: question });
  const response = await fetch(dashboardApiUrl("chat"), {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ question, history }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail || privateApiErrorMessage(response.status));
  const result = normalizeChatResponse(payload);
  chatHistory.push({ role: "assistant", content: result.answer });
  addChat(result.answer, "assistant");
  if (result.chart) addChatChart(result.chart);
}
function addChatChart(chart) {
  if (!window.Plotly || !chart.rows.length) return;
  const card = document.createElement("div"); card.className = "chat-chart-card";
  const title = document.createElement("p"); title.className = "eyebrow"; title.textContent = `${chart.metric} · ${chart.unit}`;
  const plot = document.createElement("div"); plot.className = "chat-chart";
  card.append(title, plot); $("#chat-messages").append(card);
  const trace = chart.chart_type === "bar"
    ? { type: "bar", x: chart.rows.map((row) => row.x), y: chart.rows.map((row) => row.value), marker: { color: COLORS.green2 } }
    : { type: "scatter", x: chart.rows.map((row) => row.x), y: chart.rows.map((row) => row.value), mode: "lines+markers", line: { color: COLORS.green, width: 2 } };
  window.Plotly.newPlot(plot, [trace], {
    paper_bgcolor: "#17211c", plot_bgcolor: "#17211c", font: { color: "#dce6df", size: 10 },
    margin: { l: 42, r: 8, t: 8, b: 42 }, xaxis: { gridcolor: "#2b3830", automargin: true },
    yaxis: { gridcolor: "#2b3830", rangemode: "tozero", automargin: true }, showlegend: false,
  }, { displayModeBar: false, responsive: true });
  $("#chat-messages").scrollTop = $("#chat-messages").scrollHeight;
}
async function syncGarmin() {
  const button = $("#sync-data"); button.disabled = true; button.textContent = "Syncing…";
  try {
    const response = await fetch(dashboardApiUrl("sync"), { method: "POST", headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `Sync failed (HTTP ${response.status}).`);
    await loadBackendData();
    const a = payload.activities; const w = payload.wellness;
    toast(`Sync: ${a.imported} activity changes; ${w.imported} wellness updates; ${a.failed + w.failed} failures.`);
  } catch (error) { toast(error.message || "Garmin sync failed."); }
  finally { button.disabled = false; button.textContent = "Sync Garmin"; }
}

document.addEventListener("DOMContentLoaded", async () => {
  $("#today-label").textContent = new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }).toUpperCase();
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => setPage(button.dataset.page)));
  const initialPage = ["analytics", "health", "plans"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "analytics";
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.page === initialPage));
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === `${initialPage}-page`));
  try { if (!await loadBackendData()) await loadSample(); setPage(initialPage); populatePlanInputs(); } catch (error) { $("#data-source").textContent = "Sample unavailable"; $("#analytics-metrics").textContent = error.message; }
  $("#data-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    try { dataset = validateData(JSON.parse(await file.text())); usingSample = false; backendMode = false; $("#sync-data").hidden = true; updateSource(); renderPage("analytics"); renderSavedPlans(); toast("Your export is loaded in this browser tab."); }
    catch (error) { toast(error.message || "Could not read that JSON file."); }
    event.target.value = "";
  });
  $("#reset-sample").addEventListener("click", () => loadSample().then(() => toast("Synthetic sample data restored.")).catch((error) => toast(error.message)));
  $("#sync-data").addEventListener("click", syncGarmin);
  $("#health-select").addEventListener("change", renderHealthTrend);
  $("#make-plan").addEventListener("click", makePlan);
  $("#plan-goal").addEventListener("change", updateGoalFields);
  $("#plan-event-date").addEventListener("change", updateGoalFields);
  renderSavedPlans();
  $("#chat-launcher").addEventListener("click", () => { $("#chat-panel").hidden = !$("#chat-panel").hidden; if (!$("#chat-panel").hidden) $("#chat-input").focus(); });
  $("#chat-close").addEventListener("click", () => { $("#chat-panel").hidden = true; });
  $("#chat-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const input = $("#chat-input"); const question = input.value.trim(); if (!question || !dataset) return;
    addChat(question, "user"); input.value = "";
    if (backendMode) {
      const button = $("#chat-form button"); button.disabled = true;
      try { await sendBackendChat(question); }
      catch (error) { const message = error.message || "OpenAI chat is unavailable."; addChat(message, "assistant"); chatHistory.push({ role: "assistant", content: message }); }
      finally { button.disabled = false; }
    } else addChat(answerQuestion(question), "assistant");
  });
});
