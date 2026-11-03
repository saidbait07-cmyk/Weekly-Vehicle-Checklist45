export const AUTHORITATIVE_CHECKLIST_ITEMS: readonly string[] = [
  'Light & Indicator',
  'Mirrors',
  'Blind spot mirror',
  'Horn',
  'Fuel',
  'Seat Belt',
  'Communication Radio / Tape',
  'A/C in Vehicle',
  'Body Damage',
  'Tyres, nut & bolts',
  'Load Restraint',
  'Battery',
  'Oil Level',
  'Water Level',
  'Steering',
  'Wipers & Wind Screen',
  'Brakes',
  'First Aid Box',
  'Fire Extinguishers',
  'Jack, Tools, Triangle',
  'Vehicle registration papers',
  'Ladder condition',
  'IVMS',
  'Housekeeping',
  '360 degree Walk around',
  'RAS Sticker OPAL',
  'Driver’s Mandatory Training Cards',
  'Driver Name',
  'Driver Signature',
  'Driver’s ROP EXP Date',
  'Supervisor / PA Signature',
];

export type SupportedLanguage = 'en' | 'ar' | 'hi' | 'ur';
export type UserRole = 'admin' | 'supervisor' | 'driver';
export type CheckResult = 'pass' | 'fail' | 'na';

export interface AssignmentRecord {
  vehicleId: number;
  driverId: number;
  day: string;
}

export function isRtlLanguage(lang: SupportedLanguage): boolean {
  return lang === 'ar' || lang === 'ur';
}

export function isProtectedSignOffRow(order: number): boolean {
  return order >= 28 && order <= 31;
}

export function validateAssignmentRules(
  existingAssignments: AssignmentRecord[],
  newAssignment: AssignmentRecord
): { valid: boolean; reason?: 'driver_already_assigned' | 'vehicle_already_assigned' } {
  for (const a of existingAssignments) {
    if (a.day !== newAssignment.day) continue;
    if (a.driverId === newAssignment.driverId && a.vehicleId !== newAssignment.vehicleId) {
      return { valid: false, reason: 'driver_already_assigned' };
    }
    if (a.vehicleId === newAssignment.vehicleId && a.driverId !== newAssignment.driverId) {
      return { valid: false, reason: 'vehicle_already_assigned' };
    }
  }
  return { valid: true };
}

export function summarizeChecklistResponses(results: CheckResult[]): {
  total: number;
  passed: number;
  failed: number;
  na: number;
  createsFaults: number;
} {
  let passed = 0;
  let failed = 0;
  let na = 0;
  for (const r of results) {
    if (r === 'pass') passed++;
    else if (r === 'fail') failed++;
    else if (r === 'na') na++;
  }
  return {
    total: results.length,
    passed,
    failed,
    na,
    createsFaults: failed,
  };
}

export function canRoleAccessRoute(role: UserRole, routePrefix: string): boolean {
  if (role === 'admin') return true;
  if (routePrefix.startsWith('/admin/')) return false;
  if (role === 'supervisor') {
    return (
      routePrefix === '/dashboard' ||
      routePrefix === '/faults' ||
      routePrefix === '/reports' ||
      routePrefix === '/search' ||
      routePrefix === '/export'
    );
  }
  // driver
  return (
    routePrefix === '/dashboard' ||
    routePrefix === '/inspect' ||
    routePrefix === '/scan' ||
    routePrefix === '/faults' ||
    routePrefix === '/search'
  );
}
