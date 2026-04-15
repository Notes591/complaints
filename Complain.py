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
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number",
    "Notifications"
]

sheets_dict = {}
for title in sheet_titles:
    try:
        sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
    except Exception:
        ss = client.open(SHEET_NAME)
        sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")

complaints_sheet     = sheets_dict["Complaints"]
responded_sheet      = sheets_dict["Responded"]
archive_sheet        = sheets_dict["Archive"]
types_sheet          = sheets_dict["Types"]
aramex_sheet         = sheets_dict["معلق ارامكس"]
aramex_archive       = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet   = sheets_dict["Order Number"]
notifications_sheet  = sheets_dict["Notifications"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
# ==============================================================
# 🔔 نظام الإشعارات المتطور
# ==============================================================

NOTIFICATION_CSS = """
<style>
.notif-card-new {
    background: linear-gradient(135deg, #1e3a5f, #0f2745);
    border-right: 4px solid #3498db;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    direction: rtl;
}
.notif-card-read {
    background: #1e1e2e;
    border-right: 4px solid #444;
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 6px;
    direction: rtl;
    opacity: 0.70;
}
.notif-card-aramex {
    background: linear-gradient(135deg, #1a3a2a, #0d2b1a);
    border-right: 4px solid #2ecc71;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    direction: rtl;
}
.notif-msg { color:#ecf0f1; font-size:14px; }
.notif-time { color:#7f8c8d; font-size:11px; }
</style>
"""
def add_notification(order_id, section, message, comp_type="", aramex_before="", aramex_after=""):
    try:
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notifications_sheet.append_row([
            str(order_id),
            str(comp_type),
            str(section),
            str(message),
            date_now,
            "NEW",
            str(aramex_before),
            str(aramex_after)
        ])
    except Exception:
        pass
    def _snapshot_key(awb):
    return f"aramex_snap_{awb}"

def save_aramex_snapshot(awb, status):
    st.session_state[_snapshot_key(awb)] = status

def get_aramex_snapshot(awb):
    return st.session_state.get(_snapshot_key(awb), None)

def check_and_notify_aramex_change(order_id, comp_type, awb, current_status):
    if not awb or not current_status:
        return

    prev = get_aramex_snapshot(awb)

    if prev is None:
        save_aramex_snapshot(awb, current_status)
        return

    if prev != current_status:
        add_notification(
            order_id,
            "أرامكس",
            f"تغيرت حالة الشحنة {awb}",
            comp_type=comp_type,
            aramex_before=prev,
            aramex_after=current_status
        )
        save_aramex_snapshot(awb, current_status)
        def check_stuck_shipment(order_id, comp_type, awb, current_status):
    key = f"stuck_{awb}"
    data = st.session_state.get(key, {"status": "", "time": time.time()})

    if data["status"] == current_status:
        if time.time() - data["time"] > 21600:
            add_notification(
                order_id,
                "أرامكس",
                f"الشحنة {awb} متوقفة",
                comp_type=comp_type
            )
            st.session_state[key]["time"] = time.time()
    else:
        st.session_state[key] = {
            "status": current_status,
            "time": time.time()
        }def _warehouse_key(order_id):
    return f"warehouse_snap_{order_id}"

def save_warehouse_snapshot(order_id):
    st.session_state[_warehouse_key(order_id)] = True

def warehouse_seen(order_id):
    return st.session_state.get(_warehouse_key(order_id), False)
@st.cache_data(ttl=10)
def get_notifications():
    try:
        data = notifications_sheet.get_all_values()
        return data[1:] if len(data) > 1 else []
    except Exception:
        return []
    def render_notifications_panel():
    st.markdown(NOTIFICATION_CSS, unsafe_allow_html=True)

    notifications = get_notifications()
    unread = [n for n in notifications if len(n) > 5 and n[5] == "NEW"]

    st.markdown(f"🔔 الإشعارات ({len(unread)})")

    with st.expander("عرض الإشعارات"):
        for n in reversed(notifications[-50:]):
            st.write(n)
            def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل append_row")
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
    st.error("❌ فشل update")
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
    st.error("❌ فشل delete")
    return False

        try:
    types_list = [row[0] for row in types_sheet.get_all_values()[1:]]
except Exception:
    types_list = []

try:
    return_warehouse_data = return_warehouse_sheet.get_all_values()[1:]
except Exception:
    return_warehouse_data = []
    def get_returnwarehouse_record(order_id):
    for row in return_warehouse_data:
        if len(row) > 0 and str(row[0]) == str(order_id):
            return {
                "رقم الطلب": row[0],
                "الفاتورة":  row[1] if len(row) > 1 else "",
                "التاريخ":   row[2] if len(row) > 2 else "",
                "الزبون":    row[3] if len(row) > 3 else "",
                "المبلغ":    row[4] if len(row) > 4 else "",
                "رقم الشحنة":row[5] if len(row) > 5 else "",
                "البيان":    row[6] if len(row) > 6 else ""
            }
    return None
try:
    order_number_data = order_number_sheet.get_all_values()[1:]
except Exception:
    order_number_data = []

def get_order_status(order_id):
    for row in order_number_data:
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس"
            elif delegate.strip():
                return f"🚚 مع مندوب ({delegate})"
            else:
                return "⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"
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
    xml_str = re.sub(r'xmlns(:\w+)?=\"[^\"]+\"', '', xml_str)
    xml_str = re.sub(r'(<\/?)(\w+:)', r'\1', xml_str)
    return xml_str
def extract_reference(tracking_result):
    for ref_tag in ['Reference1','Reference2','Reference3','Reference4','Reference5']:
        ref_elem = tracking_result.find(ref_tag)
        if ref_elem is not None and ref_elem.text:
            return ref_elem.text.strip()
    return ""
def get_aramex_status(awb_number):
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "ClientInfo": client_info,
            "Shipments": [awb_number]
        }

        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code != 200:
            return f"❌ فشل الاتصال {response.status_code}"

        xml_content = remove_xml_namespaces(response.text)
        root = ET.fromstring(xml_content)

        tracking_results = root.find('TrackingResults')
        if tracking_results is None:
            return "❌ لا توجد بيانات"

        keyvalue = tracking_results.find('KeyValueOfstringArrayOfTrackingResultmFAkxlpY')
        if keyvalue is not None:
            tracking_array = keyvalue.find('Value')
            if tracking_array is not None:
                tracks = tracking_array.findall('TrackingResult')
                if tracks:
                    last = tracks[-1]
                    desc = last.find('UpdateDescription').text if last.find('UpdateDescription') is not None else ""
                    return desc

        return "❌ لا توجد حالة"

    except Exception as e:
        return f"خطأ: {e}"
    @st.cache_data(ttl=300)
def cached_aramex_status(awb):
    if not awb:
        return ""
    return get_aramex_status(awb)
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored     = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb  = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):

        with st.form(key=f"form_{comp_id}_{sheet.title}"):

            st.write(f"📌 النوع: {comp_type}")
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 {date_added}")

            # ===============================
            # 🏬 المخزن + إشعار أول مرة
            # ===============================
            rw_record = get_returnwarehouse_record(comp_id)

            if rw_record:
                st.info(
                    f"📦 ReturnWarehouse:\n"
                    f"رقم الطلب: {rw_record['رقم الطلب']}\n"
                    f"الزبون: {rw_record['الزبون']}\n"
                    f"المبلغ: {rw_record['المبلغ']}\n"
                    f"رقم الشحنة: {rw_record['رقم الشحنة']}"
                )

                if not warehouse_seen(comp_id):
                    add_notification(
                        comp_id,
                        "المخزن",
                        "تم دخول الطلب إلى المخزن",
                        comp_type=comp_type
                    )
                    save_warehouse_snapshot(comp_id)

            # ===============================
            # ✏️ تعديل البيانات
            # ===============================
            new_type     = st.selectbox("تعديل النوع", [comp_type] + [t for t in types_list if t != comp_type])
            new_notes    = st.text_area("تعديل الملاحظات", value=notes)
            new_action   = st.text_area("تعديل الإجراء", value=action)
            new_outbound = st.text_input("Outbound AWB", value=outbound_awb)
            new_inbound  = st.text_input("Inbound AWB", value=inbound_awb)

            # ===============================
            # 🚚 أرامكس + إشعارات ذكية
            # ===============================

            # ----- Outbound -----
            if new_outbound:
                status_out = cached_aramex_status(new_outbound)
                st.info(f"🚚 {new_outbound} | {status_out}")

                prev = get_aramex_snapshot(new_outbound)

                # تغيير الحالة
                check_and_notify_aramex_change(comp_id, comp_type, new_outbound, status_out)

                # تسليم بدون تكرار
                if "Delivered" in status_out and prev != "Delivered":
                    add_notification(
                        comp_id,
                        "الشحن",
                        f"تم تسليم الشحنة {new_outbound}",
                        comp_type=comp_type
                    )

                # شحنة متوقفة
                check_stuck_shipment(comp_id, comp_type, new_outbound, status_out)

            # ----- Inbound -----
            if new_inbound:
                status_in = cached_aramex_status(new_inbound)
                st.info(f"📦 {new_inbound} | {status_in}")

                prev = get_aramex_snapshot(new_inbound)

                check_and_notify_aramex_change(comp_id, comp_type, new_inbound, status_in)

                if "Delivered" in status_in and prev != "Delivered":
                    add_notification(
                        comp_id,
                        "الشحن",
                        f"تم تسليم الشحنة {new_inbound}",
                        comp_type=comp_type
                    )

                check_stuck_shipment(comp_id, comp_type, new_inbound, status_in)

            # ===============================
            # 🎛️ الأزرار
            # ===============================
            col1, col2, col3, col4 = st.columns(4)

            submitted_save    = col1.form_submit_button("💾 حفظ")
            submitted_delete  = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")

            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ مردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع")

            # ===============================
            # 💾 حفظ
            # ===============================
            if submitted_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])

                # إشعار تغيير النوع
                if comp_type != new_type:
                    add_notification(
                        comp_id,
                        "تعديل",
                        f"تم تغيير النوع من {comp_type} إلى {new_type}",
                        comp_type=new_type
                    )

                add_notification(comp_id, "تعديل", "تم تعديل الشكوى", comp_type=new_type)
                st.success("تم التعديل")

            # ===============================
            # 🗑️ حذف
            # ===============================
            if submitted_delete:
                if safe_delete(sheet, i):
                    add_notification(comp_id, "حذف", "تم حذف الشكوى")
                    st.warning("تم الحذف")

            # ===============================
            # 📦 أرشفة
            # ===============================
            if submitted_archive:
                if safe_append(archive_sheet, row):
                    if safe_delete(sheet, i):
                        add_notification(comp_id, "أرشيف", "تم أرشفة الشكوى")
                        st.success("تم الأرشفة")

            # ===============================
            # 🔁 نقل
            # ===============================
            if submitted_move:
                if not in_responded:
                    if safe_append(responded_sheet, row):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, "مردودة", "تم نقل الشكوى")
                            st.success("تم النقل")
                else:
                    if safe_append(complaints_sheet, row):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, "نشطة", "تم إرجاع الشكوى")
                            st.success("تم الإرجاع")
                            st.title("⚠️ نظام إدارة الشكاوى")

# عرض الإشعارات
render_notifications_panel()

st.markdown("---")
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("رقم الشكوى")

if search_id.strip():
    found = False

    for sheet_obj, in_responded, in_archive in [
        (complaints_sheet, False, False),
        (responded_sheet, True, False),
        (archive_sheet, False, True)
    ]:
        data = sheet_obj.get_all_values()

        for i, row in enumerate(data[1:], start=2):
            if str(row[0]) == search_id:

                location = "النشطة" if not in_responded else "المردودة"
                if in_archive:
                    location = "الأرشيف"

                st.success(f"موجودة في {location}")

                add_notification(
                    search_id,
                    "بحث",
                    f"تم فتح الشكوى من {location}"
                )

                render_complaint(sheet_obj, i, row, in_responded, in_archive)

                found = True
                break

        if found:
            break

    if not found:
        st.error("❌ غير موجودة")
        st.header("➕ إضافة شكوى")

with st.form("add_form", clear_on_submit=True):

    comp_id   = st.text_input("رقم الشكوى")
    comp_type = st.selectbox("النوع", ["اختر..."] + types_list)
    notes     = st.text_area("ملاحظات")
    action    = st.text_area("الإجراء")
    outbound  = st.text_input("Outbound AWB")
    inbound   = st.text_input("Inbound AWB")

    submit = st.form_submit_button("إضافة")

    if submit:

        if not comp_id.strip() or comp_type == "اختر...":
            st.error("❌ لازم تدخل البيانات")
        else:
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if action.strip():
                safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound, inbound])
                st.success("تمت الإضافة في المردودة")

                add_notification(comp_id, "إضافة", "تمت إضافة الشكوى في المردودة", comp_type)

            else:
                safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound, inbound])
                st.success("تمت الإضافة في النشطة")

                add_notification(comp_id, "إضافة", "تمت إضافة الشكوى", comp_type)
                st.header("📋 الشكاوى النشطة")

data = complaints_sheet.get_all_values()

if len(data) > 1:
    for i, row in enumerate(data[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا يوجد بيانات")
    st.header("✅ المردودة")

data = responded_sheet.get_all_values()

if len(data) > 1:
    for i, row in enumerate(data[1:], start=2):
        render_complaint(responded_sheet, i, row, in_responded=True)
else:
    st.info("لا يوجد بيانات")
    st.header("🚚 معلق أرامكس")

with st.form("aramex_form", clear_on_submit=True):
    order_id = st.text_input("رقم الطلب")
    status   = st.text_input("الحالة")
    action   = st.text_area("الإجراء")

    submit = st.form_submit_button("إضافة")

    if submit:
        if order_id and status and action:
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            safe_append(aramex_sheet, [order_id, status, date_now, action])

            add_notification(order_id, "أرامكس", "تم إضافة طلب جديد")

            st.success("تمت الإضافة")
        else:
            st.error("❌ أدخل كل البيانات")
            data = aramex_sheet.get_all_values()

if len(data) > 1:
    for i, row in enumerate(data[1:], start=2):

        order_id = row[0]
        status   = row[1]
        date     = row[2]
        action   = row[3]

        with st.expander(f"طلب {order_id}"):

            st.write(status)
            st.write(action)

            current = cached_aramex_status(order_id)

            if current:
                check_and_notify_aramex_change(order_id, "أرامكس", order_id, current)
                check_stuck_shipment(order_id, "أرامكس", order_id, current)

                st.info(current)
                st.caption("النظام متصل بجوجل شيت + إشعارات ذكية 🔔")
