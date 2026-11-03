import io
import os
import re
import unittest
from datetime import timedelta
from pathlib import Path
from PIL import Image, ImageDraw
from openpyxl import load_workbook

import app as fleet_app


def generate_pwa_and_sample_images():
    static_dir = Path(fleet_app.BASE) / 'static'
    uploads_dir = Path(fleet_app.app.config['UPLOAD_FOLDER'])
    static_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    for filename, size, pad in [
        ('pwa-192x192.png', 192, 20),
        ('pwa-512x512.png', 512, 54),
        ('pwa-maskable-512x512.png', 512, 84),
        ('apple-touch-icon.png', 180, 20),
    ]:
        img = Image.new('RGBA', (size, size), (11, 37, 69, 255))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [pad, pad, size - pad, size - pad],
            radius=max(12, size // 8),
            fill=(22, 115, 230, 255),
        )
        # Draw minimalist white truck silhouette inside safe zone
        c0 = int(size * 0.28)
        c1 = int(size * 0.72)
        mid = int(size * 0.56)
        draw.rectangle([c0, int(size * 0.38), int(size * 0.56), mid], fill=(255, 255, 255, 255))
        draw.rectangle([int(size * 0.58), int(size * 0.44), c1, mid], fill=(255, 255, 255, 255))
        r = max(4, size // 22)
        draw.ellipse([c0 + r, mid - r, c0 + 3 * r, mid + r], fill=(11, 37, 69, 255))
        draw.ellipse([c1 - 3 * r, mid - r, c1 - r, mid + r], fill=(11, 37, 69, 255))
        img.save(static_dir / filename, format='PNG')

    # Generate sample private fault photo
    fault_img = Image.new('RGB', (480, 320), (30, 41, 59))
    fdraw = ImageDraw.Draw(fault_img)
    fdraw.rectangle([20, 20, 460, 300], outline=(220, 38, 38), width=4)
    fdraw.ellipse([160, 80, 320, 240], fill=(71, 85, 105), outline=(226, 232, 240), width=6)
    fdraw.ellipse([205, 125, 275, 195], fill=(15, 23, 42), outline=(148, 163, 184), width=3)
    fault_img.save(uploads_dir / 'sample_tyre_fault.png', format='PNG')


class FleetPlatformAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path('/tmp/test_fleet_acceptance.db')
        if self.db_path.exists():
            self.db_path.unlink()
        fleet_app.app.config['TESTING'] = True
        fleet_app.app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        self.ctx = fleet_app.app.app_context()
        self.ctx.push()
        fleet_app.db.drop_all()
        fleet_app.seed_demo_data_if_empty()
        self.client = fleet_app.app.test_client()

    def tearDown(self):
        fleet_app.db.session.remove()
        fleet_app.db.drop_all()
        self.ctx.pop()
        if self.db_path.exists():
            self.db_path.unlink()

    def _get_csrf(self, html_bytes: bytes) -> str:
        m = re.search(r'name="csrf"\s+value="([^"]+)"', html_bytes.decode('utf-8'))
        self.assertIsNotNone(m, 'CSRF token input should exist in form')
        return m.group(1)

    def _login(self, eid: str, pw: str):
        res = self.client.get('/login')
        csrf = self._get_csrf(res.data)
        return self.client.post(
            '/login',
            data={'csrf': csrf, 'employee_id': eid, 'password': pw, 'remember': '1'},
            follow_redirects=True,
        )

    def _logout(self):
        res = self.client.get('/dashboard')
        csrf = self._get_csrf(res.data)
        return self.client.post('/logout', data={'csrf': csrf}, follow_redirects=True)

    def test_01_31_checklist_rows_and_protected_signoffs(self):
        items = fleet_app.Item.query.order_by(fleet_app.Item.order).all()
        self.assertEqual(len(items), 31)
        self.assertEqual(items[0].label, 'Light & Indicator')
        self.assertEqual(items[27].label, 'Driver Name')
        self.assertEqual(items[28].label, 'Driver Signature')
        self.assertEqual(items[29].label, 'Driver’s ROP EXP Date')
        self.assertEqual(items[30].label, 'Supervisor / PA Signature')

        # Log in as Admin and verify sign-off row 28 cannot be disabled
        self._login('EMP-ADMIN', 'AdminPass1234!')
        res = self.client.get('/admin/checklist')
        csrf = self._get_csrf(res.data)
        row28 = fleet_app.Item.query.filter_by(order=28).first()
        res_toggle = self.client.post(
            '/admin/checklist',
            data={'csrf': csrf, 'action': 'toggle', 'item_id': row28.id},
            follow_redirects=True,
        )
        self.assertIn(b'cannot be disabled', res_toggle.data)
        self.assertTrue(fleet_app.db.session.get(fleet_app.Item, row28.id).active)

    def test_02_no_public_registration_and_rbac_enforcement(self):
        # Confirm no public registration route exists
        for path in ('/register', '/signup', '/admin/register'):
            self.assertEqual(self.client.get(path).status_code, 404)

        # Supervisor cannot open /admin/users or /admin/vehicles or /admin/assign or unrelated vehicle KSA-7890
        self._login('EMP-SUP01', 'SuperPass1234!')
        self.assertEqual(self.client.get('/admin/users').status_code, 403)
        self.assertEqual(self.client.get('/admin/vehicles').status_code, 403)
        self.assertEqual(self.client.get('/admin/assign').status_code, 403)
        unrelated_v = fleet_app.Vehicle.query.filter_by(plate='KSA-7890').first()
        self.assertEqual(self.client.get(f'/vehicle/{unrelated_v.id}').status_code, 403)
        self._logout()

        # Driver cannot open /admin/users, /reports, /admin/export.xlsx, or unassigned vehicle
        self._login('EMP-DRV01', 'DriverPass1234!')
        self.assertEqual(self.client.get('/admin/users').status_code, 403)
        self.assertEqual(self.client.get('/reports').status_code, 403)
        self.assertEqual(self.client.get('/admin/export.xlsx').status_code, 403)
        unassigned_v = fleet_app.Vehicle.query.filter_by(plate='KSA-5678').first()
        self.assertEqual(self.client.get(f'/inspect/{unassigned_v.id}').status_code, 403)
        self._logout()

    def test_03_one_driver_and_one_vehicle_per_day_assignment_rules(self):
        self._login('EMP-ADMIN', 'AdminPass1234!')
        res = self.client.get('/admin/assign')
        csrf = self._get_csrf(res.data)
        v1 = fleet_app.Vehicle.query.filter_by(plate='KSA-1245').first()
        v4 = fleet_app.Vehicle.query.filter_by(plate='KSA-3456').first()
        drv1 = fleet_app.User.query.filter_by(employee_id='EMP-DRV01').first()
        drv2 = fleet_app.User.query.filter_by(employee_id='EMP-DRV02').first()
        cur_day = fleet_app.today().isoformat()

        # drv1 is already assigned to v1 today -> assigning drv1 to v4 today must fail
        res1 = self.client.post(
            '/admin/assign',
            data={'csrf': csrf, 'vehicle_id': v4.id, 'driver_id': drv1.id, 'day': cur_day},
            follow_redirects=True,
        )
        self.assertIn(b'Each driver can have only one vehicle per date', res1.data)

        # Test one-driver-per-vehicle on a date where drv1 is assigned to v1 and drv2 has no vehicle yet
        future_day = (fleet_app.today() + timedelta(days=5)).isoformat()
        self.client.post(
            '/admin/assign',
            data={'csrf': csrf, 'vehicle_id': v1.id, 'driver_id': drv1.id, 'day': future_day},
            follow_redirects=True,
        )
        res2 = self.client.post(
            '/admin/assign',
            data={'csrf': csrf, 'vehicle_id': v1.id, 'driver_id': drv2.id, 'day': future_day},
            follow_redirects=True,
        )
        self.assertIn(b'Each vehicle can have only one driver per date', res2.data)

    def test_04_complete_inspection_fault_photo_supervisor_approval_and_excel(self):
        # Driver 1 scans QR for KSA-1245 and submits inspection with 1 failed item + PNG photo
        self._login('EMP-DRV01', 'DriverPass1234!')
        v1 = fleet_app.Vehicle.query.filter_by(plate='KSA-1245').first()
        scan_res = self.client.get(f'/scan/{v1.qr_token}', follow_redirects=False)
        self.assertEqual(scan_res.status_code, 302)
        self.assertIn(f'/inspect/{v1.id}', scan_res.headers['Location'])

        form_res = self.client.get(f'/inspect/{v1.id}')
        csrf = self._get_csrf(form_res.data)
        items = fleet_app.Item.query.filter_by(active=True).order_by(fleet_app.Item.order).all()
        post_data = {
            'csrf': csrf,
            'start_km': '41350',
            'odometer': '41500',
            'driver_signature': 'Ahmed Khan',
            'license_expiry': '2028-05-01',
            'notes': 'Horn intermittent during check',
            'attestation': 'yes',
        }
        horn_item = None
        for it in items:
            if it.order <= 27:
                if it.order == 4:  # Horn
                    post_data[f'item_{it.id}'] = 'fail'
                    post_data[f'remark_{it.id}'] = 'Horn button contact worn'
                    horn_item = it
                else:
                    post_data[f'item_{it.id}'] = 'pass'

        img = Image.new('RGB', (64, 64), (200, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        post_data['photos'] = (buf, 'horn_defect.png')

        sub_res = self.client.post(
            f'/inspect/{v1.id}',
            data=post_data,
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        self.assertEqual(sub_res.status_code, 200)
        insp = fleet_app.Inspection.query.filter_by(vehicle_id=v1.id, day=fleet_app.today()).first()
        self.assertIsNotNone(insp)
        fault = fleet_app.Fault.query.filter_by(inspection_id=insp.id).first()
        self.assertIsNotNone(fault)
        self.assertEqual(fault.description, 'Horn button contact worn')
        photo = fleet_app.Photo.query.filter_by(fault_id=fault.id).first()
        self.assertIsNotNone(photo)

        # Driver 2 cannot view Driver 1's private fault photo
        self._logout()
        self._login('EMP-DRV02', 'DriverPass1234!')
        self.assertEqual(self.client.get(f'/fault-photo/{photo.filename}').status_code, 403)
        self._logout()

        # Supervisor 1 (assigned to KSA-1245) CAN view the photo, approve the inspection, and resolve the fault
        self._login('EMP-SUP01', 'SuperPass1234!')
        self.assertEqual(self.client.get(f'/fault-photo/{photo.filename}').status_code, 200)
        sup_csrf = self._get_csrf(self.client.get('/dashboard').data)
        app_res = self.client.post(
            f'/inspection/{insp.id}/approve',
            data={'csrf': sup_csrf},
            follow_redirects=True,
        )
        self.assertEqual(app_res.status_code, 200)
        self.assertEqual(fleet_app.db.session.get(fleet_app.Inspection, insp.id).status, 'approved')

        res_fault = self.client.post(
            f'/fault/{fault.id}/resolve',
            data={'csrf': sup_csrf, 'action_taken': 'Replaced horn relay and tested OK'},
            follow_redirects=True,
        )
        self.assertEqual(res_fault.status_code, 200)
        self.assertEqual(fleet_app.db.session.get(fleet_app.Fault, fault.id).status, 'resolved')

        # Switch language to Arabic and test translated Excel export & RTL layout
        rtl_res = self.client.get('/language/ar', follow_redirects=True)
        self.assertIn(b'dir="rtl"', rtl_res.data)
        xl_res = self.client.get('/admin/export.xlsx')
        self.assertEqual(xl_res.status_code, 200)
        wb = load_workbook(io.BytesIO(xl_res.data))
        self.assertIn('الفحوصات', wb.sheetnames)
        self.assertEqual(len(wb.sheetnames), 6)

    def test_05_offline_sync_api_and_duplicate_protection(self):
        # Assign KSA-3456 to Driver 3 for today and sync via JSON offline endpoint
        self._login('EMP-ADMIN', 'AdminPass1234!')
        v4 = fleet_app.Vehicle.query.filter_by(plate='KSA-3456').first()
        drv4 = fleet_app.User.query.filter_by(employee_id='EMP-DRV04').first()
        # Update drv4's today assignment or test with drv1 on KSA-1245
        self._logout()

        self._login('EMP-DRV01', 'DriverPass1234!')
        v1 = fleet_app.Vehicle.query.filter_by(plate='KSA-1245').first()
        csrf = self._get_csrf(self.client.get(f'/inspect/{v1.id}').data)
        items = fleet_app.Item.query.filter_by(active=True).order_by(fleet_app.Item.order).all()
        answers = {str(it.id): 'pass' for it in items if it.order <= 27}
        payload = {
            'vehicle_id': v1.id,
            'start_km': 41350,
            'odometer': 41480,
            'notes': 'Synced from offline IndexedDB queue',
            'answers': answers,
            'remarks': {},
            'driver_signature': 'Ahmed Khan',
            'license_expiry': '2028-01-15',
            'attestation': 'yes',
        }
        sync1 = self.client.post(
            '/api/inspections',
            json=payload,
            headers={'X-CSRF-Token': csrf},
        )
        self.assertEqual(sync1.status_code, 200)
        data1 = sync1.get_json()
        self.assertTrue(data1['ok'])
        self.assertFalse(data1['duplicate'])

        # Second sync of the same queued payload must be caught as duplicate
        sync2 = self.client.post(
            '/api/inspections',
            json=payload,
            headers={'X-CSRF-Token': csrf},
        )
        self.assertEqual(sync2.status_code, 200)
        data2 = sync2.get_json()
        self.assertTrue(data2['ok'])
        self.assertTrue(data2['duplicate'])


if __name__ == '__main__':
    generate_pwa_and_sample_images()
    unittest.main(verbosity=2)
