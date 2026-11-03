import io
import os
import secrets
import json
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import click
from flask import (
    Flask, request, redirect, url_for, session, abort, g,
    render_template, flash, send_file, send_from_directory, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import qrcode

BASE = Path(__file__).resolve().parent


def resolve_timezone(raw_tz: str | None):
    candidate = (raw_tz or '').strip()
    if candidate:
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, KeyError, ValueError):
            pass
    try:
        return ZoneInfo('Asia/Muscat')
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return timezone(timedelta(hours=4))


APP_TZ = resolve_timezone(os.getenv('APP_TIMEZONE', 'Asia/Muscat'))


def today() -> date:
    return datetime.now(APP_TZ).date()


def normalize_db_url(raw_url: str | None) -> str:
    default_sqlite = 'sqlite:///' + str(BASE / 'fleet.db')
    if not raw_url:
        return default_sqlite
    cleaned = raw_url.strip()
    if cleaned.startswith('postgres://'):
        return cleaned.replace('postgres://', 'postgresql+psycopg2://', 1)
    valid_prefixes = (
        'sqlite://',
        'postgresql://',
        'postgresql+psycopg2://',
        'mysql://',
        'mysql+pymysql://',
    )
    if not cleaned.startswith(valid_prefixes):
        return default_sqlite
    return cleaned


def resolve_secret_key(raw_key: str | None) -> str:
    default_secret = 'dev-fleet-secret-key-change-in-production-9f8e7d6c5b4a'
    if not raw_key:
        return default_secret
    cleaned = raw_key.strip()
    if len(cleaned) < 8 or cleaned in ('1234', 'replace-this-with-a-long-random-secret'):
        return default_secret
    return cleaned


app = Flask(
    __name__,
    template_folder=str(BASE / 'templates'),
    static_folder=str(BASE / 'static'),
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SECRET_KEY=resolve_secret_key(os.getenv('SECRET_KEY')),
    SQLALCHEMY_DATABASE_URI=normalize_db_url(os.getenv('DATABASE_URL')),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,  # 12 MB max request payload
    MAX_SINGLE_PHOTO_BYTES=5 * 1024 * 1024,  # 5 MB per photo
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('HTTPS', '0') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)
app.config['UPLOAD_FOLDER'] = str(BASE / 'private_uploads')
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
db = SQLAlchemy(app)

# Authoritative 31 rows from the paper checklist in exact order
CHECKLIST = [
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
]

CHECKLIST_TRANSLATIONS = {
    'ar': [
        'الأضواء والإشارات', 'المرايا', 'مرآة النقطة العمياء', 'البوق', 'الوقود',
        'حزام الأمان', 'جهاز الاتصال / الراديو', 'مكيف الهواء في المركبة', 'أضرار الهيكل',
        'الإطارات والصواميل والبراغي', 'تثبيت الحمولة', 'البطارية', 'مستوى الزيت',
        'مستوى الماء', 'المقود (التوجيه)', 'المساحات والزجاج الأمامي', 'الفرامل',
        'صندوق الإسعافات الأولية', 'طفايات الحريق', 'الرافعة والأدوات ومثلث التحذير',
        'أوراق تسجيل المركبة (الملكية)', 'حالة السلم', 'نظام مراقبة المركبة IVMS',
        'نظافة وترتيب المركبة', 'الفحص الدائري 360 درجة', 'ملصق فحص RAS OPAL',
        'بطاقات التدريب الإلزامي للسائق', 'اسم السائق', 'توقيع السائق',
        'تاريخ انتهاء رخصة شرطة عمان السلطانية (ROP)', 'توقيع المشرف / المساعد الإداري'
    ],
    'hi': [
        'लाइट और इंडिकेटर', 'दर्पण (मिरर)', 'ब्लाइंड स्पॉट दर्पण', 'हॉर्न', 'ईंधन (फ़्यूल)',
        'सीट बेल्ट', 'कम्युनिकेशन रेडियो / टेप', 'वाहन में एसी (A/C)', 'बॉडी क्षति (डैमेज)',
        'टायर, नट और बोल्ट', 'लोड सुरक्षा (रेस्ट्रेंट)', 'बैटरी', 'ऑयल स्तर',
        'पानी का स्तर', 'स्टीयरिंग', 'वाइपर और विंडस्क्रीन', 'ब्रेक',
        'प्राथमिक चिकित्सा बॉक्स (फर्स्ट एड)', 'अग्निशामक यंत्र', 'जैक, औज़ार, सुरक्षा त्रिकोण',
        'वाहन पंजीकरण दस्तावेज़', 'सीढ़ी की स्थिति', 'IVMS प्रणाली',
        'वाहन की साफ-सफाई (हाउसकीपिंग)', '360 डिग्री चारों ओर जांच', 'RAS स्टिकर OPAL',
        'ड्राइवर के अनिवार्य प्रशिक्षण कार्ड', 'ड्राइवर का नाम', 'ड्राइवर के हस्ताक्षर',
        'ड्राइवर ROP लाइसेंस समाप्ति तिथि', 'सुपरवाइज़र / PA हस्ताक्षर'
    ],
    'ur': [
        'لائٹ اور اشارے', 'آئینے (مررز)', 'بلائنڈ اسپاٹ آئینہ', 'ہارن', 'ایندھن (فیول)',
        'سیٹ بیلٹ', 'کمیونیکیشن ریڈیو / ٹیپ', 'گاڑی میں اے سی (A/C)', 'باڈی کا نقصان',
        'ٹائر، نٹ اور بولٹ', 'لوڈ کی حفاظت', 'بیٹری', 'آئل لیول',
        'پانی کی سطح', 'اسٹیئرنگ', 'وائپر اور ونڈ اسکرین', 'بریک',
        'فرسٹ ایڈ باکس', 'آگ بجھانے والے آلات', 'جیک، اوزار، تکون',
        'گاڑی کے رجسٹریشن کاغذات', 'سیڑھی کی حالت', 'IVMS سسٹم',
        'گاڑی کی صفائی (ہاؤس کیپنگ)', '360 ڈگری گاڑی کا معائنہ', 'RAS اسٹیکر OPAL',
        'ڈرائیور کے لازمی تربیتی کارڈ', 'ڈرائیور کا نام', 'ڈرائیور کے دستخط',
        'ڈرائیور کے ROP لائسنس کی میعاد', 'سپروائزر / PA کے دستخط'
    ]
}

TXT = {
    'en': {
        'app': 'Smart Vehicle Inspection',
        'subtitle': '& Fleet Management System',
        'login': 'Employee Login',
        'employee': 'Employee ID',
        'password': 'Password',
        'remember': 'Remember me',
        'sign_in': 'Sign In',
        'dashboard': 'Dashboard',
        'users': 'Employees',
        'vehicles': 'Vehicles',
        'my_vehicles': 'My Vehicles',
        'inspections': 'Daily Inspections',
        'my_inspections': 'My Inspections',
        'faults': 'Faults & Maintenance',
        'fault_reports': 'Fault Reports',
        'reports': 'Reports',
        'excel_export': 'Excel Export',
        'settings': 'Inspection Forms',
        'audit_log': 'Audit Log',
        'search': 'Search',
        'logout': 'Logout',
        'admin': 'Admin Dashboard',
        'admin_sub': 'Manage your fleet, employees and inspections',
        'supervisor': 'Supervisor Dashboard',
        'supervisor_sub': 'Monitor assigned vehicles, driver inspections and fault resolution',
        'driver': 'Driver Dashboard',
        'driver_sub': 'Complete your daily vehicle inspection checklist',
        'register_user': 'Register Employee',
        'name': 'Full Name',
        'role': 'Role',
        'initial_password': 'Initial Password (12+ chars)',
        'save': 'Save',
        'status': 'Status',
        'active': 'Active',
        'inactive': 'Inactive',
        'actions': 'Actions',
        'deactivate': 'Deactivate',
        'reactivate': 'Reactivate',
        'plate': 'Vehicle No.',
        'type': 'Vehicle Type',
        'model_desc': 'Model & Description',
        'add_vehicle': 'Add Vehicle',
        'assign': 'Assign Driver',
        'driver_user': 'Driver',
        'drivers': 'Active Drivers',
        'date': 'Date',
        'odometer': 'Closing Odometer (km)',
        'start_km': 'Starting Odometer (km)',
        'end_km': 'Closing KM',
        'inspection': 'Daily Inspection Checklist',
        'item': 'Inspection Item',
        'result': 'Result',
        'pass': 'OK',
        'fail': 'Not OK',
        'na': 'N/A',
        'passed_label': 'Passed',
        'failed_label': 'Failed',
        'pending_label': 'Pending',
        'remark': 'Add remark / defect description...',
        'action_taken': 'Action taken to resolve fault',
        'photo': 'Photos of Issues',
        'add_photo': 'Add Photo',
        'submit': 'Submit Inspection',
        'save_draft': 'Save Draft',
        'pending': 'Pending Sync',
        'synced': 'Synced',
        'today': 'Today',
        'total_vehicles': 'Total Vehicles',
        'assigned_vehicles': 'Assigned Vehicles',
        'total_employees': 'Total Employees',
        'today_inspections': 'Inspections Today',
        'open_faults': 'Open Faults',
        'pending_faults': 'Pending Faults',
        'recent': 'Recent Inspections',
        'no_data': 'No records found.',
        'search_hint': 'Search by Vehicle No. (e.g. KSA-1245) or Employee ID...',
        'scan': 'Scan Vehicle QR Code',
        'scan_hint': 'Scan the QR code on the vehicle or enter the vehicle number assigned to you today.',
        'manual': 'Enter Vehicle No.',
        'search_vehicle': 'Open Inspection',
        'view': 'View',
        'export': 'Export Excel',
        'access_denied': 'Access Denied: You do not have permission to view or modify this resource.',
        'created': 'Employee account created successfully.',
        'saved': 'Changes saved successfully.',
        'vehicle_added': 'Vehicle registered successfully.',
        'assigned': 'Driver assignment saved for selected date.',
        'checklist_help': 'Mark every row (OK, Not OK, or N/A). Marking Not OK automatically creates a fault record.',
        'language': 'Language',
        'english': 'English',
        'arabic': 'عربي',
        'hindi': 'हिंदी',
        'urdu': 'اردو',
        'online': 'Online',
        'offline': 'Offline Mode',
        'account_notice': 'Only an authenticated Admin can register employee accounts and assign roles. Public self-registration is disabled.',
        'invalid_login': 'Invalid Employee ID, password, or deactivated account.',
        'initial_admin': 'Run `flask --app app create-admin` to provision the first administrator.',
        'qr': 'QR Code',
        'download_qr': 'Download QR',
        'vehicle_history': 'Vehicle Inspection History',
        'vehicle_info': 'Vehicle Information',
        'inspection_summary': 'Inspection Summary',
        'total_items': 'Total Items',
        'final_status': 'Final Status',
        'fault_status': 'Fault Status',
        'open': 'Open',
        'closed': 'Resolved',
        'resolve': 'Resolve Fault',
        'details': 'Fault Description',
        'no_assignments': 'No vehicle is assigned to you for today.',
        'notes': 'Final Inspection Remarks / Notes',
        'license_expiry': "Driver's ROP EXP Date",
        'attestation': 'I confirm that I have inspected the vehicle and recorded all findings accurately.',
        'all_items': 'Checklist Items',
        'add_item': 'Add Checklist Item',
        'update_item': 'Update Label',
        'item_label': 'Checklist Item Label (English)',
        'enabled': 'Enabled',
        'disabled': 'Disabled',
        'activity': 'Audit Events',
        'refresh': 'Refresh',
        'driver_name': 'Driver Name',
        'driver_signature': 'Driver Signature',
        'supervisor_sign': 'Supervisor / PA Signature',
        'supervisor_note': 'Recorded through the Supervisor approval workflow.',
        'pending_approval': 'Pending Approval',
        'approved': 'Approved',
        'approve': 'Approve & Sign Off',
        'quick_actions': 'Quick Operations',
        'inspection_status': 'Inspection Status',
        'monthly_inspections': 'Monthly Inspections',
        'weekly_inspections': 'Inspections This Week',
        'vehicle_status': 'Vehicle Status',
        'good_vehicles': 'Good',
        'minor_issues': 'Minor Issues',
        'major_issues': 'Major Issues',
        'install_app': 'Install App',
        'offline_queue_title': 'Offline Inspection Queue',
        'sync_now': 'Sync Queued Inspections',
        'photo_offline_notice': 'Note: Fault photos require an active internet connection and cannot be uploaded offline.',
    },
    'ar': {
        'app': 'نظام فحص المركبات الذكي',
        'subtitle': 'وإدارة الأسطول',
        'login': 'تسجيل دخول الموظفين',
        'employee': 'الرقم الوظيفي',
        'password': 'كلمة المرور',
        'remember': 'تذكرني',
        'sign_in': 'دخول',
        'dashboard': 'لوحة التحكم',
        'users': 'الموظفون',
        'vehicles': 'المركبات',
        'my_vehicles': 'مركباتي المسندة',
        'inspections': 'الفحوصات اليومية',
        'my_inspections': 'فحوصاتي',
        'faults': 'الأعطال والصيانة',
        'fault_reports': 'بلاغات الأعطال',
        'reports': 'التقارير',
        'excel_export': 'تصدير Excel',
        'settings': 'نماذج الفحص',
        'audit_log': 'سجل التدقيق',
        'search': 'بحث',
        'logout': 'تسجيل الخروج',
        'admin': 'لوحة تحكم المسؤول',
        'admin_sub': 'إدارة الأسطول والموظفين والفحوصات اليومية',
        'supervisor': 'لوحة تحكم المشرف',
        'supervisor_sub': 'متابعة المركبات المسندة واعتماد الفحوصات ومعالجة الأعطال',
        'driver': 'لوحة تحكم السائق',
        'driver_sub': 'أكمل قائمة الفحص اليومي للمركبة المسندة إليك',
        'register_user': 'تسجيل موظف جديد',
        'name': 'الاسم الكامل',
        'role': 'الصلاحية / الدور',
        'initial_password': 'كلمة المرور الأولية (12 حرفاً فأكثر)',
        'save': 'حفظ',
        'status': 'الحالة',
        'active': 'نشط',
        'inactive': 'موقوف',
        'actions': 'الإجراءات',
        'deactivate': 'إيقاف الحساب',
        'reactivate': 'إعادة التفعيل',
        'plate': 'رقم المركبة',
        'type': 'نوع المركبة',
        'model_desc': 'الطراز والوصف',
        'add_vehicle': 'إضافة مركبة',
        'assign': 'تعيين سائق',
        'driver_user': 'السائق',
        'drivers': 'السائقون النشطون',
        'date': 'التاريخ',
        'odometer': 'عداد المسافة النهائي (كم)',
        'start_km': 'عداد البداية (كم)',
        'end_km': 'عداد النهاية',
        'inspection': 'قائمة الفحص اليومي للمركبة',
        'item': 'بند الفحص',
        'result': 'النتيجة',
        'pass': 'سليم (OK)',
        'fail': 'غير سليم (Not OK)',
        'na': 'لا ينطبق (N/A)',
        'passed_label': 'ناجح',
        'failed_label': 'أعطال',
        'pending_label': 'قيد الانتظار',
        'remark': 'أضف ملاحظة أو وصف العطل...',
        'action_taken': 'الإجراء المتخذ لإصلاح العطل',
        'photo': 'صور الأعطال',
        'add_photo': 'إضافة صورة',
        'submit': 'إرسال الفحص',
        'save_draft': 'حفظ مسودة',
        'pending': 'بانتظار المزامنة',
        'synced': 'تمت المزامنة',
        'today': 'اليوم',
        'total_vehicles': 'إجمالي المركبات',
        'assigned_vehicles': 'المركبات المسندة',
        'total_employees': 'إجمالي الموظفين',
        'today_inspections': 'فحوصات اليوم',
        'open_faults': 'الأعطال المفتوحة',
        'pending_faults': 'أعطال قيد المعالجة',
        'recent': 'أحدث الفحوصات',
        'no_data': 'لا توجد سجلات مطابقة.',
        'search_hint': 'ابحث برقم المركبة أو الرقم الوظيفي...',
        'scan': 'مسح رمز QR للمركبة',
        'scan_hint': 'امسح رمز QR الملصق على المركبة أو أدخل رقم المركبة المسندة إليك اليوم.',
        'manual': 'أدخل رقم المركبة',
        'search_vehicle': 'فتح الفحص',
        'view': 'عرض',
        'export': 'تصدير Excel',
        'access_denied': 'تم رفض الوصول: ليس لديك صلاحية لعرض هذا المورد أو تعديله.',
        'created': 'تم إنشاء حساب الموظف بنجاح.',
        'saved': 'تم حفظ التغييرات بنجاح.',
        'vehicle_added': 'تمت إضافة المركبة بنجاح.',
        'assigned': 'تم حفظ تعيين السائق للتاريخ المحدد.',
        'checklist_help': 'حدد حالة كل بند (سليم، غير سليم، لا ينطبق). البنود غير السليمة تنشئ بلاغ عطل تلقائياً.',
        'language': 'اللغة',
        'english': 'English',
        'arabic': 'عربي',
        'hindi': 'हिंदी',
        'urdu': 'اردو',
        'online': 'متصل',
        'offline': 'وضع عدم الاتصال',
        'account_notice': 'المسؤول فقط يمكنه إنشاء حسابات الموظفين وتحديد الأدوار. التسجيل الذاتي غير متاح.',
        'invalid_login': 'الرقم الوظيفي أو كلمة المرور غير صحيحة أو الحساب موقوف.',
        'initial_admin': 'نفّذ الأمر `flask --app app create-admin` لإنشاء أول مسؤول.',
        'qr': 'رمز QR',
        'download_qr': 'تنزيل QR',
        'vehicle_history': 'سجل فحوصات المركبة',
        'vehicle_info': 'بيانات المركبة',
        'inspection_summary': 'ملخص الفحص',
        'total_items': 'إجمالي البنود',
        'final_status': 'الحالة النهائية',
        'fault_status': 'حالة العطل',
        'open': 'مفتوح',
        'closed': 'تم الحل',
        'resolve': 'إغلاق العطل',
        'details': 'وصف العطل',
        'no_assignments': 'لا توجد مركبة معيّنة لك لهذا اليوم.',
        'notes': 'ملاحظات الفحص النهائية',
        'license_expiry': 'تاريخ انتهاء رخصة القيادة (ROP)',
        'attestation': 'أقرّ بأنني فحصت المركبة وسجلت جميع البيانات بدقة وأمانة.',
        'all_items': 'بنود قائمة الفحص',
        'add_item': 'إضافة بند فحص',
        'update_item': 'تحديث المسمى',
        'item_label': 'مسمى بند الفحص',
        'enabled': 'مفعّل',
        'disabled': 'معطّل',
        'activity': 'سجل التدقيق والنشاط',
        'refresh': 'تحديث',
        'driver_name': 'اسم السائق',
        'driver_signature': 'توقيع السائق',
        'supervisor_sign': 'توقيع المشرف / المساعد',
        'supervisor_note': 'يُسجّل عبر سير عمل اعتماد المشرف.',
        'pending_approval': 'بانتظار اعتماد المشرف',
        'approved': 'معتمد',
        'approve': 'اعتماد وتوقيع',
        'quick_actions': 'إجراءات سريعة',
        'inspection_status': 'حالة الفحوصات',
        'monthly_inspections': 'الفحوصات الشهرية',
        'weekly_inspections': 'فحوصات هذا الأسبوع',
        'vehicle_status': 'حالة المركبات',
        'good_vehicles': 'سليمة',
        'minor_issues': 'ملاحظات بسيطة',
        'major_issues': 'أعطال رئيسية',
        'install_app': 'تثبيت التطبيق',
        'offline_queue_title': 'طابور الفحوصات دون اتصال',
        'sync_now': 'مزامنة الفحوصات المحفوظة',
        'photo_offline_notice': 'ملاحظة: رفع صور الأعطال يتطلب اتصالاً بالإنترنت ولا يمكن رفعه دون اتصال.',
    },
    'hi': {
        'app': 'स्मार्ट वाहन निरीक्षण',
        'subtitle': 'एवं बेड़ा प्रबंधन प्रणाली',
        'login': 'कर्मचारी लॉगिन',
        'employee': 'कर्मचारी ID',
        'password': 'पासवर्ड',
        'remember': 'मुझे याद रखें',
        'sign_in': 'साइन इन करें',
        'dashboard': 'डैशबोर्ड',
        'users': 'कर्मचारी',
        'vehicles': 'वाहन',
        'my_vehicles': 'मेरे वाहन',
        'inspections': 'दैनिक निरीक्षण',
        'my_inspections': 'मेरे निरीक्षण',
        'faults': 'खराबी और रखरखाव',
        'fault_reports': 'खराबी रिपोर्ट',
        'reports': 'रिपोर्ट',
        'excel_export': 'Excel निर्यात',
        'settings': 'निरीक्षण फ़ॉर्म',
        'audit_log': 'ऑडिट लॉग',
        'search': 'खोजें',
        'logout': 'लॉग आउट',
        'admin': 'एडमिन डैशबोर्ड',
        'admin_sub': 'अपने वाहन बेड़े, कर्मचारियों और दैनिक निरीक्षणों का प्रबंधन करें',
        'supervisor': 'सुपरवाइज़र डैशबोर्ड',
        'supervisor_sub': 'असाइन किए गए वाहनों और निरीक्षणों की निगरानी और अनुमोदन करें',
        'driver': 'ड्राइवर डैशबोर्ड',
        'driver_sub': 'अपनी दैनिक वाहन निरीक्षण चेकलिस्ट पूरी करें',
        'register_user': 'कर्मचारी पंजीकृत करें',
        'name': 'पूरा नाम',
        'role': 'भूमिका (Role)',
        'initial_password': 'प्रारंभिक पासवर्ड (12+ अक्षर)',
        'save': 'सहेजें',
        'status': 'स्थिति',
        'active': 'सक्रिय',
        'inactive': 'निष्क्रिय',
        'actions': 'कार्रवाई',
        'deactivate': 'निष्क्रिय करें',
        'reactivate': 'पुनः सक्रिय करें',
        'plate': 'वाहन नंबर',
        'type': 'वाहन प्रकार',
        'model_desc': 'मॉडल और विवरण',
        'add_vehicle': 'वाहन जोड़ें',
        'assign': 'ड्राइवर असाइन करें',
        'driver_user': 'ड्राइवर',
        'drivers': 'सक्रिय ड्राइवर',
        'date': 'तारीख',
        'odometer': 'अंतिम ओडोमीटर (किमी)',
        'start_km': 'शुरुआती ओडोमीटर (किमी)',
        'end_km': 'अंतिम किमी',
        'inspection': 'दैनिक वाहन निरीक्षण चेकलिस्ट',
        'item': 'निरीक्षण मद',
        'result': 'परिणाम',
        'pass': 'ठीक (OK)',
        'fail': 'खराब (Not OK)',
        'na': 'लागू नहीं (N/A)',
        'passed_label': 'सफल',
        'failed_label': 'विफल',
        'pending_label': 'लंबित',
        'remark': 'टिप्पणी / खराबी का विवरण लिखें...',
        'action_taken': 'खराबी ठीक करने के लिए की गई कार्रवाई',
        'photo': 'खराबी की तस्वीरें',
        'add_photo': 'फोटो जोड़ें',
        'submit': 'निरीक्षण जमा करें',
        'save_draft': 'ड्राफ्ट सहेजें',
        'pending': 'सिंक लंबित',
        'synced': 'सिंक हो गया',
        'today': 'आज',
        'total_vehicles': 'कुल वाहन',
        'assigned_vehicles': 'असाइन किए गए वाहन',
        'total_employees': 'कुल कर्मचारी',
        'today_inspections': 'आज के निरीक्षण',
        'open_faults': 'खुली खराबियां',
        'pending_faults': 'लंबित खराबियां',
        'recent': 'हाल के निरीक्षण',
        'no_data': 'कोई रिकॉर्ड नहीं मिला।',
        'search_hint': 'वाहन नंबर या कर्मचारी ID से खोजें...',
        'scan': 'वाहन QR कोड स्कैन करें',
        'scan_hint': 'वाहन पर लगा QR कोड स्कैन करें या आज असाइन किया गया वाहन नंबर दर्ज करें।',
        'manual': 'वाहन नंबर दर्ज करें',
        'search_vehicle': 'निरीक्षण खोलें',
        'view': 'देखें',
        'export': 'Excel डाउनलोड करें',
        'access_denied': 'पहुंच अस्वीकृत: आपको इस पृष्ठ को देखने की अनुमति नहीं है।',
        'created': 'कर्मचारी खाता सफलतापूर्वक बनाया गया।',
        'saved': 'सफलतापूर्वक सहेजा गया।',
        'vehicle_added': 'वाहन सफलतापूर्वक पंजीकृत किया गया।',
        'assigned': 'चयनित तिथि के लिए ड्राइवर असाइनमेंट सहेजा गया।',
        'checklist_help': 'प्रत्येक मद को चिह्नित करें (OK, Not OK, N/A)। Not OK होने पर स्वतः फॉल्ट रिकॉर्ड बनता है।',
        'language': 'भाषा',
        'english': 'English',
        'arabic': 'عربي',
        'hindi': 'हिंदी',
        'urdu': 'اردو',
        'online': 'ऑनलाइन',
        'offline': 'ऑफ़लाइन मोड',
        'account_notice': 'केवल एडमिन ही कर्मचारी खाते बना और प्रबंधित कर सकता है। स्वयं-पंजीकरण बंद है।',
        'invalid_login': 'अमान्य कर्मचारी ID या पासवर्ड, अथवा खाता निष्क्रिय है।',
        'initial_admin': 'पहला एडमिन बनाने के लिए कमांड लाइन से `flask --app app create-admin` चलाएं।',
        'qr': 'QR कोड',
        'download_qr': 'QR डाउनलोड करें',
        'vehicle_history': 'वाहन निरीक्षण इतिहास',
        'vehicle_info': 'वाहन की जानकारी',
        'inspection_summary': 'निरीक्षण सारांश',
        'total_items': 'कुल मदें',
        'final_status': 'अंतिम स्थिति',
        'fault_status': 'खराबी की स्थिति',
        'open': 'खुला',
        'closed': 'हल किया गया',
        'resolve': 'खराबी हल करें',
        'details': 'खराबी का विवरण',
        'no_assignments': 'आज के लिए आपको कोई वाहन असाइन नहीं किया गया है।',
        'notes': 'अंतिम निरीक्षण टिप्पणी / नोट्स',
        'license_expiry': 'ड्राइवर ROP लाइसेंस समाप्ति तिथि',
        'attestation': 'मैं पुष्टि करता हूं कि मैंने वाहन की जांच पूरी ईमानदारी से की है।',
        'all_items': 'चेकलिस्ट मदें',
        'add_item': 'नई चेकलिस्ट मद जोड़ें',
        'update_item': 'नाम अपडेट करें',
        'item_label': 'मद का नाम',
        'enabled': 'सक्रिय',
        'disabled': 'निष्क्रिय',
        'activity': 'ऑडिट लॉग',
        'refresh': 'रीफ्रेश',
        'driver_name': 'ड्राइवर का नाम',
        'driver_signature': 'ड्राइवर के हस्ताक्षर',
        'supervisor_sign': 'सुपरवाइज़र / PA हस्ताक्षर',
        'supervisor_note': 'सुपरवाइज़र अनुमोदन वर्कफ़्लो द्वारा रिकॉर्ड किया जाता है।',
        'pending_approval': 'अनुमोदन लंबित',
        'approved': 'अनुमोदित',
        'approve': 'अनुमोदित करें',
        'quick_actions': 'त्वरित कार्य',
        'inspection_status': 'निरीक्षण स्थिति',
        'monthly_inspections': 'मासिक निरीक्षण',
        'weekly_inspections': 'इस सप्ताह के निरीक्षण',
        'vehicle_status': 'वाहन स्थिति',
        'good_vehicles': 'सही (Good)',
        'minor_issues': 'छोटी खराबी',
        'major_issues': 'बड़ी खराबी',
        'install_app': 'ऐप इंस्टॉल करें',
        'offline_queue_title': 'ऑफ़लाइन निरीक्षण कतार',
        'sync_now': 'सिंक करें',
        'photo_offline_notice': 'नोट: फोटो अपलोड करने के लिए इंटरनेट कनेक्शन आवश्यक है।',
    },
    'ur': {
        'app': 'اسمارٹ وہیکل انسپیکشن',
        'subtitle': 'اور فلیٹ مینجمنٹ سسٹم',
        'login': 'ملازم لاگ اِن',
        'employee': 'ملازم آئی ڈی (Employee ID)',
        'password': 'پاس ورڈ',
        'remember': 'مجھے یاد رکھیں',
        'sign_in': 'سائن اِن',
        'dashboard': 'ڈیش بورڈ',
        'users': 'ملازمین',
        'vehicles': 'گاڑیاں',
        'my_vehicles': 'میری گاڑیاں',
        'inspections': 'روزانہ معائنے',
        'my_inspections': 'میرے معائنے',
        'faults': 'خرابیاں اور مرمت',
        'fault_reports': 'خرابی کی رپورٹس',
        'reports': 'رپورٹس',
        'excel_export': 'Excel ایکسپورٹ',
        'settings': 'معائنہ فارمز',
        'audit_log': 'آڈٹ لاگ',
        'search': 'تلاش کریں',
        'logout': 'لاگ آؤٹ',
        'admin': 'ایڈمن ڈیش بورڈ',
        'admin_sub': 'اپنے فلیٹ، ملازمین اور روزانہ معائنوں کا انتظام کریں',
        'supervisor': 'سپروائزر ڈیش بورڈ',
        'supervisor_sub': 'مقررہ گاڑیوں، معائنوں کی منظوری اور خرابیوں کے حل کی نگرانی کریں',
        'driver': 'ڈرائیور ڈیش بورڈ',
        'driver_sub': 'آج کی مقررہ گاڑی کا روزانہ معائنہ مکمل کریں',
        'register_user': 'نیا ملازم درج کریں',
        'name': 'پورا نام',
        'role': 'کردار (Role)',
        'initial_password': 'ابتدائی پاس ورڈ (12+ حروف)',
        'save': 'محفوظ کریں',
        'status': 'حالت',
        'active': 'فعال',
        'inactive': 'غیر فعال',
        'actions': 'کارروائی',
        'deactivate': 'غیر فعال کریں',
        'reactivate': 'دوبارہ فعال کریں',
        'plate': 'گاڑی نمبر',
        'type': 'گاڑی کی قسم',
        'model_desc': 'ماڈل اور تفصیل',
        'add_vehicle': 'گاڑی شامل کریں',
        'assign': 'ڈرائیور مقرر کریں',
        'driver_user': 'ڈرائیور',
        'drivers': 'فعال ڈرائیورز',
        'date': 'تاریخ',
        'odometer': 'اختتامی اوڈومیٹر (کلومیٹر)',
        'start_km': 'ابتدائی اوڈومیٹر (کلومیٹر)',
        'end_km': 'اختتامی کلومیٹر',
        'inspection': 'روزانہ گاڑی کے معائنے کی چیک لسٹ',
        'item': 'معائنے کا آئٹم',
        'result': 'نتیجہ',
        'pass': 'درست (OK)',
        'fail': 'خراب (Not OK)',
        'na': 'لاگو نہیں (N/A)',
        'passed_label': 'کامیاب',
        'failed_label': 'ناکام',
        'pending_label': 'زیرِ التوا',
        'remark': 'تبصرہ یا خرابی کی تفصیل درج کریں...',
        'action_taken': 'خرابی دور کرنے کے لیے کی گئی کارروائی',
        'photo': 'خرابی کی تصاویر',
        'add_photo': 'تصویر شامل کریں',
        'submit': 'معائنہ جمع کریں',
        'save_draft': 'ڈرافٹ محفوظ کریں',
        'pending': 'سنک کا انتظار',
        'synced': 'سنک مکمل',
        'today': 'آج',
        'total_vehicles': 'کل گاڑیاں',
        'assigned_vehicles': 'مقررہ گاڑیاں',
        'total_employees': 'کل ملازمین',
        'today_inspections': 'آج کے معائنے',
        'open_faults': 'کھلی خرابیاں',
        'pending_faults': 'زیرِ التوا خرابیاں',
        'recent': 'حالیہ معائنے',
        'no_data': 'کوئی ریکارڈ نہیں ملا۔',
        'search_hint': 'گاڑی نمبر یا ملازم آئی ڈی سے تلاش کریں...',
        'scan': 'گاڑی کا QR کوڈ اسکین کریں',
        'scan_hint': 'گاڑی پر موجود QR کوڈ اسکین کریں یا آج کی مقررہ گاڑی کا نمبر درج کریں۔',
        'manual': 'گاڑی نمبر درج کریں',
        'search_vehicle': 'معائنہ کھولیں',
        'view': 'دیکھیں',
        'export': 'Excel ڈاؤن لوڈ کریں',
        'access_denied': 'رسائی مسترد: آپ کو اس صفحے یا ریکارڈ تک رسائی کی اجازت نہیں ہے۔',
        'created': 'ملازم کا اکاؤنٹ کامیابی سے بنایا گیا۔',
        'saved': 'تبدیلیاں کامیابی سے محفوظ ہو گئیں۔',
        'vehicle_added': 'گاڑی کامیابی سے شامل کر دی گئی۔',
        'assigned': 'منتخب تاریخ کے لیے ڈرائیور کی تعیناتی محفوظ ہو گئی۔',
        'checklist_help': 'ہر آئٹم کا جواب منتخب کریں (OK، Not OK، N/A)۔ Not OK منتخب کرنے پر خودکار فالٹ ریکارڈ بنے گا۔',
        'language': 'زبان',
        'english': 'English',
        'arabic': 'عربي',
        'hindi': 'हिंदी',
        'urdu': 'اردو',
        'online': 'آن لائن',
        'offline': 'آف لائن موڈ',
        'account_notice': 'صرف ایڈمن ملازمین کے اکاؤنٹس بنا اور منظم کر سکتا ہے۔ خودکار رجسٹریشن بند ہے۔',
        'invalid_login': 'غلط ملازم آئی ڈی یا پاس ورڈ، یا اکاؤنٹ غیر فعال ہے۔',
        'initial_admin': 'پہلا ایڈمن بنانے کے لیے کمانڈ لائن پر `flask --app app create-admin` چلائیں۔',
        'qr': 'QR کوڈ',
        'download_qr': 'QR ڈاؤن لوڈ کریں',
        'vehicle_history': 'گاڑی کے معائنے کی سرگزشت',
        'vehicle_info': 'گاڑی کی معلومات',
        'inspection_summary': 'معائنے کا خلاصہ',
        'total_items': 'کل آئٹمز',
        'final_status': 'حتمی حالت',
        'fault_status': 'خرابی کی حالت',
        'open': 'کھلی',
        'closed': 'حل شدہ',
        'resolve': 'خرابی حل کریں',
        'details': 'خرابی کی تفصیل',
        'no_assignments': 'آج کے لیے آپ کو کوئی گاڑی مقرر نہیں کی گئی ہے۔',
        'notes': 'معائنے کے حتمی نوٹس',
        'license_expiry': 'ڈرائیور کے ROP لائسنس کی میعاد',
        'attestation': 'میں تصدیق کرتا ہوں کہ میں نے گاڑی کا مکمل اور درست معائنہ کیا ہے۔',
        'all_items': 'چیک لسٹ آئٹمز',
        'add_item': 'نیا آئٹم شامل کریں',
        'update_item': 'نام اپڈیٹ کریں',
        'item_label': 'آئٹم کا نام',
        'enabled': 'فعال',
        'disabled': 'غیر فعال',
        'activity': 'آڈٹ لاگ',
        'refresh': 'تازہ کریں',
        'driver_name': 'ڈرائیور کا نام',
        'driver_signature': 'ڈرائیور کے دستخط',
        'supervisor_sign': 'سپروائزر / PA کے دستخط',
        'supervisor_note': 'سپروائزر کی منظوری کے مرحلے میں ریکارڈ کیا جاتا ہے۔',
        'pending_approval': 'منظوری زیرِ التوا',
        'approved': 'منظور شدہ',
        'approve': 'منظور اور دستخط کریں',
        'quick_actions': 'فوری کارروائیاں',
        'inspection_status': 'معائنے کی صورتحال',
        'monthly_inspections': 'ماہانہ معائنے',
        'weekly_inspections': 'اس ہفتے کے معائنے',
        'vehicle_status': 'گاڑیوں کی حالت',
        'good_vehicles': 'درست',
        'minor_issues': 'معمولی خرابیاں',
        'major_issues': 'بڑی خرابیاں',
        'install_app': 'ایپ انسٹال کریں',
        'offline_queue_title': 'آف لائن معائنہ قطار',
        'sync_now': 'محفوظ معائنے سنک کریں',
        'photo_offline_notice': 'نوٹ: خرابی کی تصاویر اپ لوڈ کرنے کے لیے انٹرنیٹ کنکشن ضروری ہے۔',
    }
}

XL = {
    'en': [
        'Inspections', 'Checklist', 'Faults', 'Employees', 'Vehicles', 'Audit',
        'ID', 'Inspection ID', 'Date', 'Vehicle', 'Employee ID', 'Driver',
        'Starting KM', 'Closing KM', 'Status', 'Notes', 'Item', 'Result',
        'Remark', 'Fault ID', 'Description', 'Action Taken', 'Role', 'Type',
        'Actor', 'Event', 'Timestamp', 'Resolver'
    ],
    'ar': [
        'الفحوصات', 'قائمة الفحص', 'الأعطال', 'الموظفون', 'المركبات', 'سجل التدقيق',
        'المعرّف', 'رقم الفحص', 'التاريخ', 'المركبة', 'الرقم الوظيفي', 'السائق',
        'عداد البداية', 'عداد النهاية', 'الحالة', 'ملاحظات', 'البند', 'النتيجة',
        'ملاحظة', 'رقم العطل', 'الوصف', 'الإجراء المتخذ', 'الصلاحية', 'النوع',
        'المنفذ', 'الحدث', 'الوقت', 'تم الحل بواسطة'
    ],
    'hi': [
        'निरीक्षण', 'चेकलिस्ट', 'खराबियां', 'कर्मचारी', 'वाहन', 'ऑडिट',
        'ID', 'निरीक्षण ID', 'तारीख', 'वाहन', 'कर्मचारी ID', 'ड्राइवर',
        'शुरुआती KM', 'अंतिम KM', 'स्थिति', 'नोट्स', 'मद', 'परिणाम',
        'टिप्पणी', 'खराबी ID', 'विवरण', 'की गई कार्रवाई', 'भूमिका', 'प्रकार',
        'उपयोगकर्ता', 'घटना', 'समय', 'समाधानकर्ता'
    ],
    'ur': [
        'معائنے', 'چیک لسٹ', 'خرابیاں', 'ملازمین', 'گاڑیاں', 'آڈٹ',
        'ID', 'معائنہ ID', 'تاریخ', 'گاڑی', 'ملازم ID', 'ڈرائیور',
        'ابتدائی KM', 'اختتامی KM', 'حالت', 'نوٹس', 'آئٹم', 'نتیجہ',
        'تبصرہ', 'خرابی ID', 'تفصیل', 'کی گئی کارروائی', 'کردار', 'قسم',
        'صارف', 'واقعہ', 'وقت', 'حل کنندہ'
    ]
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, supervisor, driver
    active = db.Column(db.Boolean, default=True, nullable=False)
    language = db.Column(db.String(5), default='en')


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), default='')
    vehicle_type = db.Column(db.String(80), default='')
    supervisor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    qr_token = db.Column(db.String(48), unique=True, default=lambda: secrets.token_urlsafe(24))


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day = db.Column(db.Date, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('vehicle_id', 'day', name='one_driver_per_vehicle_per_day'),
        db.UniqueConstraint('driver_id', 'day', name='one_vehicle_per_driver_per_day'),
    )


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(250), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    order = db.Column(db.Integer, default=0)
    label_ar = db.Column(db.String(250), default='')
    label_hi = db.Column(db.String(250), default='')
    label_ur = db.Column(db.String(250), default='')


class Inspection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day = db.Column(db.Date, nullable=False)
    odometer = db.Column(db.Integer, nullable=False)
    start_km = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, default='')
    driver_signature = db.Column(db.String(120), default='')
    license_expiry = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending_approval')
    supervisor_approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    supervisor_approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('vehicle_id', 'day', name='one_inspection_per_vehicle_per_day'),
    )


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('inspection.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    label_snapshot = db.Column(db.String(250), nullable=False)
    result = db.Column(db.String(10), nullable=False)  # pass, fail, na
    remark = db.Column(db.Text, default='')


class Fault(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('inspection.id'), nullable=False)
    answer_id = db.Column(db.Integer, db.ForeignKey('answer.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    action_taken = db.Column(db.Text, default='')
    status = db.Column(db.String(16), default='open')  # open, resolved
    resolved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    resolved_at = db.Column(db.DateTime)


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fault_id = db.Column(db.Integer, db.ForeignKey('fault.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), default='')


class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    actor_employee_id = db.Column(db.String(50), default='system')
    event = db.Column(db.String(250), nullable=False)
    at = db.Column(db.DateTime, default=datetime.utcnow)


def current_user():
    uid = session.get('uid')
    return db.session.get(User, uid) if uid else None


def get_lang() -> str:
    u = current_user()
    lang = session.get('lang') or (u.language if u else 'en')
    return lang if lang in TXT else 'en'


def tr(key: str) -> str:
    lang = get_lang()
    return TXT.get(lang, TXT['en']).get(key, TXT['en'].get(key, key))


def xl(index: int) -> str:
    lang = get_lang()
    arr = XL.get(lang, XL['en'])
    return arr[index] if index < len(arr) else XL['en'][index]


def item_name(item: Item) -> str:
    lang = get_lang()
    if lang != 'en':
        translated = getattr(item, 'label_' + lang, '')
        if translated:
            return translated
    return item.label


def is_valid_image_bytes(header: bytes, ext: str) -> bool:
    if ext in ('.jpg', '.jpeg') and header.startswith(b'\xff\xd8\xff'):
        return True
    if ext == '.png' and header.startswith(b'\x89PNG\r\n\x1a\n'):
        return True
    if ext == '.webp' and len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return True
    return False


@app.context_processor
def inject():
    u = current_user()
    lang = get_lang()
    return {
        't': tr,
        'user': u,
        'lang': lang,
        'rtl': lang in ('ar', 'ur'),
        'csrf_token': csrf_token,
        'today': today,
        'Fault': Fault,
        'Answer': Answer,
        'Photo': Photo,
        'User': User,
        'Vehicle': Vehicle,
        'Assignment': Assignment,
        'Inspection': Inspection,
        'item_name': item_name,
        'current_path': request.path,
        'max': max,
        'min': min,
    }


def _csrf_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='fleet-csrf-v1')


def _session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='fleet-session-v1')


def make_session_token(uid: int | None, lang: str = 'en') -> str:
    return _session_serializer().dumps({'uid': uid, 'lang': lang or 'en'})


def load_session_token(token: str) -> dict | None:
    if not token:
        return None
    try:
        data = _session_serializer().loads(token, max_age=86400 * 14)
        return data if isinstance(data, dict) else None
    except (BadSignature, ValueError, TypeError):
        return None


def csrf_token() -> str:
    existing = session.get('csrf', '')
    if existing:
        try:
            _csrf_serializer().loads(existing, max_age=86400 * 14)
            return existing
        except (BadSignature, ValueError, TypeError):
            pass
    signed = _csrf_serializer().dumps(secrets.token_urlsafe(16))
    session['csrf'] = signed
    return signed


def is_valid_csrf(token: str) -> bool:
    if not token:
        return False
    sess_csrf = session.get('csrf', '')
    if sess_csrf and secrets.compare_digest(token, sess_csrf):
        return True
    try:
        _csrf_serializer().loads(token, max_age=86400 * 14)
        return True
    except (BadSignature, ValueError, TypeError):
        return False


def verify_csrf():
    token = request.form.get('csrf') or request.headers.get('X-CSRF-Token', '')
    if not is_valid_csrf(token):
        abort(400)


@app.before_request
def hydrate_iframe_session():
    g.using_st = False
    g.logged_out = False
    st = (
        request.args.get('_st')
        or request.form.get('_st')
        or request.headers.get('X-Session-Token', '')
    )
    if st:
        data = load_session_token(st)
        if data:
            if not request.cookies.get('session'):
                g.using_st = True
            if 'uid' not in session and data.get('uid'):
                session['uid'] = data['uid']
            if 'lang' not in session and data.get('lang') in TXT:
                session['lang'] = data['lang']


@app.url_defaults
def append_iframe_session_token(endpoint, values):
    if endpoint == 'static' or getattr(g, 'logged_out', False):
        return
    if getattr(g, 'using_st', False) and '_st' not in values:
        uid = session.get('uid')
        lang = session.get('lang', 'en')
        if uid or lang != 'en':
            values['_st'] = make_session_token(uid, lang)


from flask.sessions import SecureCookieSessionInterface


class IframeCompatibleSessionInterface(SecureCookieSessionInterface):
    def save_session(self, app, session, response):
        super().save_session(app, session, response)
        host_info = f"{request.headers.get('X-Forwarded-Host', '')} {request.host}"
        is_https = (
            request.is_secure
            or request.headers.get('X-Forwarded-Proto', '') == 'https'
            or '.run.app' in host_info
        )
        if is_https and 'Set-Cookie' in response.headers:
            cookies = response.headers.getlist('Set-Cookie')
            updated = []
            for c in cookies:
                if c.startswith('session='):
                    c = c.replace('SameSite=Lax', 'SameSite=None')
                    if 'SameSite=None' not in c:
                        c += '; SameSite=None'
                    if '; Secure' not in c:
                        c += '; Secure'
                    if '; Partitioned' not in c:
                        c += '; Partitioned'
                updated.append(c)
            response.headers.setlist('Set-Cookie', updated)


app.session_interface = IframeCompatibleSessionInterface()


@app.errorhandler(400)
def handle_bad_request(err):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'bad_request'}), 400
    return (
        page(
            '400 Bad Request',
            '<div class="card"><h2>Invalid or Expired Form Request</h2>'
            '<p class="muted">Your session or form token expired. Please try again.</p>'
            f'<p><a class="btn btn-primary" href="{url_for("dashboard" if current_user() else "login")}">Continue</a></p></div>',
        ),
        400,
    )


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u or not u.active:
                session.clear()
                return redirect(url_for('login', next=request.path))
            if roles and u.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def log(event: str, actor: User = None):
    u = actor or current_user()
    db.session.add(
        Audit(
            actor_id=u.id if u else None,
            actor_employee_id=u.employee_id if u else 'system',
            event=event,
        )
    )


def page(title: str, body: str, **data):
    return render_template('page.html', title=title, body=body, **data)


def allowed_vehicle(vehicle_id: int, u: User = None) -> bool:
    u = u or current_user()
    if not u:
        return False
    if u.role == 'admin':
        return True
    if u.role == 'supervisor':
        return Vehicle.query.filter_by(id=vehicle_id, supervisor_id=u.id).first() is not None
    return (
        Assignment.query.filter_by(vehicle_id=vehicle_id, driver_id=u.id).first() is not None
        or Inspection.query.filter_by(vehicle_id=vehicle_id, driver_id=u.id).first() is not None
    )


def inspection_has_open_faults(inspection_id: int) -> int:
    return Fault.query.filter_by(inspection_id=inspection_id, status='open').count()


def inspection_total_faults(inspection_id: int) -> int:
    return Fault.query.filter_by(inspection_id=inspection_id).count()


@app.route('/')
def home():
    return redirect(url_for('dashboard' if current_user() else 'login'))


@app.route('/language/<lang>')
def language(lang):
    if lang not in TXT:
        abort(404)
    session['lang'] = lang
    u = current_user()
    if u:
        u.language = lang
        db.session.commit()
    if not request.cookies.get('session'):
        g.using_st = True
    target = request.referrer or url_for('dashboard' if u else 'login')
    if getattr(g, 'using_st', False) and target.startswith(request.host_url):
        return redirect(url_for('dashboard' if u else 'login'))
    return redirect(target)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        eid = request.form.get('employee_id', '').strip()
        pw = request.form.get('password', '')
        u = User.query.filter(db.func.lower(User.employee_id) == eid.lower()).first()
        if u and u.active and check_password_hash(u.password_hash, pw):
            preserved_lang = session.get('lang') or u.language or 'en'
            next_url = request.args.get('next') or request.form.get('next') or ''
            has_cookie = bool(request.cookies.get('session'))
            session.clear()
            session['uid'] = u.id
            session['lang'] = preserved_lang
            csrf_token()
            if request.form.get('remember'):
                session.permanent = True
            if not has_cookie:
                g.using_st = True
            log(f'Signed in ({u.role})', u)
            db.session.commit()
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                if getattr(g, 'using_st', False):
                    sep = '&' if '?' in next_url else '?'
                    return redirect(f"{next_url}{sep}_st={make_session_token(u.id, preserved_lang)}")
                return redirect(next_url)
            return redirect(url_for('dashboard'))
        flash(tr('invalid_login'), 'error')
    return page(tr('login'), render_template('login.html', next_url=request.args.get('next', '')))


@app.route('/logout', methods=['POST'])
def logout():
    verify_csrf()
    log('Signed out')
    db.session.commit()
    lang = session.get('lang', 'en')
    session.clear()
    session['lang'] = lang
    g.logged_out = True
    g.using_st = False
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required()
def dashboard():
    u = current_user()
    cur_day = today()
    if u.role == 'admin':
        total_vehicles = Vehicle.query.count()
        total_users = User.query.count()
        today_inspections = Inspection.query.filter_by(day=cur_day).count()
        open_faults_count = Fault.query.filter_by(status='open').count()
        all_inspections = Inspection.query.order_by(Inspection.day.desc(), Inspection.id.desc()).all()
        recent = all_inspections[:8]

        # Vehicle status breakdown for donut chart
        passed_vehicles = 0
        failed_vehicles = 0
        for v in Vehicle.query.all():
            latest = Inspection.query.filter_by(vehicle_id=v.id).order_by(Inspection.day.desc(), Inspection.id.desc()).first()
            if latest:
                if Fault.query.filter_by(inspection_id=latest.id, status='open').count() > 0:
                    failed_vehicles += 1
                else:
                    passed_vehicles += 1
        pending_vehicles = max(0, total_vehicles - passed_vehicles - failed_vehicles)

        # Monthly bar chart (last 6 months)
        month_labels = []
        month_passed = []
        month_failed = []
        for offset in range(5, -1, -1):
            d = (cur_day.replace(day=1) - timedelta(days=offset * 28)).replace(day=1)
            m_label = d.strftime('%b')
            if m_label not in month_labels:
                month_labels.append(m_label)
                m_insps = [i for i in all_inspections if i.day.year == d.year and i.day.month == d.month]
                m_fail = sum(1 for i in m_insps if Fault.query.filter_by(inspection_id=i.id).count() > 0)
                m_pass = len(m_insps) - m_fail
                month_passed.append(m_pass)
                month_failed.append(m_fail)

        plates = {v.id: v.plate for v in Vehicle.query.all()}
        names = {x.id: x.name for x in User.query.all()}
        fault_counts = {i.id: Fault.query.filter_by(inspection_id=i.id).count() for i in recent}

        content = render_template(
            'admin_dashboard.html',
            users=total_users,
            vehicles=total_vehicles,
            inspections=today_inspections,
            faults=open_faults_count,
            recent=recent,
            plates=plates,
            names=names,
            fault_counts=fault_counts,
            passed_vehicles=passed_vehicles,
            failed_vehicles=failed_vehicles,
            pending_vehicles=pending_vehicles,
            month_labels=month_labels,
            month_passed=month_passed,
            month_failed=month_failed,
        )
        return page(tr('admin'), content)

    if u.role == 'supervisor':
        vs = Vehicle.query.filter_by(supervisor_id=u.id).order_by(Vehicle.plate).all()
        ids = [v.id for v in vs]
        recent = (
            Inspection.query.filter(Inspection.vehicle_id.in_(ids))
            .order_by(Inspection.day.desc(), Inspection.id.desc())
            .limit(12)
            .all()
            if ids else []
        )
        today_insps = Inspection.query.filter(Inspection.vehicle_id.in_(ids), Inspection.day == cur_day).count() if ids else 0
        open_faults_list = (
            Fault.query.join(Inspection)
            .filter(Inspection.vehicle_id.in_(ids), Fault.status == 'open')
            .order_by(Fault.id.desc())
            .all()
            if ids else []
        )
        active_drivers_count = User.query.filter_by(role='driver', active=True).count()

        # Vehicle health breakdown for supervisor's assigned vehicles
        good_count = 0
        minor_count = 0
        major_count = 0
        vehicle_rows = []
        names = {x.id: x.name for x in User.query.all()}
        for v in vs:
            latest = Inspection.query.filter_by(vehicle_id=v.id).order_by(Inspection.day.desc(), Inspection.id.desc()).first()
            today_assign = Assignment.query.filter_by(vehicle_id=v.id, day=cur_day).first()
            drv_name = names.get(today_assign.driver_id, '—') if today_assign else (names.get(latest.driver_id, '—') if latest else '—')
            open_f = Fault.query.join(Inspection).filter(Inspection.vehicle_id == v.id, Fault.status == 'open').count()
            if open_f == 0:
                good_count += 1
                v_state = 'good'
            elif open_f == 1:
                minor_count += 1
                v_state = 'minor'
            else:
                major_count += 1
                v_state = 'major'
            vehicle_rows.append({
                'vehicle': v,
                'driver_name': drv_name,
                'last_date': str(latest.day) if latest else '—',
                'latest_inspection': latest,
                'open_faults': open_f,
                'state': v_state,
            })

        # Weekly chart (last 7 days)
        week_days = []
        week_passed = []
        week_failed = []
        for offset in range(6, -1, -1):
            d = cur_day - timedelta(days=offset)
            week_days.append(d.strftime('%a'))
            if ids:
                d_insps = Inspection.query.filter(Inspection.vehicle_id.in_(ids), Inspection.day == d).all()
                d_fail = sum(1 for i in d_insps if Fault.query.filter_by(inspection_id=i.id).count() > 0)
                d_pass = len(d_insps) - d_fail
            else:
                d_pass, d_fail = 0, 0
            week_passed.append(d_pass)
            week_failed.append(d_fail)

        return page(
            tr('supervisor'),
            render_template(
                'supervisor_dashboard.html',
                vehicles=vs,
                vehicle_rows=vehicle_rows,
                recent=recent,
                plates={v.id: v.plate for v in vs},
                names=names,
                faults=len(open_faults_list),
                open_faults_list=open_faults_list,
                today_inspections=today_insps,
                active_drivers=active_drivers_count,
                good_count=good_count,
                minor_count=minor_count,
                major_count=major_count,
                week_days=week_days,
                week_passed=week_passed,
                week_failed=week_failed,
                inspections_map={i.id: i for i in recent},
            ),
        )

    # Driver Dashboard
    assignments = Assignment.query.filter_by(driver_id=u.id, day=cur_day).all()
    assigned_vehicles = {a.vehicle_id: db.session.get(Vehicle, a.vehicle_id) for a in assignments}
    my_history = (
        Inspection.query.filter_by(driver_id=u.id)
        .order_by(Inspection.day.desc(), Inspection.id.desc())
        .limit(15)
        .all()
    )
    my_faults = (
        Fault.query.join(Inspection)
        .filter(Inspection.driver_id == u.id)
        .order_by(Fault.id.desc())
        .limit(10)
        .all()
    )
    all_plates = {v.id: v.plate for v in Vehicle.query.all()}
    today_submitted = {
        a.vehicle_id: Inspection.query.filter_by(vehicle_id=a.vehicle_id, day=cur_day).first()
        for a in assignments
    }
    return page(
        tr('driver'),
        render_template(
            'driver_dashboard.html',
            assignments=assignments,
            vehicles=assigned_vehicles,
            today_submitted=today_submitted,
            my_history=my_history,
            my_faults=my_faults,
            all_plates=all_plates,
        ),
    )


@app.route('/driver/open-vehicle', methods=['POST'])
@login_required('driver')
def driver_open_vehicle():
    verify_csrf()
    plate_or_token = request.form.get('plate', '').strip()
    if not plate_or_token:
        flash('Please enter a vehicle number or QR token.', 'error')
        return redirect(url_for('dashboard'))
    # Support entering either plate (e.g. KSA-1245) or QR token or full scan URL
    if '/scan/' in plate_or_token:
        token = plate_or_token.split('/scan/')[-1].strip('/')
        v = Vehicle.query.filter_by(qr_token=token).first()
    else:
        v = (
            Vehicle.query.filter(db.func.lower(Vehicle.plate) == plate_or_token.lower()).first()
            or Vehicle.query.filter_by(qr_token=plate_or_token).first()
        )
    if not v:
        flash('Vehicle not found.', 'error')
        return redirect(url_for('dashboard'))
    assignment = Assignment.query.filter_by(vehicle_id=v.id, driver_id=current_user().id, day=today()).first()
    if not assignment:
        abort(403)
    return redirect(url_for('inspect', vid=v.id))


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required('admin')
def users():
    if request.method == 'POST':
        verify_csrf()
        action = request.form.get('action', 'create')
        if action == 'toggle':
            person = db.session.get(User, int(request.form.get('user_id', '0')))
            if person:
                if person.id == current_user().id and person.active:
                    flash('You cannot deactivate your own active Admin account.', 'error')
                else:
                    person.active = not person.active
                    log(('Reactivated ' if person.active else 'Deactivated ') + 'employee ' + person.employee_id)
                    db.session.commit()
                    flash(tr('saved'), 'success')
            return redirect(url_for('users'))

        eid = request.form.get('employee_id', '').strip()
        name = request.form.get('name', '').strip()
        pw = request.form.get('password', '')
        role = request.form.get('role', '')
        if not eid or not name or len(pw) < 12 or role not in ('admin', 'supervisor', 'driver'):
            flash('Enter valid employee details. Initial password must be at least 12 characters.', 'error')
        elif User.query.filter(db.func.lower(User.employee_id) == eid.lower()).first():
            flash('Employee ID already exists.', 'error')
        else:
            db.session.add(
                User(
                    employee_id=eid,
                    name=name,
                    password_hash=generate_password_hash(pw),
                    role=role,
                )
            )
            log(f'Created {role} account {eid} ({name})')
            db.session.commit()
            flash(tr('created'), 'success')
            return redirect(url_for('users'))

    q = request.args.get('q', '').strip()
    query = User.query
    if q:
        query = query.filter(
            (User.employee_id.ilike(f'%{q}%'))
            | (User.name.ilike(f'%{q}%'))
            | (User.role.ilike(f'%{q}%'))
        )
    people = query.order_by(User.id).all()
    return page(tr('users'), render_template('users.html', people=people, q=q))


@app.route('/admin/vehicles', methods=['GET', 'POST'])
@login_required('admin')
def vehicles():
    if request.method == 'POST':
        verify_csrf()
        action = request.form.get('action', 'create')
        if action == 'update_supervisor':
            vid = int(request.form.get('vehicle_id', '0'))
            sid = request.form.get('supervisor_id', '')
            v = db.session.get(Vehicle, vid)
            if v:
                v.supervisor_id = int(sid) if sid else None
                log(f'Updated supervisor for vehicle {v.plate}')
                db.session.commit()
                flash(tr('saved'), 'success')
            return redirect(url_for('vehicles'))

        plate = request.form.get('plate', '').strip()
        if not plate:
            flash('Vehicle number / plate is required.', 'error')
        elif Vehicle.query.filter(db.func.lower(Vehicle.plate) == plate.lower()).first():
            flash('Vehicle plate already exists.', 'error')
        else:
            sid = request.form.get('supervisor_id', '').strip()
            db.session.add(
                Vehicle(
                    plate=plate,
                    description=request.form.get('description', '').strip(),
                    vehicle_type=request.form.get('vehicle_type', '').strip(),
                    supervisor_id=int(sid) if sid else None,
                )
            )
            log('Registered vehicle ' + plate)
            db.session.commit()
            flash(tr('vehicle_added'), 'success')
            return redirect(url_for('vehicles'))

    q = request.args.get('q', '').strip()
    v_query = Vehicle.query
    if q:
        v_query = v_query.filter(
            (Vehicle.plate.ilike(f'%{q}%'))
            | (Vehicle.vehicle_type.ilike(f'%{q}%'))
            | (Vehicle.description.ilike(f'%{q}%'))
        )
    all_vehicles = v_query.order_by(Vehicle.plate).all()
    supervisors = User.query.filter_by(role='supervisor', active=True).order_by(User.name).all()
    sup_map = {s.id: s for s in User.query.filter_by(role='supervisor').all()}
    return page(
        tr('vehicles'),
        render_template('vehicles.html', vehicles=all_vehicles, supervisors=supervisors, sup_map=sup_map, q=q),
    )


@app.route('/admin/assign', methods=['GET', 'POST'])
@login_required('admin')
def assign():
    if request.method == 'POST':
        verify_csrf()
        action = request.form.get('action', 'assign')
        if action == 'delete':
            aid = int(request.form.get('assignment_id', '0'))
            a = db.session.get(Assignment, aid)
            if a:
                log(f'Removed assignment id {a.id} (vehicle {a.vehicle_id}, driver {a.driver_id}, date {a.day})')
                db.session.delete(a)
                db.session.commit()
                flash(tr('saved'), 'success')
            return redirect(url_for('assign'))

        try:
            vid = int(request.form['vehicle_id'])
            did = int(request.form['driver_id'])
            day = date.fromisoformat(request.form['day'])
        except (KeyError, ValueError):
            abort(400)

        driver = db.session.get(User, did)
        vehicle = db.session.get(Vehicle, vid)
        if not driver or driver.role != 'driver' or not driver.active or not vehicle:
            abort(400)

        existing_for_driver = Assignment.query.filter_by(driver_id=did, day=day).first()
        existing_for_vehicle = Assignment.query.filter_by(vehicle_id=vid, day=day).first()

        if existing_for_driver and existing_for_driver.vehicle_id != vid:
            other_v = db.session.get(Vehicle, existing_for_driver.vehicle_id)
            flash(
                f'Assignment rule violation: Driver {driver.name} ({driver.employee_id}) is already assigned to vehicle {other_v.plate if other_v else existing_for_driver.vehicle_id} on {day}. Each driver can have only one vehicle per date.',
                'error',
            )
        elif existing_for_vehicle and existing_for_vehicle.driver_id != did:
            other_d = db.session.get(User, existing_for_vehicle.driver_id)
            flash(
                f'Assignment rule violation: Vehicle {vehicle.plate} is already assigned to driver {other_d.name if other_d else existing_for_vehicle.driver_id} on {day}. Each vehicle can have only one driver per date.',
                'error',
            )
        elif existing_for_vehicle and existing_for_vehicle.driver_id == did:
            flash(tr('assigned'), 'success')
            return redirect(url_for('assign'))
        else:
            try:
                db.session.add(Assignment(vehicle_id=vid, driver_id=did, day=day))
                log(f'Assigned vehicle {vehicle.plate} to driver {driver.employee_id} on {day}')
                db.session.commit()
                flash(tr('assigned'), 'success')
                return redirect(url_for('assign'))
            except IntegrityError:
                db.session.rollback()
                flash('Database constraint error: Only one driver per vehicle per day and one vehicle per driver per day is allowed.', 'error')

    all_assignments = Assignment.query.order_by(Assignment.day.desc(), Assignment.id.desc()).limit(50).all()
    v_map = {v.id: v for v in Vehicle.query.all()}
    u_map = {u.id: u for u in User.query.all()}
    return page(
        tr('assign'),
        render_template(
            'assign.html',
            vehicles=Vehicle.query.order_by(Vehicle.plate).all(),
            drivers=User.query.filter_by(role='driver', active=True).order_by(User.name).all(),
            today=today().isoformat(),
            assignments=all_assignments,
            v_map=v_map,
            u_map=u_map,
        ),
    )


@app.route('/admin/checklist', methods=['GET', 'POST'])
@login_required('admin')
def checklist():
    if request.method == 'POST':
        verify_csrf()
        action = request.form.get('action')
        if action == 'add':
            label = request.form.get('label', '').strip()
            label_ar = request.form.get('label_ar', '').strip()
            label_hi = request.form.get('label_hi', '').strip()
            label_ur = request.form.get('label_ur', '').strip()
            if label:
                next_order = max(32, (db.session.query(db.func.max(Item.order)).scalar() or 31) + 1)
                db.session.add(
                    Item(
                        label=label,
                        order=next_order,
                        label_ar=label_ar,
                        label_hi=label_hi,
                        label_ur=label_ur,
                    )
                )
                log('Added checklist item: ' + label)
                db.session.commit()
                flash(tr('saved'), 'success')
        elif action == 'rename':
            item = db.session.get(Item, int(request.form.get('item_id', '0')))
            new_label = request.form.get('label', '').strip()
            if item and new_label:
                old_label = item.label
                item.label = new_label
                log(f'Renamed checklist item #{item.order} from "{old_label}" to "{new_label}"')
                db.session.commit()
                flash(tr('saved'), 'success')
        else:
            item = db.session.get(Item, int(request.form.get('item_id', '0')))
            if item and 28 <= item.order <= 31:
                flash('The driver and supervisor sign-off fields (rows 28–31) are mandatory and cannot be disabled.', 'error')
            elif item:
                item.active = not item.active
                log(f'{"Enabled" if item.active else "Disabled"} checklist item #{item.order} ({item.label})')
                db.session.commit()
                flash(tr('saved'), 'success')
        return redirect(url_for('checklist'))

    return page(
        tr('settings'),
        render_template('checklist.html', items=Item.query.order_by(Item.order, Item.id).all()),
    )


@app.route('/vehicle/<int:vid>')
@login_required()
def vehicle_detail(vid):
    v = db.get_or_404(Vehicle, vid)
    u = current_user()
    if not allowed_vehicle(vid, u):
        abort(403)
    records = Inspection.query.filter_by(vehicle_id=vid).order_by(Inspection.day.desc(), Inspection.id.desc()).all()
    names = {x.id: x.name for x in User.query.all()}
    supervisor = db.session.get(User, v.supervisor_id) if v.supervisor_id else None
    fault_counts = {r.id: Fault.query.filter_by(inspection_id=r.id).count() for r in records}
    return page(
        v.plate,
        render_template(
            'vehicle_detail.html',
            vehicle=v,
            supervisor=supervisor,
            records=records,
            names=names,
            fault_counts=fault_counts,
        ),
    )


@app.route('/inspection/<int:iid>')
@login_required()
def inspection_detail(iid):
    rec = db.get_or_404(Inspection, iid)
    u = current_user()
    if u.role == 'driver' and rec.driver_id != u.id:
        abort(403)
    if u.role == 'supervisor' and not allowed_vehicle(rec.vehicle_id, u):
        abort(403)
    v = db.session.get(Vehicle, rec.vehicle_id)
    driver = db.session.get(User, rec.driver_id)
    approver = db.session.get(User, rec.supervisor_approved_by) if rec.supervisor_approved_by else None
    answers = Answer.query.filter_by(inspection_id=rec.id).order_by(Answer.id).all()
    faults_list = Fault.query.filter_by(inspection_id=rec.id).order_by(Fault.id).all()
    photos_map = {f.id: Photo.query.filter_by(fault_id=f.id).all() for f in faults_list}
    return page(
        f'{tr("inspection")} #{rec.id} · {v.plate}',
        render_template(
            'inspection_detail.html',
            inspection=rec,
            vehicle=v,
            driver=driver,
            approver=approver,
            answers=answers,
            faults=faults_list,
            photos=photos_map,
        ),
    )


@app.route('/vehicle/<int:vid>/qr.png')
@login_required()
def vehicle_qr(vid):
    v = db.get_or_404(Vehicle, vid)
    if not allowed_vehicle(vid):
        abort(403)
    scan_url = url_for('scan_vehicle', token=v.qr_token, _external=True)
    img = qrcode.make(scan_url)
    out = io.BytesIO()
    img.save(out, format='PNG')
    out.seek(0)
    as_dl = request.args.get('download', '1') == '1'
    return send_file(
        out,
        mimetype='image/png',
        as_attachment=as_dl,
        download_name=secure_filename(v.plate) + '-qr.png',
    )


@app.route('/scan/<token>')
@login_required()
def scan_vehicle(token):
    v = Vehicle.query.filter_by(qr_token=token).first_or_404()
    u = current_user()
    if u.role != 'driver':
        if not allowed_vehicle(v.id, u):
            abort(403)
        return redirect(url_for('vehicle_detail', vid=v.id))
    if not Assignment.query.filter_by(vehicle_id=v.id, driver_id=u.id, day=today()).first():
        abort(403)
    return redirect(url_for('inspect', vid=v.id))


@app.route('/inspect/<int:vid>', methods=['GET', 'POST'])
@login_required('driver')
def inspect(vid):
    v = db.get_or_404(Vehicle, vid)
    u = current_user()
    inspection_day = today()
    if not Assignment.query.filter_by(vehicle_id=vid, driver_id=u.id, day=inspection_day).first():
        abort(403)
    existing = Inspection.query.filter_by(vehicle_id=vid, day=inspection_day).first()
    if existing:
        flash('Daily inspection for this vehicle has already been submitted today.', 'success')
        return redirect(url_for('inspection_detail', iid=existing.id))

    items = Item.query.filter_by(active=True).order_by(Item.order, Item.id).all()
    check_items = [item for item in items if item.order <= 27 or item.order >= 32]
    signoff_items = {item.order: item for item in items if 28 <= item.order <= 31}

    if request.method == 'POST':
        verify_csrf()
        try:
            start = int(request.form.get('start_km', '0'))
            odo = int(request.form['odometer'])
            assert start >= 0 and odo >= start
        except (ValueError, KeyError, AssertionError):
            flash('Closing odometer must be greater than or equal to starting odometer.', 'error')
            return page(tr('inspection'), render_template('inspect.html', vehicle=v, items=items, today=inspection_day.isoformat()))

        answers = {str(i.id): request.form.get('item_' + str(i.id)) for i in check_items}
        try:
            license_expiry = date.fromisoformat(request.form.get('license_expiry', ''))
        except ValueError:
            license_expiry = None
        signature = request.form.get('driver_signature', '').strip()

        if not check_items or any(val not in ('pass', 'fail', 'na') for val in answers.values()):
            flash('Please mark OK, Not OK, or N/A for all checklist items.', 'error')
        elif not signature or not license_expiry:
            flash('Please enter your Driver Signature and ROP License Expiry Date.', 'error')
        elif not request.form.get('attestation'):
            flash('Please check the confirmation box to submit your inspection.', 'error')
        else:
            rec = Inspection(
                vehicle_id=vid,
                driver_id=u.id,
                day=inspection_day,
                odometer=odo,
                start_km=start,
                driver_signature=signature,
                license_expiry=license_expiry,
                notes=request.form.get('notes', '').strip(),
                status='pending_approval',
            )
            db.session.add(rec)
            db.session.flush()
            fail_answer_ids = []

            for item in items:
                if item.order <= 27 or item.order >= 32:
                    res_val = answers[str(item.id)]
                    rem_val = request.form.get('remark_' + str(item.id), '').strip()
                    ans = Answer(
                        inspection_id=rec.id,
                        item_id=item.id,
                        label_snapshot=item_name(item),
                        result=res_val,
                        remark=rem_val,
                    )
                    db.session.add(ans)
                    db.session.flush()
                    if res_val == 'fail':
                        fault_desc = rem_val if rem_val else f'{item.label} reported Not OK'
                        fault = Fault(
                            inspection_id=rec.id,
                            answer_id=ans.id,
                            description=fault_desc,
                        )
                        db.session.add(fault)
                        db.session.flush()
                        fail_answer_ids.append((ans.id, fault.id))
                elif item.order == 28:
                    db.session.add(Answer(
                        inspection_id=rec.id,
                        item_id=item.id,
                        label_snapshot=item_name(item),
                        result='pass',
                        remark=f'{u.name} ({u.employee_id})',
                    ))
                elif item.order == 29:
                    db.session.add(Answer(
                        inspection_id=rec.id,
                        item_id=item.id,
                        label_snapshot=item_name(item),
                        result='pass',
                        remark=signature,
                    ))
                elif item.order == 30:
                    db.session.add(Answer(
                        inspection_id=rec.id,
                        item_id=item.id,
                        label_snapshot=item_name(item),
                        result='pass',
                        remark=str(license_expiry),
                    ))
                elif item.order == 31:
                    db.session.add(Answer(
                        inspection_id=rec.id,
                        item_id=item.id,
                        label_snapshot=item_name(item),
                        result='na',
                        remark='Pending supervisor approval',
                    ))

            db.session.flush()
            files = [f for f in request.files.getlist('photos') if f and f.filename]
            if len(files) > 6:
                abort(400)
            for f in files:
                ext = Path(f.filename).suffix.lower()
                if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
                    abort(400)
                header = f.stream.read(16)
                f.stream.seek(0, os.SEEK_END)
                size = f.stream.tell()
                f.stream.seek(0)
                if size > app.config['MAX_SINGLE_PHOTO_BYTES'] or not is_valid_image_bytes(header, ext):
                    abort(400)
                # Link photo to the first fault, or create a general inspection fault if no item was marked fail
                if fail_answer_ids:
                    fid = fail_answer_ids[0][1]
                else:
                    first_ans = Answer.query.filter_by(inspection_id=rec.id).first()
                    gen_fault = Fault(
                        inspection_id=rec.id,
                        answer_id=first_ans.id,
                        description=rec.notes or 'Attached inspection issue photo',
                    )
                    db.session.add(gen_fault)
                    db.session.flush()
                    fid = gen_fault.id
                    fail_answer_ids.append((first_ans.id, fid))
                name = secrets.token_hex(16) + ext
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], name))
                db.session.add(
                    Photo(
                        fault_id=fid,
                        filename=name,
                        original_name=secure_filename(f.filename),
                    )
                )

            log(f'Submitted inspection #{rec.id} for vehicle {v.plate}')
            db.session.commit()
            flash(tr('saved'), 'success')
            return redirect(url_for('inspection_detail', iid=rec.id))

    return page(
        tr('inspection'),
        render_template('inspect.html', vehicle=v, items=items, today=inspection_day.isoformat()),
    )


@app.route('/faults')
@login_required()
def faults():
    u = current_user()
    q = Fault.query.join(Inspection)
    if u.role == 'supervisor':
        v_ids = [v.id for v in Vehicle.query.filter_by(supervisor_id=u.id).all()]
        q = q.filter(Inspection.vehicle_id.in_(v_ids)) if v_ids else q.filter(db.false())
    elif u.role == 'driver':
        q = q.filter(Inspection.driver_id == u.id)

    status_filter = request.args.get('status', '').strip()
    if status_filter in ('open', 'resolved'):
        q = q.filter(Fault.status == status_filter)

    rows = q.order_by(Fault.status, Fault.id.desc()).all()
    users_map = {x.id: x.name for x in User.query.all()}
    return page(
        tr('faults'),
        render_template(
            'faults.html',
            faults=rows,
            status_filter=status_filter,
            vehicles={v.id: v.plate for v in Vehicle.query.all()},
            inspections={i.id: i for i in Inspection.query.all()},
            answers={a.id: a for a in Answer.query.all()},
            photos={f.id: Photo.query.filter_by(fault_id=f.id).all() for f in rows},
            users_map=users_map,
        ),
    )


@app.route('/fault-photo/<filename>')
@login_required()
def fault_photo(filename):
    photo = Photo.query.filter_by(filename=filename).first_or_404()
    fault = db.session.get(Fault, photo.fault_id)
    inspection = db.session.get(Inspection, fault.inspection_id)
    u = current_user()
    if u.role == 'driver' and inspection.driver_id != u.id:
        abort(403)
    if u.role == 'supervisor' and not allowed_vehicle(inspection.vehicle_id, u):
        abort(403)
    return send_from_directory(app.config['UPLOAD_FOLDER'], photo.filename, as_attachment=False)


@app.route('/fault/<int:fid>/resolve', methods=['POST'])
@login_required('admin', 'supervisor')
def resolve_fault(fid):
    verify_csrf()
    f = db.get_or_404(Fault, fid)
    i = db.session.get(Inspection, f.inspection_id)
    if not allowed_vehicle(i.vehicle_id):
        abort(403)
    action_text = request.form.get('action_taken', '').strip()
    if not action_text:
        flash('Please enter the action taken to resolve this fault.', 'error')
        return redirect(request.referrer or url_for('faults'))
    f.status = 'resolved'
    f.action_taken = action_text
    f.resolved_by = current_user().id
    f.resolved_at = datetime.utcnow()
    log(f'Resolved fault #{fid} on inspection #{i.id}: {action_text}')
    db.session.commit()
    flash(tr('saved'), 'success')
    return redirect(request.referrer or url_for('faults'))


@app.route('/search')
@login_required()
def search():
    q = request.args.get('q', '').strip()
    u = current_user()
    vs = []
    people = []
    insps = []
    if q:
        v_query = Vehicle.query.filter(
            (Vehicle.plate.ilike('%' + q + '%'))
            | (Vehicle.vehicle_type.ilike('%' + q + '%'))
            | (Vehicle.description.ilike('%' + q + '%'))
        )
        if u.role == 'supervisor':
            v_query = v_query.filter_by(supervisor_id=u.id)
        elif u.role == 'driver':
            assigned_vids = [a.vehicle_id for a in Assignment.query.filter_by(driver_id=u.id).all()]
            v_query = v_query.filter(Vehicle.id.in_(assigned_vids)) if assigned_vids else v_query.filter(db.false())
        vs = v_query.all()

        if u.role == 'admin':
            people = User.query.filter(
                (User.employee_id.ilike('%' + q + '%')) | (User.name.ilike('%' + q + '%'))
            ).all()

        # Also search inspections by plate or driver employee_id
        i_query = Inspection.query.join(Vehicle, Inspection.vehicle_id == Vehicle.id).join(User, Inspection.driver_id == User.id).filter(
            (Vehicle.plate.ilike('%' + q + '%'))
            | (User.employee_id.ilike('%' + q + '%'))
            | (User.name.ilike('%' + q + '%'))
        )
        if u.role == 'supervisor':
            sup_vids = [v.id for v in Vehicle.query.filter_by(supervisor_id=u.id).all()]
            i_query = i_query.filter(Inspection.vehicle_id.in_(sup_vids)) if sup_vids else i_query.filter(db.false())
        elif u.role == 'driver':
            i_query = i_query.filter(Inspection.driver_id == u.id)
        insps = i_query.order_by(Inspection.day.desc()).limit(25).all()

    return page(
        tr('search'),
        render_template(
            'search.html',
            q=q,
            vehicles=vs,
            people=people,
            inspections=insps,
            plates={v.id: v.plate for v in Vehicle.query.all()},
            names={x.id: x.name for x in User.query.all()},
        ),
    )


@app.route('/reports')
@login_required('admin', 'supervisor')
def reports():
    u = current_user()
    q_str = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = Inspection.query
    if u.role == 'supervisor':
        sup_vids = [v.id for v in Vehicle.query.filter_by(supervisor_id=u.id).all()]
        query = query.filter(Inspection.vehicle_id.in_(sup_vids)) if sup_vids else query.filter(db.false())

    if status_filter in ('approved', 'pending_approval'):
        query = query.filter(Inspection.status == status_filter)

    records = query.order_by(Inspection.day.desc(), Inspection.id.desc()).limit(500).all()
    vehicles_map = {v.id: v.plate for v in Vehicle.query.all()}
    names_map = {p.id: p.name for p in User.query.all()}
    emp_ids_map = {p.id: p.employee_id for p in User.query.all()}

    if q_str:
        q_low = q_str.lower()
        records = [
            r for r in records
            if q_low in vehicles_map.get(r.vehicle_id, '').lower()
            or q_low in names_map.get(r.driver_id, '').lower()
            or q_low in emp_ids_map.get(r.driver_id, '').lower()
            or q_low in str(r.day)
        ]

    audits = Audit.query.order_by(Audit.at.desc()).limit(100).all() if u.role == 'admin' else []
    fault_counts = {r.id: Fault.query.filter_by(inspection_id=r.id).count() for r in records}
    open_fault_counts = {r.id: Fault.query.filter_by(inspection_id=r.id, status='open').count() for r in records}

    return page(
        tr('reports'),
        render_template(
            'reports.html',
            records=records,
            vehicles=vehicles_map,
            names=names_map,
            emp_ids=emp_ids_map,
            fault_counts=fault_counts,
            open_fault_counts=open_fault_counts,
            audits=audits,
            q=q_str,
            status_filter=status_filter,
        ),
    )


@app.route('/inspection/<int:iid>/approve', methods=['POST'])
@login_required('admin', 'supervisor')
def approve_inspection(iid):
    verify_csrf()
    rec = db.get_or_404(Inspection, iid)
    u = current_user()
    if not allowed_vehicle(rec.vehicle_id, u):
        abort(403)
    rec.status = 'approved'
    rec.supervisor_approved_by = u.id
    rec.supervisor_approved_at = datetime.utcnow()

    # Update Row 31 (Supervisor / PA Signature) Answer snapshot on this inspection
    sup_item = Item.query.filter_by(order=31).first()
    sup_ans = None
    if sup_item:
        sup_ans = Answer.query.filter_by(inspection_id=rec.id, item_id=sup_item.id).first()
    if not sup_ans:
        sup_ans = Answer.query.filter(
            Answer.inspection_id == rec.id,
            Answer.label_snapshot.ilike('%Supervisor%'),
        ).first()
    sign_text = f'Signed & Approved by {u.name} ({u.employee_id}) on {rec.supervisor_approved_at.strftime("%Y-%m-%d %H:%M UTC")}'
    if sup_ans:
        sup_ans.result = 'pass'
        sup_ans.remark = sign_text
    elif sup_item:
        db.session.add(
            Answer(
                inspection_id=rec.id,
                item_id=sup_item.id,
                label_snapshot=item_name(sup_item),
                result='pass',
                remark=sign_text,
            )
        )

    log(f'Supervisor {u.employee_id} approved inspection #{rec.id}')
    db.session.commit()
    flash(tr('saved'), 'success')
    return redirect(request.referrer or url_for('inspection_detail', iid=rec.id))


@app.route('/admin/export.xlsx')
@login_required('admin', 'supervisor')
def export():
    u = current_user()
    ids = None
    if u.role == 'supervisor':
        ids = [v.id for v in Vehicle.query.filter_by(supervisor_id=u.id).all()]

    q = Inspection.query
    if ids is not None:
        q = q.filter(Inspection.vehicle_id.in_(ids)) if ids else q.filter(db.false())
    records = q.order_by(Inspection.id).all()

    wb = Workbook()
    header_fill = PatternFill(start_color='0D2942', end_color='0D2942', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)

    def style_header(sheet):
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

    # Sheet 1: Inspections
    ws = wb.active
    ws.title = xl(0)
    ws.append([
        xl(7), xl(8), xl(9), xl(10), xl(11), xl(12), xl(13),
        xl(14), xl(15), tr('license_expiry'), tr('driver_signature'), tr('supervisor_sign')
    ])
    style_header(ws)
    for r in records:
        veh = db.session.get(Vehicle, r.vehicle_id)
        drv = db.session.get(User, r.driver_id)
        sup = db.session.get(User, r.supervisor_approved_by) if r.supervisor_approved_by else None
        ws.append([
            r.id,
            str(r.day),
            veh.plate if veh else '',
            drv.employee_id if drv else '',
            drv.name if drv else '',
            r.start_km,
            r.odometer,
            tr('approved') if r.status == 'approved' else tr('pending_approval'),
            r.notes,
            str(r.license_expiry or ''),
            r.driver_signature,
            f'{sup.name} ({sup.employee_id})' if sup else '',
        ])

    # Sheet 2: Checklist Answers
    ws = wb.create_sheet(xl(1))
    ws.append([xl(7), xl(9), xl(11), xl(8), xl(16), xl(17), xl(18)])
    style_header(ws)
    for r in records:
        veh = db.session.get(Vehicle, r.vehicle_id)
        drv = db.session.get(User, r.driver_id)
        for a in Answer.query.filter_by(inspection_id=r.id).order_by(Answer.id).all():
            ws.append([
                r.id,
                veh.plate if veh else '',
                drv.name if drv else '',
                str(r.day),
                a.label_snapshot,
                tr(a.result),
                a.remark,
            ])

    # Sheet 3: Faults
    ws = wb.create_sheet(xl(2))
    ws.append([xl(19), xl(7), xl(9), xl(20), xl(21), xl(14), xl(27), xl(26)])
    style_header(ws)
    fq = Fault.query.join(Inspection)
    if ids is not None:
        fq = fq.filter(Inspection.vehicle_id.in_(ids)) if ids else fq.filter(db.false())
    for f in fq.order_by(Fault.id).all():
        insp = db.session.get(Inspection, f.inspection_id)
        veh = db.session.get(Vehicle, insp.vehicle_id) if insp else None
        res_user = db.session.get(User, f.resolved_by) if f.resolved_by else None
        ws.append([
            f.id,
            f.inspection_id,
            veh.plate if veh else '',
            f.description,
            f.action_taken,
            tr('open') if f.status == 'open' else tr('closed'),
            f'{res_user.name} ({res_user.employee_id})' if res_user else '',
            str(f.resolved_at or ''),
        ])

    # Sheet 4: Employees (Admin sees all; Supervisor sees drivers associated with their vehicles + self)
    ws = wb.create_sheet(xl(3))
    ws.append([xl(10), tr('name'), xl(22), xl(14)])
    style_header(ws)
    if ids is None:
        emp_rows = User.query.order_by(User.id).all()
    else:
        driver_ids = {r.driver_id for r in records} | {
            a.driver_id for a in Assignment.query.filter(Assignment.vehicle_id.in_(ids)).all()
        } if ids else set()
        driver_ids.add(u.id)
        emp_rows = User.query.filter(User.id.in_(driver_ids)).order_by(User.id).all()
    for p in emp_rows:
        ws.append([p.employee_id, p.name, p.role, tr('active') if p.active else tr('inactive')])

    # Sheet 5: Vehicles
    ws = wb.create_sheet(xl(4))
    ws.append([xl(9), xl(23), xl(20)])
    style_header(ws)
    v_rows = Vehicle.query.filter(Vehicle.id.in_(ids)).all() if ids is not None else Vehicle.query.all()
    for v in v_rows:
        ws.append([v.plate, v.vehicle_type, v.description])

    # Sheet 6: Audit Events
    ws = wb.create_sheet(xl(5))
    ws.append([xl(24), xl(25), xl(26)])
    style_header(ws)
    audit_q = Audit.query.order_by(Audit.at.desc())
    if ids is not None:
        audit_q = audit_q.filter_by(actor_id=u.id)
    for a in audit_q.limit(500).all():
        ws.append([a.actor_employee_id, a.event, str(a.at)])

    log(f'Exported Excel report ({get_lang()})')
    db.session.commit()
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return send_file(
        out,
        as_attachment=True,
        download_name=f'vehicle_inspections_{today().isoformat()}_{get_lang()}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@app.route('/api/inspections', methods=['POST'])
@login_required('driver')
def sync_inspection():
    # JSON offline queue sync endpoint; enforces authentication, CSRF, and daily assignment.
    if not is_valid_csrf(request.headers.get('X-CSRF-Token', '')):
        return jsonify({'ok': False, 'error': 'csrf_invalid'}), 400
    payload = request.get_json(silent=True) or {}
    vid = int(payload.get('vehicle_id', 0))
    u = current_user()
    if not Assignment.query.filter_by(vehicle_id=vid, driver_id=u.id, day=today()).first():
        return jsonify({'ok': False, 'error': 'assignment_conflict'}), 403
    existing = Inspection.query.filter_by(vehicle_id=vid, day=today()).first()
    if existing:
        return jsonify({'ok': True, 'inspection_id': existing.id, 'duplicate': True})

    active = Item.query.filter_by(active=True).order_by(Item.order, Item.id).all()
    check_items = [i for i in active if i.order <= 27 or i.order >= 32]
    answers = payload.get('answers', {})
    if not check_items or any(answers.get(str(i.id)) not in ('pass', 'fail', 'na') for i in check_items):
        return jsonify({'ok': False, 'error': 'incomplete_checklist'}), 400
    if not payload.get('attestation'):
        return jsonify({'ok': False, 'error': 'confirmation_required'}), 400
    signature = str(payload.get('driver_signature', '')).strip()
    try:
        license_expiry = date.fromisoformat(payload.get('license_expiry', ''))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'license_expiry_required'}), 400
    if not signature:
        return jsonify({'ok': False, 'error': 'signature_required'}), 400
    try:
        start = int(payload.get('start_km', 0))
        odo = int(payload['odometer'])
    except (ValueError, KeyError, TypeError):
        return jsonify({'ok': False, 'error': 'invalid_odometer'}), 400
    if start < 0 or odo < start:
        return jsonify({'ok': False, 'error': 'invalid_odometer'}), 400

    rec = Inspection(
        vehicle_id=vid,
        driver_id=u.id,
        day=today(),
        odometer=odo,
        start_km=start,
        driver_signature=signature,
        license_expiry=license_expiry,
        notes=payload.get('notes', ''),
        status='pending_approval',
    )
    db.session.add(rec)
    db.session.flush()
    for item in active:
        if item.order <= 27 or item.order >= 32:
            result = answers[str(item.id)]
            rem = payload.get('remarks', {}).get(str(item.id), '')
            ans = Answer(
                inspection_id=rec.id,
                item_id=item.id,
                label_snapshot=item_name(item),
                result=result,
                remark=rem,
            )
            db.session.add(ans)
            db.session.flush()
            if result == 'fail':
                db.session.add(
                    Fault(
                        inspection_id=rec.id,
                        answer_id=ans.id,
                        description=ans.remark or f'{item.label} reported Not OK',
                    )
                )
        elif item.order == 28:
            db.session.add(Answer(inspection_id=rec.id, item_id=item.id, label_snapshot=item_name(item), result='pass', remark=f'{u.name} ({u.employee_id})'))
        elif item.order == 29:
            db.session.add(Answer(inspection_id=rec.id, item_id=item.id, label_snapshot=item_name(item), result='pass', remark=signature))
        elif item.order == 30:
            db.session.add(Answer(inspection_id=rec.id, item_id=item.id, label_snapshot=item_name(item), result='pass', remark=str(license_expiry)))
        elif item.order == 31:
            db.session.add(Answer(inspection_id=rec.id, item_id=item.id, label_snapshot=item_name(item), result='na', remark='Pending supervisor approval'))

    log('Synced offline inspection #' + str(rec.id))
    db.session.commit()
    return jsonify({'ok': True, 'inspection_id': rec.id, 'duplicate': False})


@app.route('/manifest.webmanifest')
def manifest():
    return app.send_static_file('manifest.webmanifest')


@app.route('/sw.js')
def service_worker():
    response = app.send_static_file('sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    return response


@app.errorhandler(403)
def forbidden(e):
    return (
        page(
            '403 · Access Denied',
            '<section class="panel error-panel"><div class="error-badge">403</div><h2>'
            + tr('access_denied')
            + '</h2><p class="muted">Your current role does not grant access to this route or vehicle record.</p><a class="button primary" href="'
            + url_for('dashboard')
            + '">'
            + tr('dashboard')
            + '</a></section>',
        ),
        403,
    )


def ensure_checklist_seeded():
    db.create_all()
    if Item.query.count() == 0:
        for n, label in enumerate(CHECKLIST, 1):
            db.session.add(
                Item(
                    label=label,
                    order=n,
                    label_ar=CHECKLIST_TRANSLATIONS['ar'][n - 1],
                    label_hi=CHECKLIST_TRANSLATIONS['hi'][n - 1],
                    label_ur=CHECKLIST_TRANSLATIONS['ur'][n - 1],
                )
            )
        db.session.commit()


def seed_demo_data_if_empty():
    ensure_checklist_seeded()
    if User.query.count() > 0:
        return

    admin = User(
        employee_id='EMP-ADMIN',
        name='System Administrator',
        password_hash=generate_password_hash('AdminPass1234!'),
        role='admin',
        language='en',
    )
    sup1 = User(
        employee_id='EMP-SUP01',
        name='Salim Al-Harthy',
        password_hash=generate_password_hash('SuperPass1234!'),
        role='supervisor',
        language='en',
    )
    sup2 = User(
        employee_id='EMP-SUP02',
        name='Vikram Singh',
        password_hash=generate_password_hash('SuperPass1234!'),
        role='supervisor',
        language='en',
    )
    drv1 = User(
        employee_id='EMP-DRV01',
        name='Ahmed Khan',
        password_hash=generate_password_hash('DriverPass1234!'),
        role='driver',
        language='en',
    )
    drv2 = User(
        employee_id='EMP-DRV02',
        name='Mohammed Ali',
        password_hash=generate_password_hash('DriverPass1234!'),
        role='driver',
        language='en',
    )
    drv3 = User(
        employee_id='EMP-DRV03',
        name='Rajesh Kumar',
        password_hash=generate_password_hash('DriverPass1234!'),
        role='driver',
        language='en',
    )
    drv4 = User(
        employee_id='EMP-DRV04',
        name='Usman Malik',
        password_hash=generate_password_hash('DriverPass1234!'),
        role='driver',
        language='en',
    )
    db.session.add_all([admin, sup1, sup2, drv1, drv2, drv3, drv4])
    db.session.flush()

    v1 = Vehicle(plate='KSA-1245', vehicle_type='Toyota Hiace', description='2023 White · Passenger Van', supervisor_id=sup1.id, qr_token='qr-ksa-1245')
    v2 = Vehicle(plate='KSA-5678', vehicle_type='Nissan Urvan', description='2022 Silver · Cargo Van', supervisor_id=sup1.id, qr_token='qr-ksa-5678')
    v3 = Vehicle(plate='KSA-9012', vehicle_type='Toyota Coaster', description='2024 White · Staff Bus', supervisor_id=sup1.id, qr_token='qr-ksa-9012')
    v4 = Vehicle(plate='KSA-3456', vehicle_type='Mitsubishi Fuso', description='2021 Heavy Canter Truck', supervisor_id=sup1.id, qr_token='qr-ksa-3456')
    v5 = Vehicle(plate='KSA-7890', vehicle_type='Toyota Hilux', description='2023 4x4 Field Pickup', supervisor_id=sup2.id, qr_token='qr-ksa-7890')
    db.session.add_all([v1, v2, v3, v4, v5])
    db.session.flush()

    cur = today()
    # Today's assignments (one driver per vehicle, one vehicle per driver)
    db.session.add_all([
        Assignment(vehicle_id=v1.id, driver_id=drv1.id, day=cur),
        Assignment(vehicle_id=v2.id, driver_id=drv2.id, day=cur),
        Assignment(vehicle_id=v3.id, driver_id=drv3.id, day=cur),
        Assignment(vehicle_id=v4.id, driver_id=drv4.id, day=cur - timedelta(days=1)),
        Assignment(vehicle_id=v5.id, driver_id=drv4.id, day=cur),
    ])
    db.session.flush()

    all_items = Item.query.order_by(Item.order).all()

    def create_sample_inspection(veh, drv, insp_day, start_km, odo, status, failed_orders=None, sup_user=None):
        failed_orders = failed_orders or {}
        rec = Inspection(
            vehicle_id=veh.id,
            driver_id=drv.id,
            day=insp_day,
            start_km=start_km,
            odometer=odo,
            driver_signature=drv.name,
            license_expiry=cur + timedelta(days=420),
            notes='Routine daily walk-around completed.' if not failed_orders else 'Defects noted during walk-around inspection.',
            status=status,
            supervisor_approved_by=sup_user.id if status == 'approved' and sup_user else None,
            supervisor_approved_at=datetime.utcnow() if status == 'approved' else None,
        )
        db.session.add(rec)
        db.session.flush()
        created_faults = []
        for it in all_items:
            if it.order <= 27:
                res = 'fail' if it.order in failed_orders else 'pass'
                rem = failed_orders.get(it.order, '')
                ans = Answer(inspection_id=rec.id, item_id=it.id, label_snapshot=it.label, result=res, remark=rem)
                db.session.add(ans)
                db.session.flush()
                if res == 'fail':
                    f = Fault(inspection_id=rec.id, answer_id=ans.id, description=rem or f'{it.label} defect')
                    db.session.add(f)
                    db.session.flush()
                    created_faults.append(f)
            elif it.order == 28:
                db.session.add(Answer(inspection_id=rec.id, item_id=it.id, label_snapshot=it.label, result='pass', remark=f'{drv.name} ({drv.employee_id})'))
            elif it.order == 29:
                db.session.add(Answer(inspection_id=rec.id, item_id=it.id, label_snapshot=it.label, result='pass', remark=drv.name))
            elif it.order == 30:
                db.session.add(Answer(inspection_id=rec.id, item_id=it.id, label_snapshot=it.label, result='pass', remark=str(cur + timedelta(days=420))))
            elif it.order == 31:
                db.session.add(Answer(
                    inspection_id=rec.id,
                    item_id=it.id,
                    label_snapshot=it.label,
                    result='pass' if status == 'approved' else 'na',
                    remark=f'Approved by {sup_user.name}' if status == 'approved' and sup_user else 'Pending supervisor approval',
                ))
        return rec, created_faults

    # Notice: v1 (KSA-1245) assigned to drv1 (Ahmed Khan) today is left ready to inspect live,
    # while it has an approved inspection from yesterday!
    create_sample_inspection(v1, drv1, cur - timedelta(days=1), 41200, 41350, 'approved', {}, sup1)

    # v2 (KSA-5678) inspected today by drv2 (Mohammed Ali) with 2 open faults + sample photo
    rec_v2, faults_v2 = create_sample_inspection(
        v2, drv2, cur, 68400, 68510, 'pending_approval',
        {10: 'Front right tyre tread worn below safety indicator; lug nut loose', 16: 'Driver side wiper blade torn'},
        sup1,
    )
    if faults_v2:
        sample_photo_name = 'sample_tyre_fault.png'
        sample_path = Path(app.config['UPLOAD_FOLDER']) / sample_photo_name
        if sample_path.exists():
            db.session.add(Photo(fault_id=faults_v2[0].id, filename=sample_photo_name, original_name='tyre_inspection.png'))

    # v3 (KSA-9012) inspected today by drv3 (Rajesh Kumar) - passed & approved
    create_sample_inspection(v3, drv3, cur, 92100, 92280, 'approved', {}, sup1)

    # v4 (KSA-3456) inspected yesterday by drv4 (Usman Malik) with 1 open fault
    create_sample_inspection(
        v4, drv4, cur - timedelta(days=1), 115300, 115490, 'pending_approval',
        {17: 'Rear brake pad squeal under load'},
        sup1,
    )

    # v5 (KSA-7890) assigned to sup2 inspected 2 days ago
    create_sample_inspection(v5, drv4, cur - timedelta(days=2), 34000, 34180, 'approved', {}, sup2)

    # Historical inspections across earlier months for monthly chart
    for m_off in range(1, 6):
        past_day = cur - timedelta(days=m_off * 29)
        create_sample_inspection(v1, drv1, past_day, 35000 + m_off * 500, 35120 + m_off * 500, 'approved', {}, sup1)
        create_sample_inspection(v3, drv3, past_day - timedelta(days=1), 80000 + m_off * 500, 80150 + m_off * 500, 'approved', {1: 'Headlight bulb replaced'} if m_off % 2 == 0 else {}, sup1)

    log('Initialized database with 31 checklist rows and initial fleet records', admin)
    db.session.commit()


@app.cli.command('init-db')
def init_db():
    """Initialize database tables and seed the 31 checklist rows."""
    ensure_checklist_seeded()
    print('Database initialized with the 31 checklist rows from the scanned paper form.')


@app.cli.command('create-admin')
@click.option('--employee-id', default=None, help='Admin Employee ID')
@click.option('--name', default=None, help='Admin full name')
@click.option('--password', default=None, help='Admin password (12+ characters)')
def create_admin(employee_id, name, password):
    """Create the first Admin user account from the command line."""
    import getpass
    ensure_checklist_seeded()
    eid = (employee_id or input('Admin employee ID: ')).strip()
    full_name = (name or input('Admin full name: ')).strip()
    pw = password or getpass.getpass('Admin password (12+ characters): ')
    if len(pw) < 12:
        raise ValueError('Password must be at least 12 characters')
    existing = User.query.filter(db.func.lower(User.employee_id) == eid.lower()).first()
    if existing:
        raise ValueError('Employee ID exists')
    user = User(
        employee_id=eid,
        name=full_name,
        password_hash=generate_password_hash(pw),
        role='admin',
        language='en',
    )
    db.session.add(user)
    log(f'Created CLI admin account {eid}', user)
    db.session.commit()
    print(f'Admin created: {eid}')


@app.cli.command('seed-demo')
def seed_demo():
    """Seed deterministic fleet demo accounts, vehicles, and inspections."""
    seed_demo_data_if_empty()
    print('Demo fleet data seeded.')


if __name__ == '__main__':
    with app.app_context():
        seed_demo_data_if_empty()
    port = int(os.getenv('FLASK_RUN_PORT', '5000'))
    app.run(host='127.0.0.1', port=port, debug=False)
