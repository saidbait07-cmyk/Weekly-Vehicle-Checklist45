import test from 'node:test';
import assert from 'node:assert/strict';
import {
  AUTHORITATIVE_CHECKLIST_ITEMS,
  isRtlLanguage,
  isProtectedSignOffRow,
  validateAssignmentRules,
  summarizeChecklistResponses,
  canRoleAccessRoute,
} from './inspectionRules';

test('authoritative checklist contains all 31 rows in exact paper form order', () => {
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS.length, 31);
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[0], 'Light & Indicator');
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[9], 'Tyres, nut & bolts');
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[26], 'Driver’s Mandatory Training Cards');
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[27], 'Driver Name');
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[28], 'Driver Signature');
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[29], 'Driver’s ROP EXP Date');
  assert.equal(AUTHORITATIVE_CHECKLIST_ITEMS[30], 'Supervisor / PA Signature');
});

test('sign-off rows 28-31 are protected from disabling', () => {
  assert.equal(isProtectedSignOffRow(27), false);
  assert.equal(isProtectedSignOffRow(28), true);
  assert.equal(isProtectedSignOffRow(29), true);
  assert.equal(isProtectedSignOffRow(30), true);
  assert.equal(isProtectedSignOffRow(31), true);
  assert.equal(isProtectedSignOffRow(32), false);
});

test('one-driver-per-day and one-vehicle-per-day assignment rules', () => {
  const existing = [{ vehicleId: 101, driverId: 501, day: '2026-10-21' }];

  // Same driver assigned to a second vehicle on the same date -> rejected
  const secondVehicleForDriver = validateAssignmentRules(existing, {
    vehicleId: 102,
    driverId: 501,
    day: '2026-10-21',
  });
  assert.equal(secondVehicleForDriver.valid, false);
  assert.equal(secondVehicleForDriver.reason, 'driver_already_assigned');

  // Second driver assigned to the same vehicle on the same date -> rejected
  const secondDriverForVehicle = validateAssignmentRules(existing, {
    vehicleId: 101,
    driverId: 502,
    day: '2026-10-21',
  });
  assert.equal(secondDriverForVehicle.valid, false);
  assert.equal(secondDriverForVehicle.reason, 'vehicle_already_assigned');

  // Different date -> allowed
  const nextDayAssignment = validateAssignmentRules(existing, {
    vehicleId: 102,
    driverId: 501,
    day: '2026-10-22',
  });
  assert.equal(nextDayAssignment.valid, true);
});

test('checklist summary counts OK, Not OK, N/A and automatic fault creation count', () => {
  const summary = summarizeChecklistResponses(['pass', 'pass', 'fail', 'na', 'fail']);
  assert.equal(summary.total, 5);
  assert.equal(summary.passed, 2);
  assert.equal(summary.failed, 2);
  assert.equal(summary.na, 1);
  assert.equal(summary.createsFaults, 2);
});

test('RTL language detection and role route access permissions', () => {
  assert.equal(isRtlLanguage('en'), false);
  assert.equal(isRtlLanguage('hi'), false);
  assert.equal(isRtlLanguage('ar'), true);
  assert.equal(isRtlLanguage('ur'), true);

  assert.equal(canRoleAccessRoute('admin', '/admin/users'), true);
  assert.equal(canRoleAccessRoute('supervisor', '/admin/users'), false);
  assert.equal(canRoleAccessRoute('driver', '/admin/users'), false);
  assert.equal(canRoleAccessRoute('driver', '/reports'), false);
  assert.equal(canRoleAccessRoute('supervisor', '/reports'), true);
});
