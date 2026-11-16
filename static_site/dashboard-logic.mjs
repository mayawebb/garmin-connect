const isNumber = (value) => typeof value === "number" && Number.isFinite(value);
const isRun = (activity) => /run/i.test(activity.type || "") && !/treadmill/i.test(activity.type || "");

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
