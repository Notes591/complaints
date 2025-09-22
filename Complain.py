import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import xml.etree.ElementTree as ET
import re

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheets_dict = {}
for title in ["Complaints", "Responded", "Archive", "Types", "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number"]:
    sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== تحميل الأنواع ======
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== بيانات ReturnWarehouse ======
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

# ====== بيانات Order Number ======
order_number_data = order_number_sheet.get_all_values()[1:]
def get_order_status(order_id):
    for row in order_number_data:
        if str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f" الطلب الاساسي🚚 مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "الطلب الاساسي⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
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
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== أرامكس ======
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
        if search_type == "Waybill":
            payload = {
                "ClientInfo": client_info,
                "Shipments": [awb_number],
                "Transaction": {"Reference1": "", "Reference2": "", "Reference3": "", "Reference4": "", "Reference5": ""},
                "LabelInfo": None
            }
            url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            payload = {
                "ClientInfo": client_info,
                "Transaction": {"Reference1": "", "Reference2": "", "Reference3": "", "Reference4": "", "Reference5": ""},
                "ReferenceType": "ConsigneeReference",
                "Reference": awb_number
            }
            url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipmentsByRef"
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

# ====== زر تحديث حالات أرامكس ======
if st.button("🔄 تحديث حالات أرامكس"):
    st.session_state["refresh_aramex"] = True

# ====== دالة عرض الشكوى ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    # إشعارات بجانب رقم الشكوى
    notifications = []
    if outbound_awb and st.session_state.get("refresh_aramex"):
        status = get_aramex_status(outbound_awb)
        if "Delivered" in status:
            notifications.append("🚚 Outbound Delivered")
    if inbound_awb and st.session_state.get("refresh_aramex"):
        status = get_aramex_status(inbound_awb)
        if "Delivered" in status:
            notifications.append("📦 Inbound Delivered")

    notif_text = " ".join(notifications)

    with st.expander(f"🆔 {comp_id} {notif_text} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
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
                safe_delete(sheet, i)
                st.warning("🗑️ تم حذف الشكوى")

            if submitted_archive:
                safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                safe_delete(sheet, i)
                st.success("♻️ الشكوى انتقلت للأرشيف")

            if submitted_move:
                if not in_responded:
                    safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                    safe_delete(sheet, i)
                    st.success("✅ اتنقلت للإجراءات المردودة")
                else:
                    safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                    safe_delete(sheet, i)
                    st.success("✅ اتنقلت للنشطة")

# ====== البحث ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى")
if search_id.strip():
    found = False
    for i, row in enumerate(complaints_sheet.get_all_values()[1:], start=2):
        if str(row[0]) == search_id:
            st.success("✅ موجودة في النشطة")
            render_complaint(complaints_sheet, i, row)
            found = True
    for i, row in enumerate(responded_sheet.get_all_values()[1:], start=2):
        if str(row[0]) == search_id:
            st.success("✅ موجودة في المردودة")
            render_complaint(responded_sheet, i, row, in_responded=True)
            found = True
    for i, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
        if str(row[0]) == search_id:
            st.success("✅ موجودة في الأرشيف")
            render_complaint(archive_sheet, i, row, in_archive=True)
            found = True
    if not found:
        st.error("⚠️ غير موجودة")

# ====== تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")
with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list)
    notes = st.text_area("📝 ملاحظات")
    action = st.text_area("✅ الإجراء")
    outbound_awb = st.text_input("✏️ Outbound AWB")
    inbound_awb = st.text_input("✏️ Inbound AWB")
    submitted = st.form_submit_button("➕ إضافة")
    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if action.strip():
                safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb])
                st.success("✅ أضيفت للمردودة")
            else:
                safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb])
                st.success("✅ أضيفت للنشطة")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة")
for i, row in enumerate(complaints_sheet.get_all_values()[1:], start=2):
    render_complaint(complaints_sheet, i, row)

# ====== الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة حسب النوع")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    types_in_responded = list({row[1] for row in responded_notes[1:]})
    for complaint_type in types_in_responded:
        st.subheader(f"📌 {complaint_type}")
        for i, row in enumerate(responded_notes[1:], start=2):
            if row[1] == complaint_type:
                render_complaint(responded_sheet, i, row, in_responded=True)

# ====== الأرشيف ======
st.header("📦 الأرشيف")
archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for i, row in enumerate(archived[1:51], start=2):
        render_complaint(archive_sheet, i, row, in_archive=True)

# ====== معلق أرامكس ======
st.header("🚚 معلق أرامكس")
with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input
