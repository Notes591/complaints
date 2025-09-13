import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import requests
import xml.etree.ElementTree as ET

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

# ====== دالة لجلب حالة شحنة أرامكس (XML + JSON fallback) ======
def get_aramex_status(awb_number):
    if not awb_number.strip():
        return "رقم الشحنة فارغ"
    try:
        client_info = {
            "UserName": "fitnessworld525@gmail.com",
            "Password": "Aa12345678@",
            "Version": "v1",
            "AccountNumber": "71958996",
            "AccountPin": "657448",
            "AccountEntity": "RUH",
            "AccountCountryCode": "SA"
        }

        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc"
        payload = {
            "ClientInfo": client_info,
            "Transaction": {"Reference1": "12345"},
            "Shipments": [awb_number],
            "GetLastUpdateOnly": True
        }

        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if not response.text.strip():
            return "❌ لم يتم الحصول على رد من أرامكس"

        # محاولة تحويل الرد ل XML
        root = ET.fromstring(response.text)
        ns = {'ns': 'http://ws.aramex.net/ShippingAPI/v1/'}
        track_result = root.find('.//ns:TrackingResult', ns)
        if track_result is None:
            return "❌ لم يتم العثور على نتيجة تتبع"

        last_update = track_result.find('.//ns:Update', ns)
        if last_update is None:
            return "لا توجد حالة متاحة"

        status = last_update.find('ns:Status', ns)
        date = last_update.find('ns:Date', ns)
        return f"{status.text if status is not None else 'غير محددة'} بتاريخ {date.text if date is not None else ''}"

    except Exception as e:
        return f"خطأ في جلب الحالة: {e}"

# ====== دالة عرض الشكوى مع تعديل النوع ======
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

        if outbound_awb:
            st.info(f"🚚 Outbound AWB: {outbound_awb} | الحالة: {get_aramex_status(outbound_awb)}")
        if inbound_awb:
            st.info(f"📦 Inbound AWB: {inbound_awb} | الحالة: {get_aramex_status(inbound_awb)}")

        # تعديل النوع والملاحظات والإجراء
        new_type = st.selectbox("✏️ عدل نوع الشكوى",
                                [comp_type] + [t for t in types_list if t != comp_type],
                                index=0, key=f"type_{comp_id}_{sheet.title}")
        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{comp_id}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{comp_id}_{sheet.title}")

        col1, col2, col3, col4 = st.columns(4)

        if col1.button("💾 حفظ", key=f"save_{comp_id}_{sheet.title}"):
            safe_update(sheet, f"B{i}", [[new_type]])
            safe_update(sheet, f"C{i}", [[new_notes]])
            safe_update(sheet, f"D{i}", [[new_action]])
            st.success("✅ تم التعديل")
            st.rerun()

        if col2.button("🗑️ حذف", key=f"delete_{comp_id}_{sheet.title}"):
            safe_delete(sheet, i)
            st.warning("🗑️ تم حذف الشكوى")
            st.rerun()

        if col3.button("📦 أرشفة", key=f"archive_{comp_id}_{sheet.title}"):
            safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, outbound_awb, inbound_awb])
            time.sleep(0.5)
            safe_delete(sheet, i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.rerun()

        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{comp_id}_{sheet.title}"):
                safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, outbound_awb, inbound_awb])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للإجراءات المردودة")
                st.rerun()
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{comp_id}_{sheet.title}"):
                safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, outbound_awb, inbound_awb])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للنشطة")
                st.rerun()
