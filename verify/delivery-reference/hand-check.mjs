import assert from 'node:assert/strict';
import { POLICIES, simulate } from './simulator.mjs';

const kimchiToCompany = { restaurant: 'kimchi', destination: 'company' };
const toCompany = ['pickup', 'right', 'down', 'down', 'dropoff'];
const scenario = {
  start: [1, 2],
  orders: [kimchiToCompany],
  complaints: [],
};
const repeat = (action, count) => Array(count).fill(action);

for (const policy of POLICIES) {
  // Two duplicate orders both finish at 2+3+1. Only the three moves cost anything.
  const duplicates = simulate({ ...scenario, orders: [kimchiToCompany, kimchiToCompany] },
    toCompany, policy);
  assert.deepEqual(duplicates.completionTimes, [6, 6]);
  assert.equal(duplicates.totalCost, 3);
  assert.equal(duplicates.averageDeliveryTime, 6);
  assert.equal(duplicates.success, true);

  // Both sides of each wall and the upper map edge still count as movement.
  for (const [start, action] of [
    [[0, 4], 'right'], [[0, 5], 'left'], [[2, 2], 'down'], [[3, 2], 'up'], [[0, 0], 'up'],
  ]) {
    const blocked = simulate({ ...scenario, start }, [action], policy);
    assert.deepEqual(blocked.position, start);
    assert.equal(blocked.time, 1);
    assert.equal(blocked.totalCost, 1);
    assert.equal(blocked.success, null);
  }

  // Two pickups succeed; the third costs either one tick and +10, or two ticks.
  const threeMenus = {
    ...scenario,
    orders: [kimchiToCompany, { restaurant: 'pizza', destination: 'school' },
      { restaurant: 'tangsuyuk', destination: 'home' }],
  };
  const route = ['pickup', 'right', ...repeat('down', 4), 'left', 'left',
    ...repeat('down', 3), 'pickup', ...repeat('up', 4), ...repeat('right', 7), 'pickup'];
  const banned = simulate(threeMenus, route, policy);
  const allowed = simulate({ ...threeMenus, menuBan: false }, route, policy);
  assert.deepEqual(banned.position, [4, 8]);
  assert.deepEqual([banned.totalCost, banned.time, banned.invalidActions], [31, 26, 1]);
  assert.deepEqual([allowed.totalCost, allowed.time, allowed.invalidActions], [21, 27, 0]);

  const arrival = {
    ...scenario, start: [3, 2], complaintWindow: 1,
    complaints: [{ time: 0, destination: 'company' }],
  };
  const onDeadline = simulate(arrival, ['right'], policy);
  const afterDeadline = simulate(arrival, ['up', 'right'], policy);
  assert.deepEqual([onDeadline.complaintsSpawned, onDeadline.complaintsResolved,
    onDeadline.complaintsExpired, onDeadline.totalCost], [1, 1, 0, 1]);
  assert.deepEqual([afterDeadline.complaintsResolved, afterDeadline.complaintsExpired,
    afterDeadline.totalCost], [0, 1, 22]);
  assert.equal(simulate(arrival, ['up'], policy).complaintsExpired, Number(policy.expireAtDeadline));

  // The clock visits t=1 during pickup. At t=2 the first ticket is late,
  // and the second ticket has just spawned.
  const duringPickup = simulate({ ...scenario, complaintWindow: 1,
    complaints: [{ time: 0, destination: 'home' }, { time: 1, destination: 'park' }] },
  ['pickup'], policy);
  assert.deepEqual([duringPickup.complaintsSpawned, duringPickup.complaintsExpired,
    duringPickup.totalCost], policy.expireAtDeadline ? [2, 2, 40] : [2, 1, 20]);
  const immediate = simulate({ ...arrival, start: [3, 3] }, [], policy);
  assert.deepEqual([immediate.complaintsSpawned, immediate.complaintsResolved], [1, 1]);

  const terminal = simulate({ ...scenario, complaints: [{ time: 6, destination: 'company' }] },
    [...toCompany, 'dropoff'], policy);
  assert.equal(terminal.complaintsSpawned, Number(policy.countTerminalSpawn));
  assert.equal(terminal.actionsUsed, 5);

  // Deliver the first order at t=6 and leave the second outstanding at t=500.
  const failure = simulate({ ...scenario,
    orders: [kimchiToCompany, { restaurant: 'pizza', destination: 'park' }] },
  [...toCompany, ...repeat('right', 494)], policy);
  assert.deepEqual([failure.time, failure.totalCost, failure.averageDeliveryTime,
    failure.success], [500, 497, 253, false]);

  const tie = simulate(scenario, [...repeat('dropoff', 494), ...toCompany], policy);
  assert.deepEqual([tie.time, tie.totalCost, tie.averageDeliveryTime, tie.success],
    [500, 4943, 500, policy.successAtHorizon]);
}
console.log(`Hand-calculated checks passed under all ${POLICIES.length} boundary policies.`);
