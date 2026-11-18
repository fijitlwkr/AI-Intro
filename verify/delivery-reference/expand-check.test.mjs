import assert from 'node:assert/strict';
import { checkRow, PRESETS, scenarioHash, canonicalJson } from './expand-check.mjs';

const copies = (from, n) => Array.from({ length: n }, () => ({ from, to: '회사' }));
const sc = { scenario_id: 'L0-000', preset: 'L0', seed: 0,
  params: { n: 8, q: 0, T: 20, ensure_all_menus: true, horizon: 500 }, start: [1, 2],
  orders: [...copies('김치', 4), ...copies('피자', 2), ...copies('탕수육', 2)], complaints: [] };
const repeat = (a, n) => Array(n).fill(a);
// Kimchi completes at 6, pizza at 23, tangsuyuk at 38.
// 29 moves; average = (4*6 + 2*23 + 2*38)/8 = 18.25.
const actions = [4, 3, 1, 1, 5, ...repeat(2, 2), ...repeat(1, 5), 4,
  ...repeat(0, 5), ...repeat(3, 2), 5, ...repeat(3, 5), 1, 4, 0, ...repeat(2, 5), 5];
const row = { algorithm: 'hand', preset: 'L0', seed: 0, scenario_id: 'L0-000',
  preset_params: PRESETS.L0, scenario_sha256: scenarioHash(sc), actions,
  score_cost: 29, score_avg_time: 18.25, score_success: true, score_complaints: 0,
  score_expired: 0, score_total_time: 38, score_wrong_actions: 0, score_complaint_miss: null };
assert.deepEqual(checkRow(row, sc).errors, []);
assert.deepEqual(checkRow(row, sc).warnings, []);
assert.equal(checkRow({ ...row, score_cost: 30 }, sc).errors[0].field, 'score_cost');
assert.equal(checkRow({ ...row, scenario_sha256: 'invalid' }, sc).errors[0].field, 'input_or_replay');
assert(checkRow({ ...row, actions: [true] }, sc).errors.length);
assert(checkRow({ ...row, actions: actions.slice(0, -1) }, sc).errors.length);
assert(checkRow({ ...row, actions: [...actions, 0] }, sc).errors.length);
assert(checkRow({ ...row, preset_params: { ...PRESETS.L0, P: 999 } }, sc).errors.length);
const historical = { ...row }; delete historical.scenario_sha256;
assert.deepEqual(checkRow(historical, sc).errors, []);
assert.equal(checkRow(historical, sc).warnings.length, 1);
assert.equal(canonicalJson({ q: 0, n: 8 }), '{"n":8,"q":0.0}');
assert.equal(canonicalJson({ q: .03, n: 8 }), '{"n":8,"q":0.03}');
console.log('Expanded adapter: hand-calculated baseline and corrupted score/hash/action/input/termination checks passed.');
