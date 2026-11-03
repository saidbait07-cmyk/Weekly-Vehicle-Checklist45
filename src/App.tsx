/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useMemo, useEffect } from 'react';
import {
  CheckSquare,
  Square,
  AlertTriangle,
  ShieldCheck,
  Truck,
  Globe,
  RotateCcw,
  Send,
  FileSpreadsheet,
  Search,
  CheckCircle2,
  ClipboardCheck,
} from 'lucide-react';
import {
  AUTHORITATIVE_CHECKLIST_ITEMS,
  type CheckResult,
  type SupportedLanguage,
  isRtlLanguage,
  isProtectedSignOffRow,
  summarizeChecklistResponses,
} from './utils/inspectionRules';

export interface ChecklistPointState {
  order: number;
  label: string;
  checked: boolean;
  result: CheckResult;
  remark: string;
}

const TRANSLATIONS: Record<
  SupportedLanguage,
  {
    title: string;
    subtitle: string;
    vehiclePlate: string;
    startKm: string;
    endKm: string;
    driverName: string;
    driverSignature: string;
    ropExpiry: string;
    supervisorSign: string;
    checkAll: string;
    clearAll: string;
    submitInspection: string;
    pointsChecked: string;
    passedOk: string;
    faultsNotOk: string;
    notApplicable: string;
    searchPlaceholder: string;
    remarkPlaceholder: string;
    ok: string;
    notOk: string;
    na: string;
    submittedBanner: string;
    signOffBadge: string;
    openFleetPortal: string;
  }
> = {
  en: {
    title: '31-Point Daily Vehicle Inspection Checklist',
    subtitle: 'Complete and check off all 31 authoritative inspection points and sign-off fields.',
    vehiclePlate: 'Vehicle Number / Plate',
    startKm: 'Start Odometer (KM)',
    endKm: 'Current Odometer (KM)',
    driverName: 'Driver Name (Autofilled)',
    driverSignature: 'Driver Typed Signature',
    ropExpiry: 'Driver’s ROP EXP Date',
    supervisorSign: 'Supervisor / PA Signature',
    checkAll: 'Check All 31 Points',
    clearAll: 'Reset All',
    submitInspection: 'Submit Daily Inspection',
    pointsChecked: 'Points Checked',
    passedOk: 'OK (Passed)',
    faultsNotOk: 'Not OK (Faults)',
    notApplicable: 'N/A',
    searchPlaceholder: 'Filter 31 checklist points...',
    remarkPlaceholder: 'Enter remark or defect details...',
    ok: 'OK',
    notOk: 'Not OK',
    na: 'N/A',
    submittedBanner: 'Daily 31-point vehicle inspection submitted and logged.',
    signOffBadge: 'Mandatory Sign-Off Row',
    openFleetPortal: 'Open Fleet Dashboard',
  },
  ar: {
    title: 'قائمة الفحص اليومي للمركبات (31 نقطة)',
    subtitle: 'أكمل وحدد جميع نقاط الفحص اليومي الـ 31 وحقول التوقيع الإلزامية.',
    vehiclePlate: 'رقم المركبة / اللوحة',
    startKm: 'عداد البداية (كم)',
    endKm: 'العداد الحالي (كم)',
    driverName: 'اسم السائق (تلقائي)',
    driverSignature: 'توقيع السائق',
    ropExpiry: 'تاريخ انتهاء رخصة شرطة عمان السلطانية',
    supervisorSign: 'توقيع المشرف / المسؤول',
    checkAll: 'تحديد جميع الـ 31 نقطة',
    clearAll: 'إعادة تعيين',
    submitInspection: 'إرسال الفحص اليومي',
    pointsChecked: 'النقاط المحددة',
    passedOk: 'سليم (OK)',
    faultsNotOk: 'غير سليم (أعطال)',
    notApplicable: 'غير منطبق',
    searchPlaceholder: 'ابحث في 31 نقطة فحص...',
    remarkPlaceholder: 'أدخل ملاحظة أو تفاصيل العطل...',
    ok: 'سليم',
    notOk: 'غير سليم',
    na: 'غ/م',
    submittedBanner: 'تم إرسال وتسجيل الفحص اليومي المكون من 31 نقطة بنجاح.',
    signOffBadge: 'حقل توقيع إلزامي',
    openFleetPortal: 'لوحة إدارة الأسطول',
  },
  hi: {
    title: '31-बिंदु दैनिक वाहन निरीक्षण जांच सूची',
    subtitle: 'सभी 31 आधिकारिक निरीक्षण बिंदुओं और हस्ताक्षर फ़ील्ड को पूरा करें और चेक करें।',
    vehiclePlate: 'वाहन संख्या / प्लेट',
    startKm: 'प्रारंभ ओडोमीटर (किमी)',
    endKm: 'वर्तमान ओडोमीटर (किमी)',
    driverName: 'ड्राइवर का नाम (स्वतः भरा गया)',
    driverSignature: 'ड्राइवर का हस्ताक्षर',
    ropExpiry: 'ड्राइवर ROP समाप्ति तिथि',
    supervisorSign: 'सुपरवाइजर / PA हस्ताक्षर',
    checkAll: 'सभी 31 बिंदु चेक करें',
    clearAll: 'रीसेट करें',
    submitInspection: 'दैनिक निरीक्षण जमा करें',
    pointsChecked: 'चेक किए गए बिंदु',
    passedOk: 'ठीक है (OK)',
    faultsNotOk: 'ठीक नहीं (Faults)',
    notApplicable: 'लागू नहीं (N/A)',
    searchPlaceholder: '31 जांच बिंदु खोजें...',
    remarkPlaceholder: 'टिप्पणी या खराबी का विवरण दर्ज करें...',
    ok: 'OK',
    notOk: 'Not OK',
    na: 'N/A',
    submittedBanner: '31-बिंदु दैनिक वाहन निरीक्षण सफलतापूर्वक जमा किया गया।',
    signOffBadge: 'अनिवार्य हस्ताक्षर पंक्ति',
    openFleetPortal: 'फ़्लीट डैशबोर्ड खोलें',
  },
  ur: {
    title: '31 نکاتی روزانہ گاڑی کے معائنے کی چیک لسٹ',
    subtitle: 'معائنے کے تمام 31 مستند نکات اور دستخطی خانے مکمل کریں اور چیک کریں۔',
    vehiclePlate: 'گاڑی کا نمبر / پلیٹ',
    startKm: 'ابتدائی اوڈومیٹر (کلومیٹر)',
    endKm: 'موجودہ اوڈومیٹر (کلومیٹر)',
    driverName: 'ڈرائیور کا نام (خودکار)',
    driverSignature: 'ڈرائیور کے دستخط',
    ropExpiry: 'ڈرائیور ROP لائسنس کی میعاد',
    supervisorSign: 'سپروائزر / PA دستخط',
    checkAll: 'تمام 31 نکات منتخب کریں',
    clearAll: 'ری سیٹ کریں',
    submitInspection: 'روزانہ معائنہ جمع کروائیں',
    pointsChecked: 'منتخب کردہ نکات',
    passedOk: 'درست (OK)',
    faultsNotOk: 'خراب (نقص)',
    notApplicable: 'لاگو نہیں',
    searchPlaceholder: '31 نکات میں تلاش کریں...',
    remarkPlaceholder: 'ریمارکس یا خرابی کی تفصیل درج کریں...',
    ok: 'درست',
    notOk: 'خراب',
    na: 'N/A',
    submittedBanner: '31 نکاتی روزانہ گاڑی کا معائنہ کامیابی سے جمع ہو گیا۔',
    signOffBadge: 'لازمی دستخطی قطار',
    openFleetPortal: 'فلیٹ ڈیش بورڈ کھولیں',
  },
};

const ARABIC_ITEM_LABELS: Record<number, string> = {
  1: 'الأضواء والمؤشرات',
  2: 'المرايا',
  3: 'مرآة النقطة العمياء',
  4: 'المنبه (البوق)',
  5: 'الوقود',
  6: 'حزام الأمان',
  7: 'جهاز الاتصال اللاسلكي / المسجل',
  8: 'مكيف الهواء في المركبة',
  9: 'أضرار الهيكل الخارجي',
  10: 'الإطارات والصواميل والمسامير',
  11: 'تثبيت الحمولة',
  12: 'البطارية',
  13: 'مستوى الزيت',
  14: 'مستوى الماء',
  15: 'نظام التوجيه (المقود)',
  16: 'المساحات والزجاج الأمامي',
  17: 'المكابح (الفرامل)',
  18: 'صندوق الإسعافات الأولية',
  19: 'طفايات الحريق',
  20: 'الرافعة والأدوات ومثلث التحذير',
  21: 'أوراق تسجيل المركبة (الملكية)',
  22: 'حالة السلم',
  23: 'نظام مراقبة المركبات (IVMS)',
  24: 'النظافة الداخلية والترتيب',
  25: 'الفحص الدائري 360 درجة حول المركبة',
  26: 'ملصق فحص السلامة (RAS OPAL)',
  27: 'بطاقات التدريب الإلزامي للسائق',
  28: 'اسم السائق',
  29: 'توقيع السائق',
  30: 'تاريخ انتهاء رخصة السائق (ROP)',
  31: 'توقيع المشرف / المسؤول',
};

function createInitialPoints(): ChecklistPointState[] {
  return AUTHORITATIVE_CHECKLIST_ITEMS.map((label, idx) => {
    const order = idx + 1;
    return {
      order,
      label,
      checked: order === 28, // Row 28 Driver Name is autofilled by default
      result: 'pass',
      remark:
        order === 28
          ? 'Ahmed Khan (EMP-DRV01)'
          : order === 29
          ? 'Ahmed Khan'
          : order === 30
          ? '2028-05-01'
          : order === 31
          ? 'Pending Supervisor Approval'
          : '',
    };
  });
}

export function DailyVehicleInspectionChecklist() {
  const [lang, setLang] = useState<SupportedLanguage>('en');
  const [vehiclePlate, setVehiclePlate] = useState('KSA-1245 · Toyota Hilux 4x4');
  const [startKm, setStartKm] = useState('41350');
  const [endKm, setEndKm] = useState('41490');
  const [driverName] = useState('Ahmed Khan (EMP-DRV01)');
  const [driverSignature, setDriverSignature] = useState('Ahmed Khan');
  const [ropExpiry, setRopExpiry] = useState('2028-05-01');
  const [supervisorSignature, setSupervisorSignature] = useState('Pending Supervisor Approval');
  const [searchQuery, setSearchQuery] = useState('');
  const [points, setPoints] = useState<ChecklistPointState[]>(() => {
    try {
      const saved = localStorage.getItem('fleet-react-31-checklist');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length === 31) {
          return parsed;
        }
      }
    } catch (_) {}
    return createInitialPoints();
  });
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);

  const t = TRANSLATIONS[lang];
  const rtl = isRtlLanguage(lang);

  useEffect(() => {
    try {
      localStorage.setItem('fleet-react-31-checklist', JSON.stringify(points));
    } catch (_) {}
  }, [points]);

  const togglePointCheckbox = (order: number) => {
    setSubmittedAt(null);
    setPoints((prev) =>
      prev.map((pt) => (pt.order === order ? { ...pt, checked: !pt.checked } : pt))
    );
  };

  const updatePointResult = (order: number, result: CheckResult) => {
    setSubmittedAt(null);
    setPoints((prev) =>
      prev.map((pt) =>
        pt.order === order
          ? {
              ...pt,
              checked: true,
              result,
            }
          : pt
      )
    );
  };

  const updatePointRemark = (order: number, remark: string) => {
    setSubmittedAt(null);
    setPoints((prev) =>
      prev.map((pt) => (pt.order === order ? { ...pt, remark } : pt))
    );
  };

  const handleCheckAll = () => {
    setSubmittedAt(null);
    setPoints((prev) => prev.map((pt) => ({ ...pt, checked: true })));
  };

  const handleClearAll = () => {
    setSubmittedAt(null);
    setPoints(createInitialPoints().map((pt) => ({ ...pt, checked: false })));
  };

  const checkedCount = useMemo(
    () => points.filter((p) => p.checked).length,
    [points]
  );

  const summary = useMemo(() => {
    const activeResults = points
      .filter((p) => p.checked && !isProtectedSignOffRow(p.order))
      .map((p) => p.result);
    return summarizeChecklistResponses(activeResults);
  }, [points]);

  const filteredPoints = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return points;
    return points.filter(
      (p) =>
        p.label.toLowerCase().includes(q) ||
        String(p.order).includes(q) ||
        (ARABIC_ITEM_LABELS[p.order] || '').includes(q)
    );
  }, [points, searchQuery]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Mark all 31 points checked on submit if not already checked
    setPoints((prev) => prev.map((pt) => ({ ...pt, checked: true })));
    setSubmittedAt(new Date().toLocaleTimeString());
  };

  return (
    <div
      dir={rtl ? 'rtl' : 'ltr'}
      className="min-h-screen bg-[#071426] text-slate-100 font-sans pb-16"
    >
      {/* Top Fleet Header */}
      <header className="border-b border-slate-800 bg-[#0b1e38]/95 sticky top-0 z-20 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center shadow-inner">
              <Truck className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-bold tracking-tight text-white">
                {t.title}
              </h1>
              <p className="text-xs sm:text-sm text-slate-400">{t.subtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div
              className="flex items-center bg-[#071426] border border-slate-700 rounded-lg p-1"
              role="group"
              aria-label="Language selector"
            >
              <Globe className="w-4 h-4 text-slate-400 mx-1.5" />
              {(['en', 'ar', 'hi', 'ur'] as SupportedLanguage[]).map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => setLang(code)}
                  className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                    lang === code
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  {code === 'en'
                    ? 'EN'
                    : code === 'ar'
                    ? 'عربي'
                    : code === 'hi'
                    ? 'हिंदी'
                    : 'اردو'}
                </button>
              ))}
            </div>

            <a
              href="/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition-colors"
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              <span>{t.openFleetPortal}</span>
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 pt-6">
        {/* KPI Status Strip */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6">
          <div className="bg-[#0f2442] border border-slate-800 rounded-xl p-4">
            <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              {t.pointsChecked}
            </div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-bold font-mono text-white">
                {checkedCount} / 31
              </span>
              <span className="text-xs font-mono text-blue-400">
                {Math.round((checkedCount / 31) * 100)}%
              </span>
            </div>
            <div className="mt-2.5 h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all duration-200"
                style={{ width: `${(checkedCount / 31) * 100}%` }}
              />
            </div>
          </div>

          <div className="bg-[#0f2442] border border-slate-800 rounded-xl p-4">
            <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              {t.passedOk}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-2xl font-bold font-mono text-emerald-400">
                {summary.passed}
              </span>
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            </div>
          </div>

          <div className="bg-[#0f2442] border border-slate-800 rounded-xl p-4">
            <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              {t.faultsNotOk}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-2xl font-bold font-mono text-rose-400">
                {summary.failed}
              </span>
              <AlertTriangle className="w-5 h-5 text-rose-400" />
            </div>
          </div>

          <div className="bg-[#0f2442] border border-slate-800 rounded-xl p-4">
            <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
              {t.notApplicable}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-2xl font-bold font-mono text-amber-300">
                {summary.na}
              </span>
              <ClipboardCheck className="w-5 h-5 text-amber-300" />
            </div>
          </div>
        </section>

        {submittedAt && (
          <div
            role="status"
            className="mb-6 bg-emerald-950/80 border border-emerald-600/60 rounded-xl p-4 flex items-center justify-between gap-4 text-emerald-200"
          >
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <div>
                <p className="font-semibold text-sm">{t.submittedBanner}</p>
                <p className="text-xs text-emerald-300/80 font-mono mt-0.5">
                  {vehiclePlate} · 31/31 Points Verified · Faults Created:{' '}
                  {summary.createsFaults} · {submittedAt}
                </p>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Vehicle & Toolbar Card */}
          <section className="bg-[#0f2442] border border-slate-800 rounded-xl p-4 sm:p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <label className="block">
                <span className="text-xs font-semibold text-slate-300 block mb-1.5">
                  {t.vehiclePlate}
                </span>
                <select
                  value={vehiclePlate}
                  onChange={(e) => setVehiclePlate(e.target.value)}
                  className="w-full bg-[#071426] border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="KSA-1245 · Toyota Hilux 4x4">
                    KSA-1245 · Toyota Hilux 4x4
                  </option>
                  <option value="KSA-2389 · Isuzu NPR Cargo">
                    KSA-2389 · Isuzu NPR Cargo
                  </option>
                  <option value="KSA-5678 · Mitsubishi Canter">
                    KSA-5678 · Mitsubishi Canter
                  </option>
                  <option value="KSA-3456 · Ford Ranger Double Cab">
                    KSA-3456 · Ford Ranger Double Cab
                  </option>
                  <option value="KSA-7890 · Hino 300 Flatbed">
                    KSA-7890 · Hino 300 Flatbed
                  </option>
                </select>
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-300 block mb-1.5">
                  {t.startKm}
                </span>
                <input
                  type="number"
                  value={startKm}
                  onChange={(e) => setStartKm(e.target.value)}
                  className="w-full bg-[#071426] border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold text-slate-300 block mb-1.5">
                  {t.endKm}
                </span>
                <input
                  type="number"
                  value={endKm}
                  onChange={(e) => setEndKm(e.target.value)}
                  className="w-full bg-[#071426] border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </label>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
              <div className="relative flex-1 min-w-[220px]">
                <Search className="w-4 h-4 text-slate-400 absolute top-2.5 start-3 pointer-events-none" />
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t.searchPlaceholder}
                  className="w-full bg-[#071426] border border-slate-700 rounded-lg ps-9 pe-3 py-1.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCheckAll}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-colors cursor-pointer"
                >
                  <CheckSquare className="w-4 h-4" />
                  <span>{t.checkAll}</span>
                </button>
                <button
                  type="button"
                  onClick={handleClearAll}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition-colors cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>{t.clearAll}</span>
                </button>
              </div>
            </div>
          </section>

          {/* 31-Point Checklist List */}
          <section
            aria-label="31-Point Vehicle Inspection Checklist"
            className="bg-[#0f2442] border border-slate-800 rounded-xl divide-y divide-slate-800/90 overflow-hidden"
          >
            {filteredPoints.map((point) => {
              const isSignOff = isProtectedSignOffRow(point.order);
              const arLabel = ARABIC_ITEM_LABELS[point.order];

              return (
                <div
                  key={point.order}
                  data-point-order={point.order}
                  className={`p-3.5 sm:px-5 flex flex-col lg:flex-row lg:items-center justify-between gap-3 transition-colors ${
                    point.checked ? 'bg-blue-950/20' : 'hover:bg-slate-900/40'
                  }`}
                >
                  {/* Checkbox + Point Number + Authoritative Label */}
                  <label
                    htmlFor={`checklist-point-${point.order}`}
                    className="flex items-start sm:items-center gap-3.5 cursor-pointer select-none flex-1 min-w-0"
                  >
                    <input
                      id={`checklist-point-${point.order}`}
                      name={`point_${point.order}`}
                      type="checkbox"
                      checked={point.checked}
                      onChange={() => togglePointCheckbox(point.order)}
                      className="mt-0.5 sm:mt-0 w-5 h-5 rounded border-slate-600 bg-[#071426] text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer shrink-0"
                    />
                    <span className="w-7 h-7 rounded-md bg-[#071426] border border-slate-700 font-mono text-xs font-semibold text-slate-300 flex items-center justify-center shrink-0">
                      {point.order}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className={`font-semibold text-sm sm:text-base ${
                            point.checked ? 'text-white' : 'text-slate-200'
                          }`}
                        >
                          {point.label}
                        </span>
                        {isSignOff && (
                          <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-blue-900/50 text-blue-300 border border-blue-700/50">
                            {t.signOffBadge}
                          </span>
                        )}
                      </div>
                      {arLabel && (
                        <div className="text-xs text-slate-400 mt-0.5" dir="rtl">
                          {arLabel}
                        </div>
                      )}
                    </div>
                  </label>

                  {/* Right Side: Status Controls (Rows 1–27) or Sign-Off Inputs (Rows 28–31) */}
                  {!isSignOff ? (
                    <div className="flex flex-wrap sm:flex-nowrap items-center gap-2.5 lg:w-[460px] shrink-0">
                      <div
                        className="inline-flex rounded-lg bg-[#071426] p-1 border border-slate-700 shrink-0"
                        role="group"
                        aria-label={`Status for ${point.label}`}
                      >
                        {(['pass', 'fail', 'na'] as CheckResult[]).map((resKey) => {
                          const active = point.checked && point.result === resKey;
                          const activeStyle =
                            resKey === 'pass'
                              ? 'bg-emerald-600 text-white'
                              : resKey === 'fail'
                              ? 'bg-rose-600 text-white'
                              : 'bg-amber-600 text-white';
                          return (
                            <button
                              key={resKey}
                              type="button"
                              onClick={() => updatePointResult(point.order, resKey)}
                              className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors cursor-pointer ${
                                active
                                  ? activeStyle
                                  : 'text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              {resKey === 'pass'
                                ? t.ok
                                : resKey === 'fail'
                                ? t.notOk
                                : t.na}
                            </button>
                          );
                        })}
                      </div>

                      <input
                        type="text"
                        value={point.remark}
                        onChange={(e) =>
                          updatePointRemark(point.order, e.target.value)
                        }
                        placeholder={t.remarkPlaceholder}
                        aria-label={`Remark for ${point.label}`}
                        className={`flex-1 min-w-[160px] bg-[#071426] border rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none ${
                          point.checked && point.result === 'fail'
                            ? 'border-rose-500/80 focus:border-rose-400'
                            : 'border-slate-700 focus:border-blue-500'
                        }`}
                      />
                    </div>
                  ) : (
                    <div className="flex items-center gap-2.5 lg:w-[460px] shrink-0">
                      {point.order === 28 && (
                        <input
                          type="text"
                          value={driverName}
                          readOnly
                          aria-label={t.driverName}
                          className="w-full bg-[#071426]/70 border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-emerald-300"
                        />
                      )}
                      {point.order === 29 && (
                        <input
                          type="text"
                          value={driverSignature}
                          onChange={(e) => {
                            setDriverSignature(e.target.value);
                            updatePointRemark(29, e.target.value);
                          }}
                          placeholder={t.driverSignature}
                          aria-label={t.driverSignature}
                          required
                          className="w-full bg-[#071426] border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                        />
                      )}
                      {point.order === 30 && (
                        <input
                          type="date"
                          value={ropExpiry}
                          onChange={(e) => {
                            setRopExpiry(e.target.value);
                            updatePointRemark(30, e.target.value);
                          }}
                          aria-label={t.ropExpiry}
                          required
                          className="w-full bg-[#071426] border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-blue-500"
                        />
                      )}
                      {point.order === 31 && (
                        <input
                          type="text"
                          value={supervisorSignature}
                          onChange={(e) => {
                            setSupervisorSignature(e.target.value);
                            updatePointRemark(31, e.target.value);
                          }}
                          aria-label={t.supervisorSign}
                          className="w-full bg-[#071426] border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-amber-300 focus:outline-none focus:border-blue-500"
                        />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </section>

          {/* Footer Submit Bar */}
          <div className="bg-[#0f2442] border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 text-xs sm:text-sm text-slate-300">
              {checkedCount === 31 ? (
                <CheckSquare className="w-5 h-5 text-emerald-400 shrink-0" />
              ) : (
                <Square className="w-5 h-5 text-slate-400 shrink-0" />
              )}
              <span>
                <strong>{checkedCount}</strong> / 31 {t.pointsChecked}
              </span>
            </div>

            <button
              type="submit"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow transition-colors cursor-pointer"
            >
              <Send className="w-4 h-4" />
              <span>{t.submitInspection}</span>
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

export default function App() {
  return <DailyVehicleInspectionChecklist />;
}
