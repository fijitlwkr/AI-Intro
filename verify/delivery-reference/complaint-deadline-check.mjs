import assert from 'node:assert/strict';
import { POLICIES, simulate } from './simulator.mjs';

const toCompany = ['up', 'up', 'up', 'right'];
const toSchool = ['down', 'down', 'down', 'right'];
const scenario = {
  start: [3, 2],
  orders: [{ restaurant: 'kimchi', destination: 'park' }],
  complaintWindow: 4,
  complaints: [{ time: 0, destination: 'company' }],
};
const firstSpawn = [0, 'spawn', 0, 'company'];
const firstResolve = [4, 'resolve', 0, 'company'];
const schoolSpawn = [4, 'spawn', 4, 'school'];

function trace(input, actions, policy, options) {
  const events = [];
  const result = simulate(input, actions, policy, {
    ...options,
    onComplaintEvent: ({ time, type, scheduledAt, destination }) => {
      events.push([time, type, scheduledAt, destination]);
    },
  });
  return { result, events };
}

function run(secondTime, destination, actions, policy, options) {
  const { result, events } = trace({
    ...scenario,
    complaints: [...scenario.complaints, { time: secondTime, destination }],
  }, actions, policy, options);
  assert.equal(result.status, 'incomplete');
  return {
    time: result.time,
    position: result.position,
    counts: [result.complaintsSpawned, result.complaintsResolved,
      result.complaintsExpired, result.complaintsPending],
    events,
  };
}

const atHome = {
  ...scenario,
  start: [0, 7],
  complaints: [{ time: 0, destination: 'school' }, { time: 4, destination: 'home' }],
};
const oldSpawn = [0, 'spawn', 0, 'school'];
const immediateHome = [[4, 'spawn', 4, 'home'], [4, 'resolve', 4, 'home']];

function stayAtHome(ticks, policy) {
  // Every up move hits the map edge, leaving the courier at home for one tick and costing one.
  const { result, events } = trace(atHome, Array(ticks).fill('up'), policy);
  assert.equal(result.status, 'incomplete');
  assert.deepEqual([result.time, result.position, result.moves, result.invalidActions],
    [ticks, [0, 7], ticks, 0]);
  return {
    events,
    counts: [result.complaintsSpawned, result.complaintsResolved,
      result.complaintsExpired, result.complaintsPending],
    totalCost: result.totalCost,
  };
}

const finalDropoff = {
  start: [1, 2],
  orders: [{ restaurant: 'kimchi', destination: 'company' }],
  complaintWindow: 4,
  complaints: [{ time: 2, destination: 'school' }, { time: 6, destination: 'company' }],
};
const beforeDropoff = ['pickup', 'right', 'down', 'down'];
const schoolAtTwo = [2, 'spawn', 2, 'school'];
const schoolExpiresAtSix = [6, 'expire', 2, 'school'];
const instantCompanyAtSix = [[6, 'spawn', 6, 'company'], [6, 'resolve', 6, 'company']];

for (const policy of POLICIES) {
  // The south wall on (2,2) blocks the first three moves. Right arrives at the company at t=4.
  assert.deepEqual(run(4, 'company', toCompany, policy), {
    time: 4, position: [3, 3], counts: [2, 2, 0, 0],
    events: [firstSpawn, firstResolve, [4, 'spawn', 4, 'company'], [4, 'resolve', 4, 'company']],
  });
  assert.deepEqual(run(4, 'school', toCompany, policy), {
    time: 4, position: [3, 3], counts: [2, 1, 0, 1],
    events: [firstSpawn, firstResolve, schoolSpawn],
  });
  assert.deepEqual(run(4, 'school', [...toCompany, ...toSchool], policy), {
    time: 8, position: [6, 4], counts: [2, 2, 0, 0],
    events: [firstSpawn, firstResolve, schoolSpawn, [8, 'resolve', 4, 'school']],
  });

  // An invalid dropoff keeps the courier at the company for one tick.
  const stillAtCompany = [...toCompany, ...Array(4).fill('dropoff')];
  const expiryTick = policy.expireAtDeadline ? 8 : 9;
  assert.deepEqual(run(4, 'school', stillAtCompany, policy), {
    time: 8, position: [3, 3], counts: policy.expireAtDeadline ? [2, 1, 1, 0] : [2, 1, 0, 1],
    events: policy.expireAtDeadline
      ? [firstSpawn, firstResolve, schoolSpawn, [8, 'expire', 4, 'school']]
      : [firstSpawn, firstResolve, schoolSpawn],
  });
  assert.deepEqual(run(4, 'school', [...stillAtCompany, 'dropoff'], policy), {
    time: 9, position: [3, 3], counts: [2, 1, 1, 0],
    events: [firstSpawn, firstResolve, schoolSpawn, [expiryTick, 'expire', 4, 'school']],
  });

  // In the strict interpretation a supplied same-tick schedule is invalid.
  const strict = { requireSpawnAfterDeadline: true };
  for (const destination of ['company', 'school']) {
    assert.throws(() => run(4, destination, toCompany, policy, strict),
      /Invalid or overlapping complaint schedule/);
  }
  // A separate schedule puts the second complaint at the first admissible tick, t=5.
  assert.deepEqual(run(5, 'company', toCompany, policy, strict), {
    time: 4, position: [3, 3], counts: [1, 1, 0, 0], events: [firstSpawn, firstResolve],
  });
  assert.deepEqual(run(5, 'company', [...toCompany, 'dropoff'], policy, strict), {
    time: 5, position: [3, 3], counts: [2, 2, 0, 0],
    events: [firstSpawn, firstResolve, [5, 'spawn', 5, 'company'], [5, 'resolve', 5, 'company']],
  });

  assert.deepEqual(stayAtHome(3, policy), {
    events: [oldSpawn], counts: [1, 0, 0, 1], totalCost: 3,
  });
  const expiresAtFour = [4, 'expire', 0, 'school'];
  assert.deepEqual(stayAtHome(4, policy), policy.expireAtDeadline ? {
    events: [oldSpawn, expiresAtFour, ...immediateHome],
    counts: [2, 1, 1, 0],
    totalCost: 24,
  } : {
    events: [oldSpawn, ...immediateHome],
    counts: [2, 1, 0, 1], // Only the old penalty is pending.
    totalCost: 4,
  });
  assert.deepEqual(stayAtHome(5, policy), {
    events: policy.expireAtDeadline
      ? [oldSpawn, expiresAtFour, ...immediateHome]
      : [oldSpawn, ...immediateHome, [5, 'expire', 0, 'school']],
    counts: [2, 1, 1, 0],
    totalCost: 25,
  });

  // Pickup uses two ticks, three moves reach the company at t=5, and dropoff ends at t=6.
  const inspect = { includeOrderStatuses: true };
  const before = trace(finalDropoff, beforeDropoff, policy, inspect);
  assert.deepEqual(before.events, [schoolAtTwo]);
  assert.deepEqual([before.result.status, before.result.time, before.result.position,
    before.result.orderStatuses, before.result.completionTimes], ['incomplete', 5, [3, 3], ['loaded'], [null]]);

  const finishingActions = [...beforeDropoff, 'dropoff'];
  const finished = trace(finalDropoff, finishingActions, policy, inspect);
  assert.deepEqual(finished.events, [
    schoolAtTwo,
    ...(policy.expireAtDeadline ? [schoolExpiresAtSix] : []),
    ...(policy.countTerminalSpawn ? instantCompanyAtSix : []),
  ]);
  assert.deepEqual([finished.result.success, finished.result.time, finished.result.position,
    finished.result.orderStatuses, finished.result.completionTimes, finished.result.averageDeliveryTime,
    finished.result.moves, finished.result.invalidActions],
  [true, 6, [3, 3], ['done'], [6], 6, 3, 0]);
  assert.deepEqual([
    finished.result.complaintsSpawned, finished.result.complaintsResolved,
    finished.result.complaintsExpired, finished.result.complaintsPending, finished.result.totalCost,
  ], [
    policy.countTerminalSpawn ? 2 : 1, policy.countTerminalSpawn ? 1 : 0,
    policy.expireAtDeadline ? 1 : 0, policy.expireAtDeadline ? 0 : 1,
    policy.expireAtDeadline ? 23 : 3,
  ]);
  // A trailing move would advance to t=7 and expose an incorrectly charged deferred penalty.
  assert.deepEqual(trace(finalDropoff, [...finishingActions, 'up'], policy, inspect), finished);
}

console.log('Verified complaint event order and hand-calculated counts under all 8 base policies.');
