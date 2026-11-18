import assert from 'node:assert/strict';
import { POLICIES, simulate } from './simulator.mjs';

const scenario = {
  start: [0, 0],
  orders: [{ restaurant: 'kimchi', destination: 'company' }],
  complaints: [],
};
const atRestaurant = blockedMoves => [...Array(blockedMoves).fill('up'), 'down', 'right', 'right'];
const beforeDropoff = [...atRestaurant(491), 'pickup', 'right', 'down', 'down'];
const beforeLatePickup = atRestaurant(496);
const inspect = { includeOrderStatuses: true };

function observed(result) {
  return {
    time: result.time,
    success: result.success,
    status: result.status,
    orders: result.orderStatuses,
    completionTimes: result.completionTimes,
    moves: result.moves,
    invalidActions: result.invalidActions,
    totalCost: result.totalCost,
    averageDeliveryTime: result.averageDeliveryTime,
    actionsUsed: result.actionsUsed,
    position: result.position,
    complaints: [result.complaintsSpawned, result.complaintsExpired],
  };
}

// 491 blocked moves + 3 to the restaurant + 2 ticks loading + 3 to the company = 499.
// Delivery takes one tick. The trailing move would change cost and position if consumed.
const dropoffBase = {
  time: 500, moves: 497, invalidActions: 0, totalCost: 497,
  averageDeliveryTime: 500, actionsUsed: 499, position: [3, 3], complaints: [0, 0],
};

// 496 blocked moves + 3 to the restaurant = 499. A valid pickup would end at 501.
// No order is delivered. The unfinished order contributes H=500 in every interpretation.
const pickupBase = {
  success: false, status: 'failure', completionTimes: [null],
  moves: 499, invalidActions: 0, totalCost: 499,
  averageDeliveryTime: 500, actionsUsed: 500, position: [1, 2], complaints: [0, 0],
};

for (const policy of POLICIES) {
  const dropoffStart = simulate(scenario, beforeDropoff, policy, inspect);
  assert.deepEqual([dropoffStart.time, dropoffStart.position, dropoffStart.orderStatuses],
    [499, [3, 3], ['loaded']]);
  const dropoffActions = [...beforeDropoff, 'dropoff', 'up'];
  assert.deepEqual(observed(simulate(scenario, dropoffActions, policy, inspect)), {
    ...dropoffBase, success: policy.successAtHorizon,
    status: policy.successAtHorizon ? 'success' : 'failure',
    orders: ['done'], completionTimes: [500],
  });
  if (!policy.successAtHorizon) {
    assert.deepEqual(observed(simulate(scenario, dropoffActions, policy,
      { ...inspect, skipDropoffAtHorizon: true })), {
      ...dropoffBase, success: false, status: 'failure',
      orders: ['loaded'], completionTimes: [null],
    });
  }

  const pickupStart = simulate(scenario, beforeLatePickup, policy, inspect);
  assert.deepEqual([pickupStart.time, pickupStart.position, pickupStart.orderStatuses],
    [499, [1, 2], ['waiting']]);
  const pickupActions = [...beforeLatePickup, 'pickup', 'up'];
  for (const [crossingPickup, time, orderState] of [
    ['cancel', 500, 'waiting'],
    ['commit', 500, 'loaded'],
    ['finish', 501, 'loaded'],
  ]) {
    assert.deepEqual(observed(simulate(scenario, pickupActions, policy, { ...inspect, crossingPickup })), {
      ...pickupBase, time, orders: [orderState],
    });
  }

  // The company complaint starts at 480 and is unresolved at its deadline, 500.
  // Only the finish interpretation visits 501, when a deferred penalty is charged.
  const withComplaint = { ...scenario, complaints: [{ time: 480, destination: 'company' }] };
  for (const crossingPickup of ['cancel', 'commit', 'finish']) {
    const result = simulate(withComplaint, pickupActions, policy, { crossingPickup });
    const expires = Number(policy.expireAtDeadline || crossingPickup === 'finish');
    assert.deepEqual([result.complaintsSpawned, result.complaintsExpired, result.totalCost],
      [1, expires, 499 + 20 * expires]);
  }

  // A pickup ending exactly at t=500 does not cross the boundary.
  const exactPickup = simulate(scenario, [...atRestaurant(495), 'pickup', 'up'], policy, inspect);
  assert.deepEqual(observed(exactPickup), {
    ...pickupBase, time: 500, orders: ['loaded'], moves: 498, totalCost: 498, actionsUsed: 499,
  });
}

console.log('Verified exact-tick dropoff, crossing pickup, and exact-tick pickup against hand calculations under all 8 base policies.');
