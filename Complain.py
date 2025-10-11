import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import re
from streamlit_autorefresh import st_autorefresh

# ====== تحديث تلقائي كل 6 دقائق ======
st_autorefresh(interval=360*1000, key="auto_refresh")

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
aramex_pending = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ====== إعداد الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== تحميل أنواع الشكاوى ======
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== دوال القراءة من ReturnWarehouse ======
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

# ====== قراءة حالة الطلب ======
order_number_data = order_number_sheet.get_all_values()[1:]
def get_order_status(order_id):
    for row in order_number_data:
        if str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f"🚚 الطلب الاساسي مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "⏳ الطلب الاساسي تحت المتابعة"
    return "⏳ تحت المتابعة"

# ====== دوال أمان (لعمليات القراءة والكتابة) ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for _ in range(retries):
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
        response = requests.post(url, json=payload, headers=headers, timeout=6)
        if response.status_code != 200:
            return f"❌ خطأ في الاتصال ({response.status_code})"
        data = response.json()
        results = data.get("TrackingResults", [])
        if not results or not results[0].get("Value"):
            return "❌ لا توجد بيانات تتبع"
        updates = results[0]["Value"]
        desc = updates[-1].get("UpdateDescription", "—")
        return desc
    except Exception as e:
        return f"⚠️ خطأ: {e}"

# ====== عرض الشكوى ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} | {order_status}"):
        with st.form(key=f"form_{comp_id}_{sheet.title}"):
            st.write(f"📋 النوع: {comp_type}")
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ الإدخال: {date_added}")

            rw_record = get_returnwarehouse_record(comp_id)
            if rw_record:
                st.info(
                    f"📦 سجل ReturnWarehouse:\n"
                    f"رقم الطلب: {rw_record['رقم الطلب']}\n"
                    f"الفاتورة: {rw_record['الفاتورة']}\n"
                    f"التاريخ: {rw_record['التاريخ']}\n"
                    f"الزبون: {rw_record['الزبون']}\n"
                    f"المبلغ: {rw_record['المبلغ']}\n"
                    f"رقم الشحنة: {rw_record['رقم الشحنة']}\n"
                    f"البيان: {rw_record['البيان']}"
                )

            new_type = st.selectbox("✏️ عدل النوع", [comp_type] + [t for t in types_list if t != comp_type])
            new_notes = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("📦 Outbound AWB", value=outbound_awb)
            new_inbound = st.text_input("📦 Inbound AWB", value=inbound_awb)

            if new_outbound:
                st.info(f"🚚 Outbound حالة: {get_aramex_status(new_outbound)}")
            if new_inbound:
                st.info(f"📦 Inbound حالة: {get_aramex_status(new_inbound)}")

            col1, col2, col3, col4 = st.columns(4)
            save = col1.form_submit_button("💾 حفظ")
            delete = col2.form_submit_button("🗑️ حذف")
            archive = col3.form_submit_button("📦 أرشفة")
            move = col4.form_submit_button("➡️ نقل" if not in_responded else "⬅️ رجوع")

            if save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                st.success("✅ تم الحفظ.")

            if delete:
                safe_delete(sheet, i)
                st.warning("🗑️ تم الحذف.")

            if archive:
                safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                safe_delete(sheet, i)
                st.success("📦 تم الأرشفة.")

            if move:
                if not in_responded:
                    safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                    safe_delete(sheet, i)
                    st.success("➡️ تم النقل للمردودة.")
                else:
                    safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                    safe_delete(sheet, i)
                    st.success("⬅️ تمت الإعادة للنشطة.")

# ====== عرض الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة:")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    types_in_responded = list({row[1] for row in responded_notes[1:]})
    for complaint_type in types_in_responded:
        with st.expander(f"📌 نوع الشكوى: {complaint_type}"):
            type_rows = [(i, row) for i, row in enumerate(responded_notes[1:], start=2) if row[1] == complaint_type]

            followup_1, followup_2, others = [], [], []

            for i, row in type_rows:
                comp_id = row[0]
                outbound_awb = row[6] if len(row) > 6 else ""
                inbound_awb = row[7] if len(row) > 7 else ""
                rw_record = get_returnwarehouse_record(comp_id)

                delivered = False
                for awb in [outbound_awb, inbound_awb]:
                    if awb and "Delivered" in get_aramex_status(awb):
                        delivered = True
                        break

                if delivered and rw_record:
                    followup_2.append((i, row))
                elif delivered:
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

# ====== قسم الأرشيف ======
st.header("📦 الأرشيف:")
archive_data = archive_sheet.get_all_values()
if len(archive_data) > 1:
    limit = st.session_state.get("archive_limit", 50)
    for i, row in enumerate(archive_data[1:limit+1], start=2):
        render_complaint(archive_sheet, i, row, in_archive=True)
    if len(archive_data) - 1 > limit:
        if st.button("عرض المزيد..."):
            st.session_state["archive_limit"] = limit + 50
else:
    st.info("لا توجد شكاوى في الأرشيف.")

# ====== قسم أرامكس ======
st.header("📦 شكاوى أرامكس:")
aramex_pending_data = aramex_pending.get_all_values()
if len(aramex_pending_data) > 1:
    for i, row in enumerate(aramex_pending_data[1:], start=2):
        render_complaint(aramex_pending, i, row)
else:
    st.info("لا توجد شكاوى معلقة في أرامكس.")

aramex_archive_data = aramex_archive.get_all_values()
if len(aramex_archive_data) > 1:
    with st.expander("📚 أرشيف أرامكس"):
        for i, row in enumerate(aramex_archive_data[1:], start=2):
            render_complaint(aramex_archive, i, row, in_archive=True)
else:
    st.info("لا توجد شكاوى في أرشيف أرامكس.")
