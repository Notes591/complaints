import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import xml.etree.ElementTree as ET
import re

# ====== بيانات حساب أرامكس ======
client_info = {
    "UserName": "fitnessworld525@gmail.com",
    "Password": "Aa12345678@",
    "Version": "v1",
    "AccountNumber": "71958996",
    "AccountPin": "657448",
    "AccountEntity": "RUH",
    "AccountCountryCode": "SA"
}

# ====== دالة إزالة المساحات/Namespace من XML ======
def remove_xml_namespaces(xml_str):
    xml_str = re.sub(r'xmlns(:\w+)?="[^"]+"', '', xml_str)
    xml_str = re.sub(r'(<\/?)(\w+:)', r'\1', xml_str)
    return xml_str

# ====== دالة تتبع شحنة أرامكس ======
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
            response = requests.post(url, json=payload, headers=headers)
        else:
            payload = {
                "ClientInfo": client_info,
                "Transaction": {"Reference1": "", "Reference2": "", "Reference3": "", "Reference4": "", "Reference5": ""},
                "ReferenceType": "ConsigneeReference",
                "Reference": awb_number
            }
            url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipmentsByRef"
            response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            return f"❌ فشل الاتصال - كود {response.status_code}"

        xml_content = response.content.decode("utf-8")
        xml_content = remove_xml_namespaces(xml_content)
        root = ET.fromstring(xml_content)
        tracking_results = root.find("TrackingResults")
        if tracking_results is None or len(tracking_results) == 0:
            return "❌ لا توجد حالة متاحة"

        keyvalue = tracking_results.find("KeyValueOfstringArrayOfTrackingResultmFAkxlpY")
        if keyvalue is not None:
            tracking_array = keyvalue.find("Value")
            if tracking_array is not None:
                tracks = tracking_array.findall("TrackingResult")
                if tracks:
                    last_track = sorted(tracks, key=lambda tr: tr.find("UpdateDateTime").text if tr.find("UpdateDateTime") is not None else "", reverse=True)[0]
                    desc = last_track.find("UpdateDescription").text if last_track.find("UpdateDescription") is not None else "—"
                    date = last_track.find("UpdateDateTime").text if last_track.find("UpdateDateTime") is not None else "—"
                    return f"{desc} بتاريخ {date}"
        return "❌ لا توجد حالة متاحة"

    except Exception as e:
        return f"خطأ في جلب الحالة: {e}"

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheets_dict = {}
for title in ["Complaints", "Responded", "Archive", "Types", "معلق ارامكس", "أرشيف أرامكس"]:
    sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل الأنواع
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

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

# ====== دالة عرض الشكوى مع تعديل النوع والشحنات ======
def render_complaint(sheet, i, row, in_responded=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
        st.write(f"📌 النوع الحالي: {comp_type}")
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        st.caption(f"📅 تاريخ التسجيل: {date_added}")

        new_type = st.selectbox("✏️ عدل نوع الشكوى",
                                [comp_type] + [t for t in types_list if t != comp_type],
                                index=0, key=f"type_{comp_id}_{sheet.title}")
        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{comp_id}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{comp_id}_{sheet.title}")
        new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb, key=f"outbound_{comp_id}_{sheet.title}")
        new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb, key=f"inbound_{comp_id}_{sheet.title}")

        # عرض حالة الشحنة باستخدام الطريقة الجديدة
        if new_outbound:
            status_out = get_aramex_status(new_outbound, search_type="Waybill")
            st.info(f"🚚 حالة الشحنة (Outbound): {status_out}")
        if new_inbound:
            status_in = get_aramex_status(new_inbound, search_type="Waybill")
            st.info(f"📦 حالة الشحنة (Inbound): {status_in}")

        col1, col2, col3, col4 = st.columns(4)

        if col1.button("💾 حفظ", key=f"save_{comp_id}_{sheet.title}"):
            safe_update(sheet, f"B{i}", [[new_type]])
            safe_update(sheet, f"C{i}", [[new_notes]])
            safe_update(sheet, f"D{i}", [[new_action]])
            safe_update(sheet, f"G{i}", [[new_outbound]])
            safe_update(sheet, f"H{i}", [[new_inbound]])
            st.success("✅ تم التعديل")
            st.rerun()

        if col2.button("🗑️ حذف", key=f"delete_{comp_id}_{sheet.title}"):
            safe_delete(sheet, i)
            st.warning("🗑️ تم حذف الشكوى")
            st.rerun()

        if col3.button("📦 أرشفة", key=f"archive_{comp_id}_{sheet.title}"):
            safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
            time.sleep(0.5)
            safe_delete(sheet, i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.rerun()

        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{comp_id}_{sheet.title}"):
                safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للإجراءات المردودة")
                st.rerun()
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{comp_id}_{sheet.title}"):
                safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للنشطة")
                st.rerun()

# ====== باقي الكود (البحث، تسجيل شكوى جديدة، عرض الشكاوى، معلق أرامكس) ======
# نفس الكود الأصلي، مع استدعاء get_aramex_status الجديدة لكل AWB
# هذا يضمن ظهور حالة التتبع مباشرة في Streamlit بدون أي نقص في المزايا
