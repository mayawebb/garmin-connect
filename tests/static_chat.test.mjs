import test from "node:test";
import assert from "node:assert/strict";
import { buildRunningWeeks, buildTrainingPlan, classifyTrainingQuestion, dashboardApiUrl, deriveRunBaseline, normalizeChatResponse, normalizeDashboardData, parseFinishTime, parsePace, privateApiErrorMessage } from "../static_site/dashboard-logic.mjs";

test("combined request to lower heart rate and improve pace is one training goal", () => {
  assert.equal(
    classifyTrainingQuestion("how can i decrease hr and increase pace in my runs"),
    "heart_rate_pace_goal",
  );
});

test("lowering heart rate while maintaining pace is also a combined goal", () => {
  assert.equal(
    classifyTrainingQuestion("how do I lower heart rate while maintaining this pace?"),
    "heart_rate_pace_goal",
  );
});

test("short follow-up questions are identified as follow-ups", () => {
  assert.equal(classifyTrainingQuestion("what?", "heart_rate_pace_goal"), "follow_up");
});

test("unknown run distance stays unknown while weeks with no runs stay zero", () => {
  const weeks = buildRunningWeeks([
    { date: "2026-01-05T07:00:00Z", type: "running", distance_km: 5, duration_s: 1800 },
    { date: "2026-01-06T07:00:00Z", type: "running", distance_km: null, duration_s: null },
    { date: "2026-01-19T07:00:00Z", type: "running", distance_km: 7, duration_s: 2520 },
  ]);

  assert.deepEqual(weeks.map(({ distance }) => distance), [null, 0, 7]);
  assert.deepEqual(weeks.map(({ runs }) => runs), [2, 0, 1]);
});

test("weekly smoothing ignores unknown weeks instead of treating them as zero", () => {
  const weeks = buildRunningWeeks([
    { date: "2026-01-05T07:00:00Z", type: "running", distance_km: null },
    { date: "2026-01-19T07:00:00Z", type: "running", distance_km: 7 },
  ]);

  assert.equal(weeks[1].rolling, 0);
  assert.equal(weeks[2].rolling, 3.5);
});

test("normalized backend dashboard keeps Garmin source and database date metadata", () => {
  const data = normalizeDashboardData({
    schema_version: 1,
    source: "garmin_sqlite",
    metadata: { activity_count: 2, date_range: { start: "2025-10-13", end: "2026-11-15" } },
    activities: [{ date: "2026-11-15", type: "running", distance_km: 5 }, { date: "2026-11-15", type: "treadmill_running" }],
    health: [],
  });

  assert.equal(data.source, "garmin_sqlite");
  assert.deepEqual(data.metadata.date_range, { start: "2025-10-13", end: "2026-11-15" });
  assert.equal(data.activities.length, 1);
  assert.equal(data.activities[0].duration_s, null);
});

test("chat response validation keeps safe chart rows and rejects malformed output", () => {
  const result = normalizeChatResponse({
    answer: "Your weekly distance is shown.",
    chart: { metric: "distance_km", chart_type: "line", group_by: "week", unit: "km", rows: [{ x: "2026-11-09", value: 12 }] },
  });

  assert.equal(result.chart.rows[0].value, 12);
  assert.throws(() => normalizeChatResponse({ answer: "ok", chart: { rows: [{ x: "x", value: "<script>" }] } }));
});

test("API URLs stay same-origin under both root hosting and a GitHub Pages subpath", () => {
  assert.equal(dashboardApiUrl("chat", "https://mayawebb.github.io/garmin-connect/static_site/"), "/garmin-connect/static_site/api/chat");
  assert.equal(dashboardApiUrl("sync", "https://dashboard.example/"), "/api/sync");
});

test("training baseline uses recent complete weeks and formats a recorded pace as min:sec/km", () => {
  const activities = [
    { date: "2026-10-19T07:00:00Z", type: "running", distance_km: 8, duration_s: 8 * 400 },
    { date: "2026-10-26T07:00:00Z", type: "running", distance_km: 6, duration_s: 6 * 400 },
    { date: "2026-11-02T07:00:00Z", type: "running", distance_km: 10, duration_s: 10 * 400 },
    { date: "2026-11-09T07:00:00Z", type: "treadmill_running", distance_km: 20, duration_s: 20 * 300 },
  ];
  const baseline = deriveRunBaseline(activities, new Date("2026-11-16T12:00:00Z"));
  assert.equal(baseline.weeklyDistanceKm, 6);
  assert.equal(baseline.medianPaceMinKm, 6 + 40 / 60);
  assert.equal(baseline.recordedRuns, 3);
});

test("training plan schedules the requested count with concrete distances and pace targets", () => {
  const plan = buildTrainingPlan({
    goal: "10k", weeklySessions: 3, availableDays: ["tue", "thu", "sat"], longRunDay: "sat",
    durationWeeks: 4, weeklyDistanceKm: 12, medianPaceMinKm: 6.6, startDate: "2026-11-16",
  });
  assert.equal(plan.weeks.length, 4);
  for (const week of plan.weeks) {
    assert.equal(week.sessions.length, 3);
    assert.ok(week.sessions.every((session) => session.distanceKm > 0 && session.paceTarget.includes("/km")));
    assert.ok(week.sessions.some((session) => session.type === "long" && session.day === "Saturday"));
    assert.ok(Math.abs(week.sessions.reduce((sum, session) => sum + session.distanceKm, 0) - week.totalDistanceKm) < 0.11);
  }
  assert.ok(plan.weeks[3].totalDistanceKm < plan.weeks[2].totalDistanceKm, "fourth week should reduce load");
});

test("training plan rejects a schedule with fewer available days than requested sessions", () => {
  assert.throws(() => buildTrainingPlan({
    goal: "5k", weeklySessions: 4, availableDays: ["tue", "sat"], longRunDay: "sat",
    durationWeeks: 8, weeklyDistanceKm: 10, medianPaceMinKm: 6.5, startDate: "2026-11-16",
  }), /available days/i);
});

test("race target time turns into a pace target while easy pace stays based on training data", () => {
  const plan = buildTrainingPlan({
    goal: "5k", weeklySessions: 3, availableDays: ["tue", "thu", "sat"], longRunDay: "sat",
    durationWeeks: 8, weeklyDistanceKm: 12, medianPaceMinKm: parsePace("6:36"),
    targetFinishSeconds: parseFinishTime("28:00"), startDate: "2026-11-16",
  });
  assert.equal(plan.goalPaceMinKm, 5.6);
  assert.equal(plan.weeks[0].sessions[1].paceTarget, "5:31/km–5:46/km");
  assert.equal(plan.weeks[0].sessions[0].paceTarget, "7:06/km–7:51/km");
});

test("race date replaces the final long run and leaves no workouts after race day", () => {
  const plan = buildTrainingPlan({
    goal: "5k", weeklySessions: 3, availableDays: ["tue", "thu", "sat"], longRunDay: "sat",
    durationWeeks: 4, weeklyDistanceKm: 12, medianPaceMinKm: 6.6,
    eventDate: "2026-12-13", startDate: "2026-11-16",
  });
  const finalWeek = plan.weeks.at(-1);
  assert.ok(finalWeek.sessions.some((session) => session.type === "race" && session.date === "2026-12-13" && session.distanceKm === 5));
  assert.ok(finalWeek.sessions.every((session) => session.date <= "2026-12-13"));
  assert.ok(!finalWeek.sessions.some((session) => session.type === "long"));
});

test("private chat explains that an unauthenticated 401 requires signing in", () => {
  assert.match(privateApiErrorMessage(401), /sign in with your allowed email and PIN/i);
});
