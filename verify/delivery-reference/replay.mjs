import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { POLICIES, simulate } from './simulator.mjs';

const RESTAURANT_NAMES = new Map([
  ['김치', 'kimchi'], ['피자', 'pizza'], ['탕수육', 'tangsuyuk'],
]);
const DESTINATION_NAMES = new Map([
  ['집', 'home'], ['학교', 'school'], ['공원', 'park'], ['아파트', 'apartment'], ['회사', 'company'],
]);
const ACTION_NAMES = ['up', 'down', 'left', 'right', 'pickup', 'dropoff'];
const L2 = {
  name: 'L2', n: 8, q: 0.03, T: 20, P: 20, menu_ban: true,
  ensure_all_menus: true, load_time: 2, deliver_time: 1, wrong_penalty: 10, horizon: 500,
};
const CONDITIONS = ['astar/every_step', 'astar/never', 'astar/on_complaint', 'greedy/never'];
const outputDirectory = process.argv[2];
if (!outputDirectory) throw new Error('An output directory is required');

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  return `{${Object.keys(value).sort().map(key =>
    `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
}

function readScenario(raw) {
  assert.equal(raw.preset, L2.name);
  assert.equal(raw.orders.length, L2.n);
  assert.equal(new Set(raw.orders.map(order => order.from)).size, 3);
  for (const [key, value] of Object.entries(raw.params)) assert.equal(value, L2[key], key);
  return {
    seed: raw.seed,
    hash: createHash('sha256').update(canonicalJson(raw), 'utf8').digest('hex'),
    input: {
      start: raw.start,
      orders: raw.orders.map(order => ({
        restaurant: RESTAURANT_NAMES.get(order.from),
        destination: DESTINATION_NAMES.get(order.to),
      })),
      complaints: raw.complaints.map(complaint => ({
        time: complaint.t, destination: DESTINATION_NAMES.get(complaint.dest),
      })),
      menuBan: L2.menu_ban,
      pickupTime: L2.load_time,
      complaintWindow: L2.T,
      complaintPenalty: L2.P,
    },
  };
}

const scenarios = new Map();
const records = [];
for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  const { kind, data } = JSON.parse(line);
  if (kind === 'scenario') {
    assert(!scenarios.has(data.scenario_id), data.scenario_id);
    scenarios.set(data.scenario_id, readScenario(data));
  } else {
    assert.equal(kind, 'actions');
    records.push(data);
  }
}

assert.equal(scenarios.size, 100);
assert.equal(records.length, 400);
const caseIds = new Set();
const runs = new Map(CONDITIONS.map(condition => [condition, new Map()]));
const results = [];
for (const record of records) {
  const { case_id, scenario_id, scenario_sha256, seed, preset, preset_params, algorithm, replan, actions } = record;
  const scenario = scenarios.get(scenario_id);
  const conditionRuns = runs.get(`${algorithm}/${replan}`);
  assert(scenario && conditionRuns, case_id);
  assert.equal(preset, L2.name, case_id);
  assert.deepEqual(preset_params, L2, case_id);
  assert(Number.isInteger(seed) && seed >= 0 && seed < 100, case_id);
  assert.equal(scenario.seed, seed, case_id);
  assert.equal(scenario.hash, scenario_sha256, case_id);
  assert(typeof case_id === 'string' && case_id && !caseIds.has(case_id), case_id);
  assert(!conditionRuns.has(seed), case_id);
  caseIds.add(case_id);
  const actionNames = actions.map(action => {
    assert(Number.isInteger(action) && action >= 0 && action < ACTION_NAMES.length, case_id);
    return ACTION_NAMES[action];
  });
  const variants = POLICIES.map(policy => simulate(scenario.input, actionNames, policy));
  conditionRuns.set(seed, variants);
  const grouped = new Map();
  for (const [policyIndex, variant] of variants.entries()) {
    const key = JSON.stringify(variant);
    if (!grouped.has(key)) grouped.set(key, { policyIds: [], result: variant });
    grouped.get(key).policyIds.push(policyIndex + 1);
  }
  results.push({ case_id, scenario_id, seed, algorithm, replan,
    actionsProvided: actions.length, variants: [...grouped.values()] });
}

const requestedMetrics = [
  'totalCost', 'averageDeliveryTime', 'success', 'complaintsSpawned', 'complaintsExpired',
];
const policySensitiveCases = Object.fromEntries(requestedMetrics.map(metric => [
  metric, results.filter(row => new Set(row.variants.map(({ result }) => result[metric])).size > 1).length,
]));
const summary = {
  scenarios: scenarios.size,
  cases: results.length,
  policySensitiveCases,
  policies: POLICIES.map((policy, index) => ({ id: index + 1, ...policy })),
  conditions: Object.fromEntries([...runs].map(([condition, conditionRuns]) => {
    assert.equal(conditionRuns.size, 100, condition);
    const byPolicy = POLICIES.map((_, policyIndex) => {
      const outcomes = [...conditionRuns.values()].map(variants => variants[policyIndex]);
      const sum = (metric) => outcomes.reduce((total, outcome) => total + outcome[metric], 0);
      const terminal = outcomes.filter(outcome => outcome.status !== 'incomplete');
      const complaintsSpawned = sum('complaintsSpawned');
      const complaintsExpired = sum('complaintsExpired');
      return {
        policyId: policyIndex + 1,
        successful: sum('success'),
        failed: terminal.length - sum('success'),
        incomplete: outcomes.length - terminal.length,
        meanTotalCost: terminal.reduce((total, outcome) => total + outcome.totalCost, 0) / terminal.length,
        meanDeliveryTime: terminal.reduce((total, outcome) => total + outcome.averageDeliveryTime, 0) / terminal.length,
        complaintsSpawned,
        complaintsExpired,
        complaintExpiryRate: complaintsSpawned ? complaintsExpired / complaintsSpawned : null,
      };
    });
    return [condition, byPolicy];
  })),
};

mkdirSync(outputDirectory, { recursive: true });
writeFileSync(join(outputDirectory, 'results.jsonl'), results.map(row => JSON.stringify(row)).join('\n') + '\n');
writeFileSync(join(outputDirectory, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
console.log(`Replayed ${scenarios.size} verified scenarios and ${results.length} cases.`);
