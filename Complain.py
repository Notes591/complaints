import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import requests
import json

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

# ====== دالة لجلب حالة شحنة أرامكس ======
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

        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        payload = {
            "ClientInfo": client_info,
            "Transaction": {"Reference1": "12345"},
            "Shipments": [awb_number],
            "GetLastUpdateOnly": True
        }

        response = requests.post(url, json=payload, timeout=10)

        try:
            data = response.json()
        except json.JSONDecodeError:
            return f"خطأ: الرد ليس JSON"

        tracking_results = data.get("TrackingResults", [])
        if not tracking_results:
            return "لا توجد حالة متاحة"

        last_update = tracking_results[0].get("Update", [])
        if not last_update:
            return "لا توجد حالة متاحة"

        last_status = last_update[-1].get("Status", "غير محددة")
        last_date = last_update[-1].get("Date", "")
        return f"{last_status} بتاريخ {last_date}"

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

# ====== البحث عن شكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("🆔 اكتب رقم الشكوى")

if st.button("🔍 بحث"):
    if search_id.strip():
        found = False
        for sheet in [complaints_sheet, responded_sheet, archive_sheet]:
            data = sheet.get_all_values()
            for i, row in enumerate(data[1:], start=2):
                if row[0] == search_id:
                    found = True
                    render_complaint(sheet, i, row, in_responded=(sheet == responded_sheet))
                    st.stop()
        if not found:
            st.error("❌ لم يتم العثور على الشكوى")

# ====== تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")
with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    notes = st.text_area("📝 ملاحظات الشكوى")
    action = st.text_area("✅ الإجراء المتخذ")
    outbound_awb = st.text_input("🚚 Outbound AWB")
    inbound_awb = st.text_input("📦 Inbound AWB")
    submitted = st.form_submit_button("➕ إضافة شكوى")

    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints = complaints_sheet.get_all_records()
            responded = responded_sheet.get_all_records()
            archive = archive_sheet.get_all_records()
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            all_active_ids = [str(c["ID"]) for c in complaints] + [str(r["ID"]) for r in responded]
            all_archive_ids = [str(a["ID"]) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                # إرجاع الشكوى من الأرشيف
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes = row[2]
                        restored_action = row[3]
                        restored_type = row[1]
                        restored_outbound = row[6] if len(row) > 6 else ""
                        restored_inbound = row[7] if len(row) > 7 else ""
                        if safe_append(complaints_sheet, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound]):
                            time.sleep(0.5)
                            safe_delete(archive_sheet, idx)
                            st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                            st.rerun()
            else:
                if action.strip():
                    safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb])
                    st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb])
                    st.success("✅ تم تسجيل الشكوى في النشطة")
                st.rerun()

# ====== عرض الشكاوى النشطة والمردودة والأرشيف ======
def display_sheet(sheet, in_responded=False):
    data = sheet.get_all_values()
    if len(data) <= 1:
        st.info("لا توجد بيانات حالياً.")
        return
    for i, row in enumerate(data[1:], start=2):
        render_complaint(sheet, i, row, in_responded=in_responded)

st.header("📋 الشكاوى النشطة:")
display_sheet(complaints_sheet, in_responded=False)

st.header("✅ الإجراءات المردودة:")
display_sheet(responded_sheet, in_responded=True)

st.header("📦 الأرشيف:")
display_sheet(archive_sheet, in_responded=False)
