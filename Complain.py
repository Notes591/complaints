import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
from streamlit_autorefresh import st_autorefresh

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

# ====== دالة لجلب حالة الشحنة من أرامكس ======
client_info = {
    "UserName": "fitnessworld525@gmail.com",
    "Password": "Aa12345678@",
    "Version": "v1",
    "AccountNumber": "71958996",
    "AccountPin": "657448",
    "AccountEntity": "RUH",
    "AccountCountryCode": "SA"
}

def get_aramex_status(awb_number):
    url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
    headers = {"Content-Type": "application/json"}
    payload = {
        "ClientInfo": client_info,
        "Transaction": {"Reference1": "12345"},
        "Shipments": [awb_number],
        "GetLastUpdateOnly": True
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        if "TrackingResults" in data and len(data["TrackingResults"]) > 0:
            result = data["TrackingResults"][0]
            if "Update" in result and len(result["Update"]) > 0:
                last_update = result["Update"][-1]
                status = last_update.get("Status", "غير محددة")
                date = last_update.get("Date", "")
                return f"{status} بتاريخ {date}"
        return "لا توجد حالة متاحة"
    except Exception as e:
        return f"خطأ في جلب الحالة: {e}"

# ====== التحديث التلقائي كل دقيقة ======
st_autorefresh(interval=60*1000, key="auto_refresh")  # 60 ثانية تحديث تلقائي

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

        # تعديل النوع والملاحظات والإجراء والأعمدة الجديدة
        new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0, key=f"type_{comp_id}_{sheet.title}")
        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{comp_id}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{comp_id}_{sheet.title}")
        new_outbound = st.text_input("✏️ Outbound AWB (شحنة مرسلة)", value=outbound_awb, key=f"outbound_{comp_id}_{sheet.title}")
        new_inbound = st.text_input("✏️ Inbound AWB (شحنة واردة)", value=inbound_awb, key=f"inbound_{comp_id}_{sheet.title}")

        # عرض حالة الشحنة تلقائياً لكل الحقليين
        if new_outbound:
            status_out = get_aramex_status(new_outbound)
            st.info(f"🚚 Outbound AWB (شحنة مرسلة): {new_outbound} | الحالة: {status_out}")
        if new_inbound:
            status_in = get_aramex_status(new_inbound)
            st.info(f"📦 Inbound AWB (شحنة واردة): {new_inbound} | الحالة: {status_in}")

        # أزرار الحفظ والحذف والأرشفة
        col1, col2, col3, col4 = st.columns(4)
        if col1.button("💾 حفظ", key=f"save_{comp_id}_{sheet.title}"):
            safe_update(sheet, f"B{i}", [[new_type]])
            safe_update(sheet, f"C{i}", [[new_notes]])
            safe_update(sheet, f"D{i}", [[new_action]])
            safe_update(sheet, f"G{i}", [[new_outbound]])
            safe_update(sheet, f"H{i}", [[new_inbound]])
            st.success("✅ تم التعديل")
            st.experimental_rerun()
        if col2.button("🗑️ حذف", key=f"delete_{comp_id}_{sheet.title}"):
            safe_delete(sheet, i)
            st.warning("🗑️ تم حذف الشكوى")
            st.experimental_rerun()
        if col3.button("📦 أرشفة", key=f"archive_{comp_id}_{sheet.title}"):
            safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
            time.sleep(0.5)
            safe_delete(sheet, i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.experimental_rerun()
        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{comp_id}_{sheet.title}"):
                safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للإجراءات المردودة")
                st.experimental_rerun()
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{comp_id}_{sheet.title}"):
                safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للنشطة")
                st.experimental_rerun()

# ====== عرض الشكاوى النشطة مع التحديث التلقائي ======
st.header("📋 الشكاوى النشطة:")
active_notes = complaints_sheet.get_all_values()
if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row, in_responded=False)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

st.header("✅ الإجراءات المردودة:")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    for i, row in enumerate(responded_notes[1:], start=2):
        render_complaint(responded_sheet, i, row, in_responded=True)
else:
    st.info("لا توجد شكاوى مردودة حالياً.")

st.header("📦 الأرشيف:")
archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, notes, action, date_added = row[:5]
        restored = row[5] if len(row) > 5 else ""
        outbound_awb = row[6] if len(row) > 6 else ""
        inbound_awb = row[7] if len(row) > 7 else ""
        with st.expander(f"📦 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
            if outbound_awb:
                st.info(f"🚚 Outbound AWB (شحنة مرسلة): {outbound_awb} | الحالة: {get_aramex_status(outbound_awb)}")
            if inbound_awb:
                st.info(f"📦 Inbound AWB (شحنة واردة): {inbound_awb} | الحالة: {get_aramex_status(inbound_awb)}")
else:
    st.info("لا يوجد أرشيف حالياً.")

# ====== معلق أرامكس ======
st.header("🚚 معلق ارامكس")
with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input("📌 الحالة")
    action = st.text_area("✅ الإجراء المتخذ")
    submitted = st.form_submit_button("➕ إضافة")
    if submitted:
        if order_id.strip() and status.strip() and action.strip():
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            safe_append(aramex_sheet, [order_id, status, date_now, action])
            st.success("✅ تم تسجيل الطلب")
            st.experimental_rerun()
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

# عرض الطلبات المعلقة
st.subheader("📋 قائمة الطلبات المعلقة")
aramex_data = aramex_sheet.get_all_values()
if len(aramex_data) > 1:
    for i, row in enumerate(aramex_data[1:], start=2):
        order_id, status, date_added, action = row[:4]
        with st.expander(f"📦 طلب {order_id}"):
            st.write(f"📌 الحالة الحالية: {status}")
            st.write(f"✅ الإجراء الحالي: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            new_status = st.text_input("✏️ عدل الحالة", value=status, key=f"status_{order_id}")
            new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{order_id}")
            col1, col2 = st.columns(2)
            if col1.button("💾 حفظ", key=f"save_{order_id}"):
                safe_update(aramex_sheet, f"B{i}", [[new_status]])
                safe_update(aramex_sheet, f"D{i}", [[new_action]])
                st.success("✅ تم الحفظ")
                st.experimental_rerun()
            if col2.button("📦 أرشفة", key=f"archive_{order_id}"):
                safe_append(aramex_archive, [order_id, new_status, date_added, new_action])
                time.sleep(0.5)
                safe_delete(aramex_sheet, i)
                st.success("✅ تم نقل الطلب للأرشيف")
                st.experimental_rerun()
else:
    st.info("لا توجد طلبات معلقة حالياً.")
