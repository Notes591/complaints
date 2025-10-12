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

# ====== بيانات ReturnWarehouse و Order Number ======
return_warehouse_data = return_warehouse_sheet.get_all_values()[1:]
order_number_data = order_number_sheet.get_all_values()[1:]

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

# ====== تحميل البيانات مرة واحدة في session_state ======
def load_data():
    if "complaints" not in st.session_state:
        st.session_state.complaints = complaints_sheet.get_all_values()[1:]
    if "responded" not in st.session_state:
        st.session_state.responded = responded_sheet.get_all_values()[1:]
    if "archive" not in st.session_state:
        st.session_state.archive = archive_sheet.get_all_values()[1:]
    if "aramex_pending" not in st.session_state:
        st.session_state.aramex_pending = aramex_sheet.get_all_values()[1:]
    if "aramex_archive" not in st.session_state:
        st.session_state.aramex_archive = aramex_archive.get_all_values()[1:]

load_data()

# ====== دالة عرض الشكوى مع تحديث فقط الصف ======
def render_complaint_local(sheet_name, i, row):
    while len(row) < 8:
        row.append("")
    comp_id, comp_type, notes, action, date_added, restored, outbound_awb, inbound_awb = row

    order_status = get_order_status(comp_id)

    session_key = f"{sheet_name}_{comp_id}"
    if session_key not in st.session_state:
        st.session_state[session_key] = {
            "comp_type": comp_type,
            "notes": notes,
            "action": action,
            "outbound_awb": outbound_awb,
            "inbound_awb": inbound_awb
        }

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        st.write(f"📌 النوع الحالي: {st.session_state[session_key]['comp_type']}")
        st.write(f"📝 الملاحظات: {st.session_state[session_key]['notes']}")
        st.write(f"✅ الإجراء: {st.session_state[session_key]['action']}")
        st.caption(f"📅 تاريخ التسجيل: {date_added}")

        new_type = st.selectbox("✏️ عدل نوع الشكوى", [st.session_state[session_key]['comp_type']] + [t for t in types_list if t != st.session_state[session_key]['comp_type']], key=f"type_{session_key}")
        new_notes = st.text_area("✏️ عدل الملاحظات", value=st.session_state[session_key]['notes'], key=f"notes_{session_key}")
        new_action = st.text_area("✏️ عدل الإجراء", value=st.session_state[session_key]['action'], key=f"action_{session_key}")
        new_outbound = st.text_input("✏️ Outbound AWB", value=st.session_state[session_key]['outbound_awb'], key=f"out_{session_key}")
        new_inbound = st.text_input("✏️ Inbound AWB", value=st.session_state[session_key]['inbound_awb'], key=f"in_{session_key}")

        col1, col2 = st.columns(2)
        if col1.button("💾 حفظ", key=f"save_{session_key}"):
            safe_update(complaints_sheet, f"B{i}", [[new_type]])
            safe_update(complaints_sheet, f"C{i}", [[new_notes]])
            safe_update(complaints_sheet, f"D{i}", [[new_action]])
            safe_update(complaints_sheet, f"G{i}", [[new_outbound]])
            safe_update(complaints_sheet, f"H{i}", [[new_inbound]])
            st.session_state[session_key].update({
                "comp_type": new_type,
                "notes": new_notes,
                "action": new_action,
                "outbound_awb": new_outbound,
                "inbound_awb": new_inbound
            })
            st.success("✅ تم تعديل الشكوى بدون إعادة تحميل الصفحة")
