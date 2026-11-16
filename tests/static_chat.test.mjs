import test from "node:test";
import assert from "node:assert/strict";
import { buildRunningWeeks, classifyTrainingQuestion } from "../static_site/dashboard-logic.mjs";

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
