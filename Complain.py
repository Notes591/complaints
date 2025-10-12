# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import xml.etree.ElementTree as ET
import re
from streamlit_autorefresh import st_autorefresh

# ====== تحديث تلقائي (يمكن تغييره) ======
# ملاحظة: القيمة هنا بالميلي ثانية. المثال: 1,200,000 = 20 دقيقة
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== إعداد الاتصال بـ Google Sheets ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أسماء الأوراق ======
SHEET_NAME = "Complaints"
sheet_names = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number"
]

sheets_dict = {}
for title in sheet_names:
    try:
        sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
    except Exception as e:
        # إن لم توجد الورقة سنحاول إنشاؤها (أمان)
        try:
            ss = client.open(SHEET_NAME)
            sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")
        except Exception as e2:
            st.error(f"خطأ في الوصول أو إنشاء ورقة: {title} - {e2}")
            raise

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ====== صفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== دوال Retry آمنة ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError as e:
            time.sleep(delay)
        except Exception as e:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except gspread.exceptions.APIError as e:
            time.sleep(delay)
        except Exception as e:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except gspread.exceptions.APIError as e:
            time.sleep(delay)
        except Exception as e:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== بيانات Types, ReturnWarehouse, OrderNumber ======
# نحمّل الأنواع فقط مرة ونخزنها
try:
    types_list = [row[0] for row in types_sheet.get_all_values()[1:]]
except Exception:
    types_list = []

return_warehouse_data = return_warehouse_sheet.get_all_values()[1:]
def get_returnwarehouse_record(order_id):
    for row in return_warehouse_data:
        if str(row[0]) == str(order_id):
            return {
                "رقم الطلب": row[0],
                "الفاتورة": row[1],
                "التاريخ": row[2],
                "الزبون": row[3],
                "المبلغ": row[4],
                "رقم الشحنة": row[5],
                "البيان": row[6]
            }
    return None

order_number_data = order_number_sheet.get_all_values()[1:]
def get_order_status(order_id):
    for row in order_number_data:
        # افتراض: عمود 1 هو order id
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f"الطلب الاساسي🚚 مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "الطلب الاساسي⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"

# ====== إعداد Aramex (API) ======
client_info = {
    "UserName": "fitnessworld525@gmail.com",
    "Password": "Aa12345678@",
    "Version": "v1",
    "AccountNumber": "71958996",
    "AccountPin": "657448",
    "AccountEntity": "RUH",
    "AccountCountryCode": "SA"
}

def remove_xml_namespaces(xml_str):
    xml_str = re.sub(r'xmlns(:\w+)?="[^"]+"', '', xml_str)
    xml_str = re.sub(r'(<\/?)(\w+:)', r'\1', xml_str)
    return xml_str

def extract_reference(tracking_result):
    for ref_tag in ['Reference1', 'Reference2', 'Reference3', 'Reference4', 'Reference5']:
        ref_elem = tracking_result.find(ref_tag)
        if ref_elem is not None and ref_elem.text and ref_elem.text.strip() != "":
            return ref_elem.text.strip()
    return ""

def get_aramex_status(awb_number, search_type="Waybill"):
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "ClientInfo": client_info,
            "Shipments": [awb_number],
            "Transaction": {"Reference1": "", "Reference2": "", "Reference3": "", "Reference4": "", "Reference5": ""},
            "LabelInfo": None
        }
        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"❌ فشل الاتصال - كود {response.status_code}"
        xml_content = response.content.decode('utf-8')
        xml_content = remove_xml_namespaces(xml_content)
        root = ET.fromstring(xml_content)
        tracking_results = root.find('TrackingResults')
        if tracking_results is None or len(tracking_results) == 0:
            return "❌ لا توجد حالة متاحة"
        keyvalue = tracking_results.find('KeyValueOfstringArrayOfTrackingResultmFAkxlpY')
        if keyvalue is not None:
            tracking_array = keyvalue.find('Value')
            if tracking_array is not None:
                tracks = tracking_array.findall('TrackingResult')
                if tracks:
                    last_track = sorted(
                        tracks,
                        key=lambda tr: tr.find('UpdateDateTime').text if tr.find('UpdateDateTime') is not None else '',
                        reverse=True
                    )[0]
                    desc = last_track.find('UpdateDescription').text if last_track.find('UpdateDescription') is not None else "—"
                    date = last_track.find('UpdateDateTime').text if last_track.find('UpdateDateTime') is not None else "—"
                    loc = last_track.find('UpdateLocation').text if last_track.find('UpdateLocation') is not None else "—"
                    reference = extract_reference(last_track)
                    info = f"{desc} بتاريخ {date} في {loc}"
                    if reference:
                        info += f" | الرقم المرجعي: {reference}"
                    return info
        return "❌ لا توجد حالة متاحة"
    except Exception as e:
        return f"خطأ في جلب الحالة: {e}"

# ====== Cache لنتائج Aramex (لتقليل النداءات) ======
@st.cache_data(ttl=300)
def cached_aramex_status(awb):
    # نوفر حماية لو awb فارغ
    if not awb or str(awb).strip() == "":
        return ""
    return get_aramex_status(awb)

# ====== تهيئة session_state لتحميل البيانات مرة واحدة ======
def load_sheet_to_session(sheet, key_name):
    if "sheet_data" not in st.session_state:
        st.session_state["sheet_data"] = {}
    if key_name not in st.session_state["sheet_data"]:
        try:
            st.session_state["sheet_data"][key_name] = sheet.get_all_values()[1:]
        except Exception:
            st.session_state["sheet_data"][key_name] = []

# تحميل جميع الأوراق الأساسية
load_sheet_to_session(complaints_sheet, "Complaints")
load_sheet_to_session(responded_sheet, "Responded")
load_sheet_to_session(archive_sheet, "Archive")
load_sheet_to_session(aramex_sheet, "معلق ارامكس")
load_sheet_to_session(aramex_archive, "أرشيف أرامكس")
# لا نحمل Types لأننا استخدمنا أعلاه، لكن يمكن تحديثها لاحقًا إذا احتجت.

# ====== دالة عرض الشكوى محسنة (تعمل على session_state) ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    # نتأكد من بنية الصف
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    # تأكد أن البيانات المحلية مُحمّلة
    sheet_key = sheet.title
    load_sheet_to_session(sheet, sheet_key)

    # local index في البيانات المخزنة محليًا
    local_index = i - 2
    # حماية لو تغيرت أحجام القوائم
    if local_index >= len(st.session_state["sheet_data"][sheet_key]):
        # نسق fallback
        local_row = [comp_id, comp_type, notes, action, date_added, restored, outbound_awb, inbound_awb]
        st.session_state["sheet_data"][sheet_key].append(local_row)
    else:
        local_row = st.session_state["sheet_data"][sheet_key][local_index]

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        with st.form(key=f"form_{comp_id}_{sheet_key}"):
            st.write(f"📌 النوع الحالي: {comp_type}")
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            rw_record = get_returnwarehouse_record(comp_id)
            if rw_record:
                st.info(
                    f"📦 سجل من ReturnWarehouse:\n"
                    f"رقم الطلب: {rw_record['رقم الطلب']}\n"
                    f"الفاتورة: {rw_record['الفاتورة']}\n"
                    f"التاريخ: {rw_record['التاريخ']}\n"
                    f"الزبون: {rw_record['الزبون']}\n"
                    f"المبلغ: {rw_record['المبلغ']}\n"
                    f"رقم الشحنة: {rw_record['رقم الشحنة']}\n"
                    f"البيان: {rw_record['البيان']}"
                )

            # عناصر التعديل
            new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0)
            new_notes = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb)
            new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb)

            # عرض حالة أرامكس مؤقتًا (مخزن)
            if new_outbound:
                st.info(f"🚚 Outbound AWB: {new_outbound} | الحالة: {cached_aramex_status(new_outbound)}")
            if new_inbound:
                st.info(f"📦 Inbound AWB: {new_inbound} | الحالة: {cached_aramex_status(new_inbound)}")

            col1, col2, col3, col4 = st.columns(4)
            submitted_save = col1.form_submit_button("💾 حفظ")
            submitted_delete = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")
            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ نقل للإجراءات المردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع للنشطة")

            # ===== معالجة الأزرار بدون full rerun (نحدث remote ثم local session_state) =====
            if submitted_save:
                # تحديث جوجل شيت
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                # تحديث محلي
                st.session_state["sheet_data"][sheet_key][local_index] = [
                    comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound
                ]
                st.success("✅ تم الحفظ بنجاح")

            if submitted_delete:
                if safe_delete(sheet, i):
                    # تحديث محلي
                    try:
                        st.session_state["sheet_data"][sheet_key].pop(local_index)
                    except Exception:
                        pass
                    st.warning("🗑️ تم حذف الشكوى")

            if submitted_archive:
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        try:
                            st.session_state["sheet_data"][sheet_key].pop(local_index)
                        except Exception:
                            pass
                        # كما نحدث الـ session_state للأرشيف محليًا (حتى يظهر فوريًا)
                        load_sheet_to_session(archive_sheet, "Archive")
                        st.session_state["sheet_data"]["Archive"].insert(0, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                        st.success("♻️ الشكوى انتقلت للأرشيف")

            if submitted_move:
                if not in_responded:
                    # نقل إلى responded
                    if safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            try:
                                st.session_state["sheet_data"][sheet_key].pop(local_index)
                            except Exception:
                                pass
                            load_sheet_to_session(responded_sheet, "Responded")
                            st.session_state["sheet_data"]["Responded"].insert(0, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                            st.success("✅ انتقلت للإجراءات المردودة")
                else:
                    # نقل إلى complaints (الرجوع للنشطة)
                    if safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            try:
                                st.session_state["sheet_data"][sheet_key].pop(local_index)
                            except Exception:
                                pass
                            load_sheet_to_session(complaints_sheet, "Complaints")
                            st.session_state["sheet_data"]["Complaints"].insert(0, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                            st.success("✅ انتقلت للنشطة")

# ====== قسم البحث عن شكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")
if search_id.strip():
    found = False
    for sheet_obj, in_responded, in_archive in [
        (complaints_sheet, False, False),
        (responded_sheet, True, False),
        (archive_sheet, False, True)
    ]:
        try:
            data = sheet_obj.get_all_values()
        except Exception:
            data = []
        for i, row in enumerate(data[1:], start=2) if data else []:
            if len(row) > 0 and str(row[0]) == search_id:
                st.success(f"✅ الشكوى موجودة في {'المردودة' if in_responded else 'الأرشيف' if in_archive else 'النشطة'}")
                render_complaint(sheet_obj, i, row, in_responded=in_responded, in_archive=in_archive)
                found = True
                break
        if found:
            break
    if not found:
        st.error("⚠️ لم يتم العثور على الشكوى")

# ====== تسجيل شكوى جديدة (تحسين: يحدث محليًا وفوريًا) ======
st.header("➕ تسجيل شكوى جديدة")
with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    notes = st.text_area("📝 ملاحظات الشكوى")
    action = st.text_area("✅ الإجراء المتخذ")
    outbound_awb = st.text_input("✏️ Outbound AWB")
    inbound_awb = st.text_input("✏️ Inbound AWB")
    submitted = st.form_submit_button("➕ إضافة")

    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            # قراءة محلية عن طريق API (يمكن تحسين لاحقًا)
            try:
                complaints = complaints_sheet.get_all_records()
            except Exception:
                complaints = []
            try:
                responded = responded_sheet.get_all_records()
            except Exception:
                responded = []
            try:
                archive = archive_sheet.get_all_records()
            except Exception:
                archive = []

            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_active_ids = [str(c.get("ID", "")) for c in complaints] + [str(r.get("ID", "")) for r in responded]
            all_archive_ids = [str(a.get("ID", "")) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                # استرجاع من الأرشيف (إذا وجد)
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes = row[2] if len(row) > 2 else ""
                        restored_action = row[3] if len(row) > 3 else ""
                        restored_type = row[1] if len(row) > 1 else ""
                        restored_outbound = row[6] if len(row) > 6 else ""
                        restored_inbound = row[7] if len(row) > 7 else ""
                        if safe_append(complaints_sheet, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound]):
                            if safe_delete(archive_sheet, idx):
                                # تحديث محلي للأرشيف و النشطة
                                load_sheet_to_session(archive_sheet, "Archive")
                                try:
                                    # نحذف العنصر من النسخة المحلية للأرشيف
                                    for j, rr in enumerate(st.session_state["sheet_data"]["Archive"]):
                                        if str(rr[0]) == comp_id:
                                            st.session_state["sheet_data"]["Archive"].pop(j)
                                            break
                                except Exception:
                                    pass
                                load_sheet_to_session(complaints_sheet, "Complaints")
                                st.session_state["sheet_data"]["Complaints"].insert(0, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound])
                                st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                        break
            else:
                if action.strip():
                    # تذهب مباشرة للمردودة
                    if safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb]):
                        load_sheet_to_session(responded_sheet, "Responded")
                        st.session_state["sheet_data"]["Responded"].insert(0, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb])
                        st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb]):
                        load_sheet_to_session(complaints_sheet, "Complaints")
                        st.session_state["sheet_data"]["Complaints"].insert(0, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb])
                        st.success("✅ تم تسجيل الشكوى في النشطة")
        else:
            st.error("⚠️ لازم تدخل رقم الشكوى وتختار نوع صحيح")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
load_sheet_to_session(complaints_sheet, "Complaints")
active_notes = st.session_state["sheet_data"]["Complaints"]
if active_notes and len(active_notes) > 0:
    for idx, row in enumerate(active_notes, start=2):
        # row قد تكون أقصر أو أطول، نمرره كما هو (render_complaint يتعامل مع ذلك)
        render_complaint(complaints_sheet, idx, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== عرض الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة حسب النوع:")
load_sheet_to_session(responded_sheet, "Responded")
responded_notes = st.session_state["sheet_data"]["Responded"]
if responded_notes and len(responded_notes) > 0:
    types_in_responded = list({row[1] if len(row) > 1 else "بدون نوع" for row in responded_notes})
    for complaint_type in types_in_responded:
        with st.expander(f"📌 نوع الشكوى: {complaint_type}"):
            # نجمع صفوف ذلك النوع محليًا
            type_rows = [(i+2, r) for i, r in enumerate(responded_notes) if (len(r) > 1 and r[1] == complaint_type)]
            followup_1 = []
            followup_2 = []
            others = []
            for i, row in type_rows:
                comp_id = row[0] if len(row) > 0 else ""
                outbound_awb = row[6] if len(row) > 6 else ""
                inbound_awb = row[7] if len(row) > 7 else ""
                rw_record = get_returnwarehouse_record(comp_id)
                delivered = False
                for awb in [outbound_awb, inbound_awb]:
                    if awb and "Delivered" in cached_aramex_status(awb):
                        delivered = True
                        break
                if delivered and rw_record:
                    followup_2.append((i, row))
                elif delivered and not rw_record:
                    followup_1.append((i, row))
                else:
                    others.append((i, row))

            if followup_1:
                with st.expander("📋 جاهز للمتابعة 1"):
                    for i, row in followup_1:
                        render_complaint(responded_sheet, i, row, in_responded=True)

            if followup_2:
                with st.expander("📋 جاهز للمتابعة 2"):
                    for i, row in followup_2:
                        render_complaint(responded_sheet, i, row, in_responded=True)

            if others:
                with st.expander("📋 غير جاهز للمتابعة"):
                    for i, row in others:
                        render_complaint(responded_sheet, i, row, in_responded=True)
else:
    st.info("لا توجد شكاوى مردودة حالياً.")

# ====== عرض الأرشيف (مع تحميل تدريجي) ======
st.header("📦 الأرشيف:")
load_sheet_to_session(archive_sheet, "Archive")
archived = st.session_state["sheet_data"]["Archive"]
if archived and len(archived) > 0:
    if "archive_show_count" not in st.session_state:
        st.session_state["archive_show_count"] = 50
    show_count = st.session_state["archive_show_count"]
    for offset, row in enumerate(archived[:show_count], start=2):
        render_complaint(archive_sheet, offset, row, in_archive=True)
    if len(archived) > show_count:
        if st.button("عرض المزيد من الأرشيف"):
            st.session_state["archive_show_count"] += 50
            st.experimental_rerun()
else:
    st.info("لا توجد شكاوى مؤرشفة حالياً.")

# ====== (الآن) قسم إضافة "معلق أرامكس" — حسب طلبك يكون قبل عرض معلق أرامكس ======
# هذا القسم يضيف سجل إلى ورقة "معلق ارامكس" ويحدّث session_state فورًا
st.markdown("---")
st.header("🚚 إضافة طلب لمعلق أرامكس")
with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input("📌 الحالة")
    action = st.text_area("✅ الإجراء المتخذ")
    submitted = st.form_submit_button("➕ إضافة")
    if submitted:
        if order_id.strip() and status.strip() and action.strip():
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if safe_append(aramex_sheet, [order_id, status, date_now, action]):
                load_sheet_to_session(aramex_sheet, "معلق ارامكس")
                # نضعه في أول القائمة محليًا ليظهر فورًا
                st.session_state["sheet_data"]["معلق ارامكس"].insert(0, [order_id, status, date_now, action])
                st.success("✅ تم تسجيل الطلب في معلق أرامكس")
            else:
                st.error("❌ فشل في تسجيل الطلب، حاول مرة أخرى")
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

# ====== عرض معلق أرامكس (القسم الذي عرضته أنت) ======
st.markdown("---")
st.header("📦 معلق أرامكس:")
load_sheet_to_session(aramex_sheet, "معلق ارامكس")
aramex_data = st.session_state["sheet_data"]["معلق ارامكس"]
if aramex_data and len(aramex_data) > 0:
    st.subheader("📋 قائمة الطلبات المعلقة")
    for idx, row in enumerate(aramex_data, start=2):
        # افتراض: row = [order_id, status, date_added, action]
        while len(row) < 4:
            row.append("")
        order_id = row[0]
        status = row[1]
        date_added = row[2]
        action = row[3]
        with st.expander(f"📦 طلب {order_id}"):
            st.write(f"📌 الحالة الحالية: {status}")
            st.write(f"✅ الإجراء الحالي: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            with st.form(key=f"form_aramex_{order_id}"):
                new_status = st.text_input("✏️ عدل الحالة", value=status)
                new_action = st.text_area("✏️ عدل الإجراء", value=action)
                col1, col2, col3 = st.columns(3)
                submitted_save = col1.form_submit_button("💾 حفظ")
                submitted_delete = col2.form_submit_button("🗑️ حذف")
                submitted_archive = col3.form_submit_button("📦 أرشفة")
                if submitted_save:
                    # تحديث remote ثم local
                    if safe_update(aramex_sheet, f"B{idx}", [[new_status]]) and safe_update(aramex_sheet, f"D{idx}", [[new_action]]):
                        # تحديث محلي للصف
                        try:
                            st.session_state["sheet_data"]["معلق ارامكس"][idx - 2][1] = new_status
                            st.session_state["sheet_data"]["معلق ارامكس"][idx - 2][3] = new_action
                        except Exception:
                            pass
                        st.success("✅ تم تعديل الطلب")
                if submitted_delete:
                    if safe_delete(aramex_sheet, idx):
                        try:
                            st.session_state["sheet_data"]["معلق ارامكس"].pop(idx - 2)
                        except Exception:
                            pass
                        st.warning("🗑️ تم حذف الطلب")
                if submitted_archive:
                    if safe_append(aramex_archive, [order_id, new_status, date_added, new_action]):
                        if safe_delete(aramex_sheet, idx):
                            # تحديث محلي: احذف من pending وأضف للأرشيف المحلي
                            try:
                                st.session_state["sheet_data"]["معلق ارامكس"].pop(idx - 2)
                            except Exception:
                                pass
                            load_sheet_to_session(aramex_archive, "أرشيف أرامكس")
                            st.session_state["sheet_data"]["أرشيف أرامكس"].insert(0, [order_id, new_status, date_added, new_action])
                            st.success("♻️ تم أرشفة الطلب")
else:
    st.info("لا توجد شكاوى أرامكس معلقة.")

# ====== عرض أرشيف أرامكس ======
st.markdown("---")
st.header("📦 أرشيف أرامكس:")
load_sheet_to_session(aramex_archive, "أرشيف أرامكس")
aramex_archived = st.session_state["sheet_data"]["أرشيف أرامكس"]
if aramex_archived and len(aramex_archived) > 0:
    for idx, row in enumerate(aramex_archived, start=2):
        while len(row) < 4:
            row.append("")
        order_id = row[0]
        status = row[1]
        date_added = row[2]
        action = row[3]
        with st.expander(f"📦 أرشيف طلب {order_id}"):
            st.write(f"📌 الحالة عند الأرشفة: {status}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            # نسمح بالعرض فقط أو إرجاعه لمنصة المعلق (اختياري)
            col1, col2 = st.columns(2)
            if col1.button(f"⬅️ إرجاع {order_id} إلى معلق ارامكس"):
                # إعادة الإدراج في معلق ارامكس
                if safe_append(aramex_sheet, [order_id, status, date_added, action]):
                    # حذف من أرشيف أرامكس remote
                    if safe_delete(aramex_archive, idx):
                        # تحديث محلي
                        try:
                            st.session_state["sheet_data"]["أرشيف أرامكس"].pop(idx - 2)
                        except Exception:
                            pass
                        load_sheet_to_session(aramex_sheet, "معلق ارامكس")
                        st.session_state["sheet_data"]["معلق ارامكس"].insert(0, [order_id, status, date_added, action])
                        st.success(f"✅ تم إعادة {order_id} لمعلق ارامكس")
            if col2.button(f"🗑️ حذف {order_id} من الأرشيف"):
                if safe_delete(aramex_archive, idx):
                    try:
                        st.session_state["sheet_data"]["أرشيف أرامكس"].pop(idx - 2)
                    except Exception:
                        pass
                    st.warning(f"🗑️ تم حذف {order_id} من أرشيف أرامكس")
else:
    st.info("لا توجد شكاوى أرامكس مؤرشفة.")

# ====== نهاية البرنامج ======
st.caption("تذكير: التغييرات تحفظ على Google Sheets و تظهر فورًا في الواجهة (session_state) بدون إعادة تحميل كامل الصفحة.")
