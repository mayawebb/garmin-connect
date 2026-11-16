const isNumber = (value) => typeof value === "number" && Number.isFinite(value);
const isRun = (activity) => /run/i.test(activity.type || "") && !/treadmill/i.test(activity.type || "");

export function normalizeDashboardData(data) {
  if (!data || data.schema_version !== 1 || !Array.isArray(data.activities) || !Array.isArray(data.health)) {
    throw new Error("Unsupported dashboard data. Load a schema version 1 Garmin export.");
  }
  const activities = data.activities.filter((activity) => activity && typeof activity === "object" && typeof activity.date === "string" && typeof activity.type === "string");
  if (activities.length !== data.activities.length) throw new Error("An activity row is missing its date or activity type.");
  return {
    schema_version: 1,
    source: typeof data.source === "string" ? data.source : null,
    metadata: data.metadata && typeof data.metadata === "object" ? data.metadata : null,
    activities: activities.filter((activity) => !/treadmill/i.test(activity.type)).map((activity) => ({
      date: activity.date,
      type: activity.type,
      distance_km: isNumber(activity.distance_km) ? activity.distance_km : null,
      duration_s: isNumber(activity.duration_s) ? activity.duration_s : null,
      elevation_m: isNumber(activity.elevation_m) ? activity.elevation_m : null,
      average_hr_bpm: isNumber(activity.average_hr_bpm) ? activity.average_hr_bpm : null,
    })),
    health: data.health.filter((item) => item && typeof item.metric === "string").map((item) => ({
      date: typeof item.date === "string" ? item.date : null,
      metric: item.metric,
      value: isNumber(item.value) ? item.value : null,
      unit: typeof item.unit === "string" ? item.unit : "",
    })),
  };
}

export function normalizeChatResponse(payload) {
  if (!payload || typeof payload.answer !== "string") throw new Error("Chat returned an invalid response.");
  if (payload.chart == null) return { answer: payload.answer, chart: null };
  const chart = payload.chart;
  const groups = new Set(["week", "month", "activity_type", "none"]);
  if (!chart || typeof chart.metric !== "string" || !["line", "bar"].includes(chart.chart_type) || !groups.has(chart.group_by) || !Array.isArray(chart.rows)) {
    throw new Error("Chat returned an invalid chart.");
  }
  const rows = chart.rows.map((row) => {
    if (!row || typeof row.x !== "string" || !isNumber(row.value)) throw new Error("Chat returned invalid chart data.");
    return { x: row.x, value: row.value };
  });
  return { answer: payload.answer, chart: { metric: chart.metric, chart_type: chart.chart_type, group_by: chart.group_by, unit: String(chart.unit || ""), rows } };
}

export function dashboardApiUrl(route, pageUrl = globalThis.location?.href) {
  if (!pageUrl) throw new Error("A page URL is required to build a dashboard API URL.");
  const path = String(route || "").replace(/^\/+/, "");
  return new URL(`api/${path}`, pageUrl).pathname;
}

export function privateApiErrorMessage(status) {
  if (status === 401) return "Your private dashboard sign-in has expired or was not completed. Open the dashboard link, sign in with your allowed email and PIN, then retry. The chat request did not reach OpenAI.";
  return `Chat request failed (HTTP ${status}).`;
}

const PLAN_GOALS = {
  "5k": { label: "5K", distanceKm: 5, race: true },
  "10k": { label: "10K", distanceKm: 10, race: true },
  half: { label: "Half marathon", distanceKm: 21.0975, race: true },
  lower_hr: { label: "Lower heart rate at a comfortable pace", race: false },
  distance: { label: "Build weekly running distance", race: false },
};
const PLAN_DAYS = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
const DAY_ORDER = Object.keys(PLAN_DAYS);
const DAY_INDEX = Object.fromEntries(DAY_ORDER.map((day, index) => [day, index]));

export function formatPace(minPerKm) {
  if (!isNumber(minPerKm) || minPerKm <= 0) return "—";
  const totalSeconds = Math.round(minPerKm * 60);
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}/km`;
}

export function parsePace(value) {
  const text = String(value || "").trim();
  const match = /^(\d{1,2}):([0-5]\d)$/.exec(text);
  if (!match) return null;
  const pace = Number(match[1]) + Number(match[2]) / 60;
  return pace >= 3 && pace <= 15 ? pace : null;
}

export function parseFinishTime(value) {
  const text = String(value || "").trim();
  const parts = text.split(":");
  if (parts.length < 2 || parts.length > 3 || parts.some((part) => !/^\d+$/.test(part))) return null;
  const numbers = parts.map(Number);
  if (numbers.at(-1) > 59 || (parts.length === 3 && numbers[1] > 59)) return null;
  const seconds = parts.length === 2 ? numbers[0] * 60 + numbers[1] : numbers[0] * 3600 + numbers[1] * 60 + numbers[2];
  return seconds > 0 ? seconds : null;
}

export function deriveRunBaseline(activities, now = new Date()) {
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const currentMonday = new Date(today);
  currentMonday.setUTCDate(currentMonday.getUTCDate() - ((currentMonday.getUTCDay() + 6) % 7));
  const recentWeeks = Array.from({ length: 4 }, (_, index) => {
    const start = new Date(currentMonday);
    start.setUTCDate(start.getUTCDate() - 7 * (4 - index));
    const key = start.toISOString().slice(0, 10);
    return { key, distance: 0, hasRun: false, unknownDistance: false };
  });
  const weekMap = new Map(recentWeeks.map((week) => [week.key, week]));
  const paces = [];
  let recordedRuns = 0;
  for (const activity of activities || []) {
    if (!isRun(activity)) continue;
    const key = weekStart(activity.date);
    const week = weekMap.get(key);
    if (!week) continue;
    recordedRuns += 1;
    week.hasRun = true;
    if (isNumber(activity.distance_km) && activity.distance_km > 0) week.distance += activity.distance_km;
    else week.unknownDistance = true;
    if (isNumber(activity.distance_km) && activity.distance_km > 0 && isNumber(activity.duration_s) && activity.duration_s > 0) {
      paces.push(activity.duration_s / 60 / activity.distance_km);
    }
  }
  const distances = recentWeeks.filter((week) => !week.unknownDistance).map((week) => week.distance);
  const weeklyDistanceKm = distances.length ? distances.reduce((sum, value) => sum + value, 0) / distances.length : null;
  return {
    weeklyDistanceKm,
    medianPaceMinKm: paces.length ? median(paces) : null,
    recordedRuns,
    weeksIncluded: distances.length,
  };
}

export function buildTrainingPlan(options) {
  const goal = PLAN_GOALS[options?.goal];
  const weeklySessions = Number(options?.weeklySessions);
  const durationWeeks = Number(options?.durationWeeks);
  const weeklyDistanceKm = Number(options?.weeklyDistanceKm);
  const medianPaceMinKm = Number(options?.medianPaceMinKm);
  const targetFinishSeconds = options?.targetFinishSeconds == null ? null : Number(options.targetFinishSeconds);
  if (!goal) throw new Error("Choose a supported training goal.");
  if (!Number.isInteger(weeklySessions) || weeklySessions < 2 || weeklySessions > 5) throw new Error("Choose 2 to 5 run sessions per week.");
  if (!Number.isInteger(durationWeeks) || durationWeeks < 4 || durationWeeks > 24) throw new Error("Choose a plan length from 4 to 24 weeks.");
  if (!isNumber(weeklyDistanceKm) || weeklyDistanceKm < 1 || weeklyDistanceKm > 200) throw new Error("Enter your current weekly running distance in kilometers.");
  if (weeklyDistanceKm < weeklySessions * 1.5) throw new Error("This weekly distance is low for that many run sessions. Reduce the session count or enter a higher current weekly distance.");
  if (!isNumber(medianPaceMinKm) || medianPaceMinKm < 3 || medianPaceMinKm > 15) throw new Error("Enter your recent median run pace as min:sec per kilometer.");
  if (targetFinishSeconds !== null && (!goal.race || !isNumber(targetFinishSeconds) || targetFinishSeconds <= 0)) throw new Error("Enter a valid optional finish time for your selected race distance.");
  const availableDays = [...new Set((options?.availableDays || []).filter((day) => DAY_ORDER.includes(day)))].sort((a, b) => DAY_INDEX[a] - DAY_INDEX[b]);
  if (availableDays.length < weeklySessions) throw new Error("Select at least as many available days as your requested weekly sessions.");
  const longRunDay = options?.longRunDay;
  if (!availableDays.includes(longRunDay)) throw new Error("Choose your long-run day from your available training days.");
  const startText = String(options?.startDate || new Date().toISOString().slice(0, 10)).slice(0, 10);
  const start = new Date(`${startText}T00:00:00Z`);
  if (!Number.isFinite(start.getTime())) throw new Error("Choose a valid plan start date.");
  start.setUTCDate(start.getUTCDate() + ((8 - start.getUTCDay()) % 7));
  const raceDate = options?.eventDate ? new Date(`${String(options.eventDate).slice(0, 10)}T00:00:00Z`) : null;
  if (raceDate && (!goal.race || !Number.isFinite(raceDate.getTime()) || raceDate < start || Math.floor((raceDate - start) / 604800000) !== durationWeeks - 1)) {
    throw new Error("Set the race date within the final week of this plan.");
  }
  const goalPaceMinKm = targetFinishSeconds && goal.distanceKm ? targetFinishSeconds / 60 / goal.distanceKm : null;
  if (goalPaceMinKm && (goalPaceMinKm < 3 || goalPaceMinKm > 15)) throw new Error("That finish time implies an unsupported race pace; check the time and distance.");
  const targets = [
    { key: "easy", title: "Easy aerobic run", type: "easy" },
    { key: "quality", title: "Controlled quality session", type: "quality" },
    { key: "easy2", title: "Easy aerobic run", type: "easy" },
    { key: "tempo", title: "Steady tempo session", type: "tempo" },
    { key: "long", title: "Long easy run", type: "long" },
  ];
  let sessionTypes;
  if (weeklySessions === 2) sessionTypes = [targets[0], targets[4]];
  else if (weeklySessions === 3) sessionTypes = options.goal === "lower_hr" ? [targets[0], targets[2], targets[4]] : [targets[0], targets[1], targets[4]];
  else if (weeklySessions === 4) sessionTypes = [targets[0], targets[1], targets[2], targets[4]];
  else sessionTypes = targets;
  if (options.goal === "lower_hr") sessionTypes = sessionTypes.map((session) => session.type === "quality" || session.type === "tempo" ? { ...session, type: "easy", title: "Easy aerobic run" } : session);
  const chosenDays = selectTrainingDays(availableDays, weeklySessions, longRunDay);
  const orderedTypes = [...sessionTypes.filter((session) => session.type !== "long"), sessionTypes.find((session) => session.type === "long")];
  let peakDistance = weeklyDistanceKm;
  let previousDistance = weeklyDistanceKm;
  const weeks = [];
  for (let index = 0; index < durationWeeks; index += 1) {
    let totalDistance = weeklyDistanceKm;
    let focus = "Build steadily while keeping easy running comfortable.";
    if (index > 0) {
      const position = index % 4;
      if (position === 0) { totalDistance = peakDistance * 0.95; focus = "Return from the lighter week and resume gradually."; }
      else if (position === 3) { totalDistance = peakDistance * 0.88; focus = "Lighter recovery week: keep the sessions easy and absorb the training."; }
      else { totalDistance = previousDistance * 1.05; focus = position === 2 ? "Highest-volume week of this build block; keep the harder session controlled." : "Small volume increase; prioritize the easy pace range."; }
      if (position === 2) peakDistance = totalDistance;
      previousDistance = totalDistance;
    }
    const isRaceGoal = goal.race;
    if (isRaceGoal && index === durationWeeks - 1 && durationWeeks >= 6) {
      totalDistance = previousDistance * 0.75;
      focus = `Taper week${options.eventDate ? ` before ${options.eventDate}` : ""}: reduce volume and arrive rested.`;
    }
    totalDistance = Math.max(weeklySessions * 1.5, Math.round(totalDistance * 10) / 10);
    const distributions = {
      2: [0.4, 0.6],
      3: [0.3, 0.32, 0.38],
      4: [0.22, 0.24, 0.2, 0.34],
      5: [0.18, 0.2, 0.17, 0.2, 0.25],
    }[weeklySessions];
    const sessionDistances = distributions.map((share) => Math.max(1, Math.round(totalDistance * share * 10) / 10));
    const adjustment = Math.round((totalDistance - sessionDistances.reduce((sum, value) => sum + value, 0)) * 10) / 10;
    sessionDistances[sessionDistances.length - 1] = Math.max(1, Math.round((sessionDistances.at(-1) + adjustment) * 10) / 10);
    const weekStartDate = new Date(start);
    weekStartDate.setUTCDate(weekStartDate.getUTCDate() + index * 7);
    const nonLongDays = chosenDays.filter((day) => day !== longRunDay).sort((a, b) => DAY_INDEX[a] - DAY_INDEX[b]);
    let sessions = orderedTypes.map((session, sessionIndex) => {
      let paceLow; let paceHigh;
      if (session.type === "quality") {
        paceLow = goalPaceMinKm ? goalPaceMinKm - 5 / 60 : medianPaceMinKm - 20 / 60;
        paceHigh = goalPaceMinKm ? goalPaceMinKm + 10 / 60 : medianPaceMinKm - 5 / 60;
      }
      else if (session.type === "tempo") {
        paceLow = goalPaceMinKm ? goalPaceMinKm + 10 / 60 : medianPaceMinKm - 5 / 60;
        paceHigh = goalPaceMinKm ? goalPaceMinKm + 25 / 60 : medianPaceMinKm + 15 / 60;
      }
      else { paceLow = medianPaceMinKm + 30 / 60; paceHigh = medianPaceMinKm + 75 / 60; }
      const day = session.type === "long" ? longRunDay : nonLongDays.shift();
      const sessionDate = new Date(weekStartDate);
      sessionDate.setUTCDate(sessionDate.getUTCDate() + DAY_INDEX[day]);
      const paceTarget = `${formatPace(Math.min(paceLow, paceHigh))}–${formatPace(Math.max(paceLow, paceHigh))}`;
      let details = `${sessionDistances[sessionIndex].toFixed(1)} km total at ${paceTarget}.`;
      if (session.type === "quality") details = sessionDistances[sessionIndex] < 3 ? `${sessionDistances[sessionIndex].toFixed(1)} km total. After an easy warm-up, do 4 × 20 sec relaxed strides with 60–90 sec easy recovery; finish at easy effort. The pace range is for the strides.` : `${sessionDistances[sessionIndex].toFixed(1)} km total, including easy warm-up and cool-down. Run 4 × 1 min work intervals at ${paceTarget}, with 90 sec easy jog between them; run the rest easy.`;
      if (session.type === "tempo") details = sessionDistances[sessionIndex] < 3 ? `${sessionDistances[sessionIndex].toFixed(1)} km total. Include 5 min easy warm-up, 2 × 2 min steady at ${paceTarget} with 2 min easy jog, then finish easy.` : `${sessionDistances[sessionIndex].toFixed(1)} km total, including easy warm-up and cool-down. Run 3 × 3 min steady at ${paceTarget}, with 2 min easy jog between them; run the rest easy.`;
      if (session.type === "long") details += " Keep the effort conversational; slow down or use short walk breaks if needed.";
      return { date: sessionDate.toISOString().slice(0, 10), day: PLAN_DAYS[day], type: session.type, title: session.title, distanceKm: sessionDistances[sessionIndex], paceTarget, details };
    });
    sessions.sort((a, b) => a.date.localeCompare(b.date));
    if (raceDate && index === durationWeeks - 1) {
      const raceDateString = raceDate.toISOString().slice(0, 10);
      const day = DAY_ORDER[(raceDate.getUTCDay() + 6) % 7];
      sessions = sessions.filter((session) => session.date < raceDateString && session.type !== "long");
      sessions.push({
        date: raceDateString,
        day: PLAN_DAYS[day],
        type: "race",
        title: `${goal.label} race day`,
        distanceKm: goal.distanceKm,
        paceTarget: goalPaceMinKm ? `${formatPace(goalPaceMinKm)} goal pace` : "Effort-based · no pace target set",
        details: `Event day: ${goal.distanceKm === 21.0975 ? "21.1" : goal.distanceKm} km. Start controlled and use your finish-time target only if you entered one.`,
      });
      sessions.sort((a, b) => a.date.localeCompare(b.date));
      totalDistance = Math.round(sessions.reduce((sum, session) => sum + session.distanceKm, 0) * 10) / 10;
    }
    weeks.push({ week: index + 1, starting: weekStartDate.toISOString().slice(0, 10), totalDistanceKm: totalDistance, focus, sessions });
  }
  return {
    id: Date.now(), goal: options.goal, title: `${goal.label} · ${durationWeeks}-week plan`, goalLabel: goal.label,
    createdAt: new Date().toISOString(), durationWeeks, eventDate: options.eventDate || null, weeklySessions, longRunDay: PLAN_DAYS[longRunDay],
    baselineWeeklyKm: weeklyDistanceKm, medianPaceMinKm, goalPaceMinKm,
    paceNote: goalPaceMinKm ? `Race pace target is ${formatPace(goalPaceMinKm)} from your goal finish time. Easy running remains anchored to your recent median run pace (${formatPace(medianPaceMinKm)}).` : `Pace ranges are training estimates anchored to your recent median run pace (${formatPace(medianPaceMinKm)}), not a race-time prediction. Heat, hills, fatigue, and wrist heart-rate accuracy can change effort.`,
    weeks,
  };
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function selectTrainingDays(availableDays, sessionCount, longRunDay) {
  const candidates = availableDays.filter((day) => day !== longRunDay);
  let best = null;
  function visit(startIndex, picked) {
    if (picked.length === sessionCount - 1) {
      const choice = [longRunDay, ...picked].sort((a, b) => DAY_INDEX[a] - DAY_INDEX[b]);
      const gaps = choice.map((day, index) => (DAY_INDEX[choice[(index + 1) % choice.length]] - DAY_INDEX[day] + 7) % 7);
      const score = Math.min(...gaps) * 100 + gaps.reduce((sum, gap) => sum + gap * gap, 0);
      if (!best || score > best.score) best = { choice, score };
      return;
    }
    for (let index = startIndex; index < candidates.length; index += 1) visit(index + 1, [...picked, candidates[index]]);
  }
  visit(0, []);
  return best?.choice || [longRunDay];
}

function weekStart(value) {
  const day = new Date(`${String(value || "").slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(day.getTime())) return null;
  day.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
  return day.toISOString().slice(0, 10);
}

export function buildRunningWeeks(activities) {
  const active = new Map();
  for (const activity of activities || []) {
    if (!isRun(activity)) continue;
    const key = weekStart(activity.date);
    if (!key) continue;
    if (!active.has(key)) active.set(key, {
      week: key, distanceTotal: 0, unknownDistance: false, runs: 0, paces: [], hrs: [],
    });
    const row = active.get(key);
    row.runs += 1;
    if (isNumber(activity.distance_km)) row.distanceTotal += activity.distance_km;
    else row.unknownDistance = true;
    if (isNumber(activity.distance_km) && activity.distance_km > 0 && isNumber(activity.duration_s) && activity.duration_s > 0) {
      row.paces.push(activity.duration_s / 60 / activity.distance_km);
    }
    if (isNumber(activity.average_hr_bpm)) row.hrs.push(activity.average_hr_bpm);
  }
  if (!active.size) return [];

  const first = new Date(`${[...active.keys()].sort()[0]}T00:00:00Z`);
  const last = new Date(`${[...active.keys()].sort().at(-1)}T00:00:00Z`);
  const weeks = [];
  while (first <= last) {
    const week = first.toISOString().slice(0, 10);
    const source = active.get(week);
    weeks.push(source ? {
      week,
      distance: source.unknownDistance ? null : source.distanceTotal,
      runs: source.runs,
      paces: source.paces,
      hrs: source.hrs,
    } : { week, distance: 0, runs: 0, paces: [], hrs: [] });
    first.setUTCDate(first.getUTCDate() + 7);
  }
  return weeks.map((row, index) => {
    const window = weeks.slice(Math.max(0, index - 3), index + 1).map((week) => week.distance).filter(isNumber);
    return { ...row, rolling: window.length ? window.reduce((sum, value) => sum + value, 0) / window.length : null };
  });
}

export function classifyTrainingQuestion(question, previousIntent = null) {
  const text = String(question || "").trim().toLowerCase();
  if (/^(what|why|how|huh|explain)[?!.\s]*$/.test(text) && previousIntent) return "follow_up";
  const mentionsHr = /heart\s*rate|\bhr\b|bpm|pulse/.test(text);
  const mentionsPace = /pace|faster|speed|\btime\b/.test(text);
  const hasGoal = /decreas|lower|reduce|drop|maintain|keep|increase|improv|faster|speed|raise/.test(text);
  if (mentionsHr && mentionsPace && hasGoal) return "heart_rate_pace_goal";
  if (mentionsHr && mentionsPace) return "heart_rate_pace";
  if (/chart|graph|plot|visuali[sz]/.test(text)) return "visualize";
  if (/vo.?2|max/.test(text)) return "vo2";
  if (/sleep|recover|recovery/.test(text)) return "recovery";
  if (mentionsHr) return "heart_rate";
  if (mentionsPace) return "pace";
  if (/week|distance|volume|kilometer|\bkm\b/.test(text)) return "distance";
  if (/activity|sport|workout|strength|yoga|cycle/.test(text)) return "activity_mix";
  return "unknown";
}
