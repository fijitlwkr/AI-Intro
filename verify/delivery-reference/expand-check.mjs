// Later input/comparison adapter. The specification-only simulator engine is unchanged.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { resolve, dirname, relative, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
import { platform, release } from 'node:os';
import { POLICIES, simulate } from './simulator.mjs';

const RESTAURANTS = new Map([['김치', 'kimchi'], ['피자', 'pizza'], ['탕수육', 'tangsuyuk']]);
const DESTINATIONS = new Map([['집', 'home'], ['학교', 'school'], ['공원', 'park'], ['아파트', 'apartment'], ['회사', 'company']]);
const ACTIONS = ['up', 'down', 'left', 'right', 'pickup', 'dropoff'];
const BASE = { n: 8, T: 20, P: 20, menu_ban: true, ensure_all_menus: true,
  load_time: 2, deliver_time: 1, wrong_penalty: 10, horizon: 500 };
// Transcribed from the supplied rules, not imported from the game environment.
export const PRESETS = Object.fromEntries(Object.entries({
  L0: { q: 0, menu_ban: false }, L1: { q: 0 }, L2: { q: .03 },
  L3: { n: 12, q: .06, T: 15, P: 40 },
}).map(([name, overrides]) => [name, { name, ...BASE, ...overrides }]));
const FIELDS = { score_cost: 'totalCost', score_avg_time: 'averageDeliveryTime',
  score_success: 'success', score_complaints: 'complaintsSpawned', score_expired: 'complaintsExpired',
  score_total_time: 'time', score_wrong_actions: 'invalidActions' };

export function canonicalJson(value, key = '') {
  // Schema q is a Python float. JSON.parse loses 0.0 vs 0; restore the schema's
  // float spelling for hash parity without accepting a missing/mismatched hash.
  if (typeof value === 'number' && key === 'q' && Number.isInteger(value)) return value.toFixed(1);
  if (Array.isArray(value)) return `[${value.map(item => canonicalJson(item)).join(',')}]`;
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalJson(value[k], k)}`).join(',')}}`;
}
export function scenarioHash(scenario) {
  return createHash('sha256').update(canonicalJson(scenario), 'utf8').digest('hex');
}

export function checkRow(row, scenario) {
  const warnings = [], errors = [];
  let result;
  try {
    const preset = PRESETS[row.preset];
    assert(preset, 'Unsupported preset');
    assert.deepEqual(row.preset_params, preset, 'Recorded preset differs from specification');
    assert.equal(scenario.preset, row.preset, 'Scenario preset mismatch');
    assert.equal(scenario.seed, row.seed, 'Scenario seed mismatch');
    assert.equal(scenario.scenario_id, row.scenario_id, 'Scenario ID mismatch');
    assert.equal(scenario.orders.length, preset.n, 'Order count mismatch');
    assert.equal(new Set(scenario.orders.map(o => o.from)).size, 3, 'Missing menu');
    const params = { n: preset.n, q: preset.q, T: preset.T,
      ensure_all_menus: preset.ensure_all_menus, horizon: preset.horizon };
    assert.deepEqual(scenario.params, params, 'Scenario settings mismatch');
    const hash = scenarioHash(scenario);
    if (row.scenario_sha256) assert.equal(row.scenario_sha256, hash, 'Scenario hash mismatch');
    else warnings.push('Historical log has no scenario hash; original input identity is unproven');
    assert(Array.isArray(row.actions), 'Missing actions');
    const actions = row.actions.map(a => {
      assert(Number.isInteger(a) && a >= 0 && a < ACTIONS.length, 'Invalid action number');
      return ACTIONS[a];
    });
    const input = {
      start: scenario.start,
      orders: scenario.orders.map(o => ({ restaurant: RESTAURANTS.get(o.from), destination: DESTINATIONS.get(o.to) })),
      complaints: scenario.complaints.map(c => ({ time: c.t, destination: DESTINATIONS.get(c.dest) })),
      menuBan: preset.menu_ban, pickupTime: preset.load_time,
      complaintWindow: preset.T, complaintPenalty: preset.P,
    };
    // Policy 4: team-confirmed success at H; current log's complaint conventions.
    // Expected scores and algorithm internals are not passed to the engine.
    result = simulate(input, actions, POLICIES[3], { requireSpawnAfterDeadline: true });
    assert.notEqual(result.status, 'incomplete', 'Incomplete action sequence; timeout/partial logs are outside this adapter scope');
    assert.equal(result.actionsUsed, actions.length, 'Actions recorded after episode termination');
    for (const [field, metric] of Object.entries(FIELDS)) {
      const actual = result[metric], expected = row[field];
      const equal = typeof actual === 'number' && typeof expected === 'number'
        ? Number.isFinite(expected) && Math.abs(actual - expected) <= 1e-9
        : actual === expected;
      if (!equal) errors.push({ field, recorded: expected ?? null, replayed: actual });
    }
    const miss = result.complaintsSpawned ? result.complaintsExpired / result.complaintsSpawned : null;
    if (row.score_complaint_miss !== miss && !(typeof miss === 'number' &&
      typeof row.score_complaint_miss === 'number' && Math.abs(row.score_complaint_miss - miss) <= 1e-9)) {
      errors.push({ field: 'score_complaint_miss', recorded: row.score_complaint_miss ?? null, replayed: miss });
    }
  } catch (error) { errors.push({ field: 'input_or_replay', message: error.message }); }
  return { errors, warnings, result };
}

function filesAt(path) {
  if (statSync(path).isFile()) return path.endsWith('.jsonl') ? [path] : [];
  return readdirSync(path, { withFileTypes: true }).flatMap(entry => filesAt(join(path, entry.name)));
}

export function main(argv = process.argv.slice(2)) {
  let out, scenarios = 'scenarios';
  const sources = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--out') out = argv[++i];
    else if (argv[i] === '--scenarios') scenarios = argv[++i];
    else sources.push(argv[i]);
  }
  assert(out && sources.length, 'Usage: node expand-check.mjs --out report.json [--scenarios scenarios] <JSONL files or directories...>');
  const files = [...new Set(sources.flatMap(p => filesAt(resolve(p))))].sort();
  assert(files.length, 'No JSONL logs');
  const details = [], groups = new Map(), inputErrors = [];
  const scenarioIds = new Set();
  for (const file of files) {
    const seen = new Set();
    for (const [index, line] of readFileSync(file, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/).entries()) {
      if (!line.trim()) continue;
      let row;
      try { row = JSON.parse(line); }
      catch (error) { inputErrors.push({ file: relative(process.cwd(), file), line: index + 1, message: error.message }); continue; }
      const key = JSON.stringify([relative(process.cwd(), file), row.git_commit, row.algorithm, row.preset, row.replan, row.params]);
      if (!groups.has(key)) groups.set(key, { file: relative(process.cwd(), file), commit: row.git_commit,
        algorithm: row.algorithm, preset: row.preset, replan: row.replan, params: row.params,
        games: 0, mismatches: 0, hashWarningGames: 0, successes: 0, maxTime: 0 });
      let checked;
      try {
        const identity = JSON.stringify([row.preset, row.seed, row.algorithm, row.replan, row.params]);
        assert(!seen.has(identity), 'Duplicate case in a source file');
        seen.add(identity);
        const sc = JSON.parse(readFileSync(join(scenarios, `${row.preset}_${String(row.seed).padStart(3, '0')}.json`), 'utf8'));
        checked = checkRow(row, sc);
        scenarioIds.add(row.scenario_id);
      } catch (error) { checked = { errors: [{ field: 'input_or_replay', message: error.message }], warnings: [] }; }
      const group = groups.get(key);
      group.games++;
      group.mismatches += Number(checked.errors.length > 0);
      group.hashWarningGames += Number(checked.warnings.length > 0);
      group.successes += Number(checked.result?.success === true);
      group.maxTime = Math.max(group.maxTime, checked.result?.time ?? 0);
      details.push({ source: relative(process.cwd(), file), line: index + 1, seed: row.seed,
        errors: checked.errors, warnings: checked.warnings });
    }
  }
  const mismatchingGames = details.filter(d => d.errors.length).length;
  let commit = null, dirty = null;
  try {
    commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    dirty = Boolean(execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim());
  } catch { /* Standalone use without Git remains possible. */ }
  const report = { status: mismatchingGames || inputErrors.length ? 'fail' : 'pass_with_scope_limits',
    recordedAt: new Date().toISOString(), environment: { node: process.version, platform: platform(), release: release(), commit, dirty },
    engineSha256: createHash('sha256').update(readFileSync(new URL('./simulator.mjs', import.meta.url))).digest('hex'),
    policy: { id: 4, ...POLICIES[3], crossingPickup: 'finish', requireSpawnAfterDeadline: true },
    scope: 'Existing specification-only engine; later adapter written in implementation-informed integration context. No env/agents imports. Historical input identity remains unproven without hashes. Timing and node counts excluded.',
    files: files.length, games: details.length, distinctScenarios: scenarioIds.size, mismatchingGames,
    hashWarningGames: details.filter(d => d.warnings.length).length,
    comparedFields: [...Object.keys(FIELDS), 'score_complaint_miss'], groups: [...groups.values()], inputErrors, details };
  mkdirSync(dirname(resolve(out)), { recursive: true });
  writeFileSync(out, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, files: report.files, groups: report.groups.length,
    games: report.games, mismatchingGames, hashWarningGames: report.hashWarningGames, inputErrors: inputErrors.length }));
  return mismatchingGames || inputErrors.length ? 1 : 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) process.exitCode = main();
