// k6 load test for the Events API (POST /api/v1/events/).
//
// Traffic is a mix of brand-new dedup keys (each must open exactly one incident) and
// repeats of a small hot set (each must attach to the one open incident, never open a
// second). After the run, loadtest/verify.py checks those counts against the database.
//
//   k6 run -e BASE_URL=http://localhost:8080 -e ROUTING_KEY=... loadtest/events.js
//
// Env:  VUS (default 32)        concurrent virtual users, closed model (saturation test)
//       RATE (unset)            if set, requests/second in an open model instead
//       DURATION (default 60s)  measured window (a 5s warm-up precedes it)
//       NEW_RATIO (default 0.3) fraction of requests that use a never-seen dedup key
//       HOT_KEYS (default 50)   size of the repeated-key pool
//       SUMMARY (default /out/summary.json)
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const ROUTING_KEY = __ENV.ROUTING_KEY;
const NEW_RATIO = parseFloat(__ENV.NEW_RATIO || "0.3");
const HOT_KEYS = parseInt(__ENV.HOT_KEYS || "50", 10);
const RUN = __ENV.RUN_ID || `${Date.now()}`;

const newKeys = new Counter("pulse_new_keys");
const hotKeys = new Counter("pulse_hot_requests");
const rejected = new Counter("pulse_unexpected_status");

const measured = __ENV.RATE
  ? {
      executor: "constant-arrival-rate",
      rate: parseInt(__ENV.RATE, 10),
      timeUnit: "1s",
      duration: __ENV.DURATION || "60s",
      preAllocatedVUs: parseInt(__ENV.VUS || "64", 10),
      maxVUs: 512,
      startTime: "5s",
    }
  : {
      executor: "constant-vus",
      vus: parseInt(__ENV.VUS || "32", 10),
      duration: __ENV.DURATION || "60s",
      startTime: "5s",
    };

export const options = {
  scenarios: {
    // Warm-up: connection pools, query plans, worker processes. Not measured.
    warmup: { executor: "constant-vus", vus: 4, duration: "5s", tags: { phase: "warmup" } },
    measured: { ...measured, tags: { phase: "measured" } },
  },
  thresholds: {
    "http_req_failed{phase:measured}": ["rate<0.001"],
    // Declared so k6 computes the measured-window numbers separately from the warm-up.
    "http_reqs{phase:measured}": ["count>0"],
    "http_req_duration{phase:measured}": ["p(99)<60000"],
    "pulse_unexpected_status": ["count==0"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export default function () {
  let key;
  if (Math.random() < NEW_RATIO) {
    key = `new-${RUN}-${__VU}-${__ITER}`;
    newKeys.add(1); // counted in every phase: verify.py checks the whole database
  } else {
    key = `hot-${RUN}-${Math.floor(Math.random() * HOT_KEYS)}`;
    hotKeys.add(1);
  }
  const res = http.post(
    `${BASE_URL}/api/v1/events/`,
    JSON.stringify({
      routing_key: ROUTING_KEY,
      event_action: "trigger",
      dedup_key: key,
      payload: { summary: `load test ${key}`, severity: "warning", source: "k6" },
    }),
    { headers: { "Content-Type": "application/json" } },
  );
  const ok = check(res, { "202 accepted": (r) => r.status === 202 });
  if (!ok) rejected.add(1);
}

export function handleSummary(data) {
  const out = __ENV.SUMMARY || "/out/summary.json";
  return { [out]: JSON.stringify(data, null, 2), stdout: textSummary(data) };
}

function textSummary(data) {
  const m = data.metrics;
  const t = m["http_req_duration{phase:measured}"] ? m["http_req_duration{phase:measured}"].values : m.http_req_duration.values;
  const reqs = m["http_reqs{phase:measured}"] ? m["http_reqs{phase:measured}"].values : m.http_reqs.values;
  // k6's own rate divides by the whole test, warm-up included; use the measured window.
  const d = (__ENV.DURATION || "60s").match(/^(\d+)(s|m)$/);
  const seconds = d ? parseInt(d[1], 10) * (d[2] === "m" ? 60 : 1) : 60;
  return [
    "",
    `measured requests : ${reqs.count} in ${seconds}s  (${(reqs.count / seconds).toFixed(1)} req/s)`,
    `latency (ms)      : p50=${t.med.toFixed(1)}  p95=${t["p(95)"].toFixed(1)}  p99=${t["p(99)"].toFixed(1)}  max=${t.max.toFixed(1)}`,
    `new keys sent     : ${m.pulse_new_keys ? m.pulse_new_keys.values.count : 0}`,
    `unexpected status : ${m.pulse_unexpected_status ? m.pulse_unexpected_status.values.count : 0}`,
    "",
  ].join("\n");
}
