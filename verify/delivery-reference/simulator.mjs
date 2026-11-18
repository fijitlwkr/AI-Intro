export const RESTAURANTS = Object.freeze({
  kimchi: Object.freeze([1, 2]),
  pizza: Object.freeze([8, 1]),
  tangsuyuk: Object.freeze([4, 8]),
});
export const DESTINATIONS = Object.freeze({
  home: Object.freeze([0, 7]),
  school: Object.freeze([6, 4]),
  park: Object.freeze([9, 5]),
  apartment: Object.freeze([7, 9]),
  company: Object.freeze([3, 3]),
});

const SIZE = 10;
const HORIZON = 500;
const INVALID_PENALTY = 10;
const EAST_WALLS = new Set(['0,4', '1,4', '2,4', '5,5', '6,5', '7,5', '2,8', '3,8', '8,2', '9,2']);
const SOUTH_WALLS = new Set(['2,0', '2,1', '2,2', '4,5', '4,6', '4,7', '6,7', '6,8', '7,2', '7,3', '0,5', '0,6']);
const MOVES = {
  up: [-1, 0],
  down: [1, 0],
  left: [0, -1],
  right: [0, 1],
};

function at([row, col], [otherRow, otherCol]) {
  return row === otherRow && col === otherCol;
}

function onMap(cell) {
  return Array.isArray(cell) && cell.length === 2 &&
    cell.every(value => Number.isInteger(value) && value >= 0 && value < SIZE);
}

function move([row, col], [dr, dc]) {
  const next = [row + dr, col + dc];
  if (!onMap(next)) return [row, col];
  const blocked = dc
    ? EAST_WALLS.has([row, Math.min(col, next[1])].join(','))
    : SOUTH_WALLS.has([Math.min(row, next[0]), col].join(','));
  return blocked ? [row, col] : next;
}

// Evaluate each unresolved boundary convention explicitly.
export const POLICIES = [];
for (const expireAtDeadline of [false, true]) {
  for (const countTerminalSpawn of [false, true]) {
    for (const successAtHorizon of [false, true]) {
      POLICIES.push(Object.freeze({ expireAtDeadline, countTerminalSpawn, successAtHorizon }));
    }
  }
}
Object.freeze(POLICIES);

export function simulate(scenario, actions, policy, {
  skipDropoffAtHorizon = false,
  crossingPickup = 'cancel',
  includeOrderStatuses = false,
  requireSpawnAfterDeadline = false,
  onComplaintEvent,
} = {}) {
  const {
    start, orders, complaints,
    menuBan = true, pickupTime = 2, complaintWindow = 20, complaintPenalty = 20,
  } = scenario;
  if (!POLICIES.some(candidate =>
    Object.keys(candidate).every(key => candidate[key] === policy?.[key]))) {
    throw new Error('An explicit boundary policy is required');
  }
  if (!['cancel', 'commit', 'finish'].includes(crossingPickup) ||
      (skipDropoffAtHorizon && policy.successAtHorizon)) {
    throw new Error('Inconsistent horizon options');
  }
  if (!onMap(start) || !Array.isArray(orders) || !orders.length || !Array.isArray(complaints) ||
      typeof menuBan !== 'boolean' ||
      ![1, 2, 4].includes(pickupTime) ||
      !Number.isInteger(complaintWindow) || complaintWindow < 1 ||
      !Number.isInteger(complaintPenalty) || complaintPenalty < 0) {
    throw new Error('Invalid scenario');
  }
  const state = orders.map(({ restaurant, destination }) => {
    if (!Object.hasOwn(RESTAURANTS, restaurant) || !Object.hasOwn(DESTINATIONS, destination)) {
      throw new Error('Unknown order location');
    }
    return { restaurant, destination, status: 'waiting', completedAt: null };
  });
  const minimumComplaintGap = complaintWindow + Number(requireSpawnAfterDeadline);
  for (const [index, { time, destination }] of complaints.entries()) {
    if (!Number.isInteger(time) || time < 0 || !Object.hasOwn(DESTINATIONS, destination) ||
        (index > 0 && time < complaints[index - 1].time + minimumComplaintGap)) {
      throw new Error('Invalid or overlapping complaint schedule');
    }
  }

  let position = start;
  let time = 0;
  let moves = 0;
  let invalidActions = 0;
  let completed = 0;
  let actionsUsed = 0;
  let status = 'incomplete';
  let spawned = 0;
  let resolved = 0;
  let expired = 0;
  let active = null;
  let deferredPenalty = null;

  function recordComplaintEvent(type, complaint) {
    onComplaintEvent?.({ time, type, scheduledAt: complaint.time, destination: complaint.destination });
  }

  function handleComplaints(includeSpawn) {
    if (deferredPenalty) {
      expired++;
      recordComplaintEvent('expire', deferredPenalty);
      deferredPenalty = null;
    }
    if (active && at(position, DESTINATIONS[active.destination])) {
      resolved++;
      recordComplaintEvent('resolve', active);
      active = null;
    } else if (active && time === active.time + complaintWindow) {
      if (policy.expireAtDeadline) {
        expired++;
        recordComplaintEvent('expire', active);
      } else {
        deferredPenalty = active;
      }
      active = null;
    }
    if (includeSpawn && complaints[spawned]?.time === time) {
      const complaint = complaints[spawned++];
      recordComplaintEvent('spawn', complaint);
      if (at(position, DESTINATIONS[complaint.destination])) {
        resolved++;
        recordComplaintEvent('resolve', complaint);
      } else {
        active = complaint;
      }
    }
  }

  handleComplaints(true);
  for (const action of actions) {
    if (status !== 'incomplete') break;
    actionsUsed++;
    let duration = 1;
    let nextPosition = position;
    let pickedUp = [];
    let delivered = [];
    if (Object.hasOwn(MOVES, action)) {
      moves++;
      nextPosition = move(position, MOVES[action]);
    } else if (action === 'pickup') {
      const eligible = state.filter(order =>
        order.status === 'waiting' && at(position, RESTAURANTS[order.restaurant]));
      const menus = new Set(state.filter(order => order.status === 'loaded').map(order => order.restaurant));
      for (const order of eligible) menus.add(order.restaurant);
      if (eligible.length && (!menuBan || menus.size < 3)) {
        duration = pickupTime;
        pickedUp = eligible;
      } else {
        invalidActions++;
      }
    } else if (action === 'dropoff') {
      delivered = state.filter(order =>
        order.status === 'loaded' && at(position, DESTINATIONS[order.destination]));
      if (!delivered.length) invalidActions++;
    } else {
      throw new Error(`Unknown action token: ${action}`);
    }

    const end = time + duration;
    const pickupCrossesHorizon = pickedUp.length > 0 && end > HORIZON;
    const terminalTick = pickupCrossesHorizon && crossingPickup === 'finish' ? end : HORIZON;
    while (time < end && time < terminalTick) {
      time++;
      if (time === end) {
        position = nextPosition;
        for (const order of pickedUp) order.status = 'loaded';
        if (time !== HORIZON || !skipDropoffAtHorizon) {
          for (const order of delivered) {
            order.status = 'done';
            order.completedAt = time;
            completed++;
          }
        }
      } else if (time === HORIZON && pickupCrossesHorizon && crossingPickup === 'commit') {
        for (const order of pickedUp) order.status = 'loaded';
      }
      const terminal = time === terminalTick || completed === state.length;
      handleComplaints(!terminal || policy.countTerminalSpawn);
      if (terminal) {
        status = completed === state.length && (time < HORIZON || policy.successAtHorizon)
          ? 'success'
          : 'failure';
      }
    }
  }

  const completionTimes = state.map(order => order.completedAt);
  const deliveryTimeSum = status === 'incomplete'
    ? null
    : completionTimes.reduce((sum, value) => sum + (value ?? HORIZON), 0);
  return {
    totalCost: moves + invalidActions * INVALID_PENALTY + expired * complaintPenalty,
    averageDeliveryTime: deliveryTimeSum === null ? null : deliveryTimeSum / orders.length,
    success: status === 'incomplete' ? null : status === 'success',
    complaintsSpawned: spawned,
    complaintsExpired: expired,
    complaintsResolved: resolved,
    complaintsPending: Number(active !== null) + Number(deferredPenalty !== null),
    status,
    time,
    actionsUsed,
    moves,
    invalidActions,
    position,
    completionTimes,
    ...(includeOrderStatuses ? { orderStatuses: state.map(order => order.status) } : {}),
  };
}
