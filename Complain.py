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

# ====== تحديث تلقائي ======
st_autorefresh(interval=1200000, key="auto_refresh")  # 20 دقيقة

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number"
]

sheets_dict = {}
for title in sheet_titles:
    try:
        sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
    except Exception as e:
        try:
            ss = client.open(SHEET_NAME)
            sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")
        except Exception as e2:
            st.error(f"خطأ في الوصول/إنشاء ورقة: {title} - {e2}")
            raise

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== تحميل البيانات مع caching ======
def load_sheet(sheet, key):
    if key not in st.session_state:
        try:
            st.session_state[key] = sheet.get_all_values()
        except Exception:
            st.session_state[key] = []
    return st.session_state[key]

complaints_data = load_sheet(complaints_sheet, "complaints_data")
responded_data = load_sheet(responded_sheet, "responded_data")
archive_data = load_sheet(archive_sheet, "archive_data")
types_list = [row[0] for row in load_sheet(types_sheet, "types_data")[1:]] if load_sheet(types_sheet, "types_data") else []
return_warehouse_data = load_sheet(return_warehouse_sheet, "return_warehouse_data")[1:]
order_number_data = load_sheet(order_number_sheet, "order_number_data")[1:]
aramex_pending = load_sheet(aramex_sheet, "aramex_pending_data")
aramex_archived = load_sheet(aramex_archive, "aramex_archived_data")

# ====== دوال مساعدة ======
def get_returnwarehouse_record(order_id):
    for row in return_warehouse_data:
        if len(row) > 0 and str(row[0]) == str(order_id):
            return {
                "رقم الطلب": row[0],
                "الفاتورة": row[1] if len(row) > 1 else "",
                "التاريخ": row[2] if len(row) > 2 else "",
                "الزبون": row[3] if len(row) > 3 else "",
                "المبلغ": row[4] if len(row) > 4 else "",
                "رقم الشحنة": row[5] if len(row) > 5 else "",
                "البيان": row[6] if len(row) > 6 else ""
            }
    return None

def get_order_status(order_id):
    for row in order_number_data:
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f"الطلب الاساسي🚚 مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "الطلب الاساسي⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"

# ====== إعداد Aramex ======
client_info = st.secrets["aramex_credentials"]

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

def get_aramex_status(awb_number):
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
                    last_track = sorted(tracks, key=lambda tr: tr.find('UpdateDateTime').text if tr.find('UpdateDateTime') is not None else '', reverse=True)[0]
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

# ====== Cache لحالات Aramex ======
if "aramex_cache" not in st.session_state:
    st.session_state["aramex_cache"] = {}

def cached_aramex_status(awb):
    if not awb or str(awb).strip() == "":
        return ""
    if awb in st.session_state["aramex_cache"]:
        return st.session_state["aramex_cache"][awb]
    status = get_aramex_status(awb)
    st.session_state["aramex_cache"][awb] = status
    return status

# ====== دالة عرض الشكوى ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""
    order_status = get_order_status(comp_id)
    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        with st.form(key=f"form_{comp_id}_{sheet.title}"):
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
            new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0)
            new_notes = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb)
            new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb)
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
            if submitted_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                st.success("✅ تم التعديل")
            if submitted_delete:
                if safe_delete(sheet, i):
                    st.warning("🗑️ تم حذف الشكوى")
            if submitted_archive:
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        st.success("♻️ الشكوى انتقلت للأرشيف")
            if submitted_move:
                if not in_responded:
                    if safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            st.success("✅ انتقلت للإجراءات المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            st.success("✅ انتقلت للنشطة")

# ====== البحث عن شكوى ======
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

# ====== تسجيل شكوى جديدة ======
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
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if action.strip():
                safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb])
                st.success("✅ تم تسجيل الشكوى في المردودة")
            else:
                safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb])
                st.success("✅ تم تسجيل الشكوى في النشطة")
        else:
            st.error("⚠️ لازم تدخل رقم الشكوى وتختار نوع صحيح")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
if len(complaints_data) > 1:
    for i, row in enumerate(complaints_data[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== عرض الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة حسب النوع:")
if len(responded_data) > 1:
    types_in_responded = list({row[1] for row in responded_data[1:]})
    for complaint_type in types_in_responded:
        with st.expander(f"📌 نوع الشكوى: {complaint_type}"):
            type_rows = [(i, row) for i, row in enumerate(responded_data[1:], start=2) if row[1] == complaint_type]

            followup_1 = []
            followup_2 = []
            others = []

            for i, row in type_rows:
                comp_id = row[0]
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
    st.info("لا توجد إجراءات مردودة حالياً.")

# ====== عرض الأرشيف ======
st.header("🗄️ الأرشيف")
if len(archive_data) > 1:
    for i, row in enumerate(archive_data[1:], start=2):
        render_complaint(archive_sheet, i, row, in_archive=True)
else:
    st.info("لا توجد شكاوى مؤرشفة حالياً.")
