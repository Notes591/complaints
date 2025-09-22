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

# ====== تحديث تلقائي كل 60 ثانية ======
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

# ====== تحميل البيانات في session_state ======
if "complaints_data" not in st.session_state:
    st.session_state["complaints_data"] = complaints_sheet.get_all_values()[1:]
if "responded_data" not in st.session_state:
    st.session_state["responded_data"] = responded_sheet.get_all_values()[1:]
if "archive_data" not in st.session_state:
    st.session_state["archive_data"] = archive_sheet.get_all_values()[1:]
if "aramex_data" not in st.session_state:
    st.session_state["aramex_data"] = aramex_sheet.get_all_values()[1:]

# ====== دالة عرض الشكوى ======
def render_complaint(sheet_name, i, row, in_responded=False, in_archive=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    st.write(f"### 🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}")
    st.write(f"📌 النوع الحالي: {comp_type}")
    st.write(f"📝 الملاحظات: {notes}")
    st.write(f"✅ الإجراء: {action}")

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

    new_type = st.selectbox(f"✏️ عدل نوع الشكوى {comp_id}", [comp_type] + [t for t in types_list if t != comp_type], index=0)
    new_notes = st.text_area(f"✏️ عدل الملاحظات {comp_id}", value=notes)
    new_action = st.text_area(f"✏️ عدل الإجراء {comp_id}", value=action)
    new_outbound = st.text_input(f"✏️ Outbound AWB {comp_id}", value=outbound_awb)
    new_inbound = st.text_input(f"✏️ Inbound AWB {comp_id}", value=inbound_awb)

    col1, col2, col3, col4 = st.columns(4)
    submitted_save = col1.button(f"💾 حفظ {comp_id}")
    submitted_delete = col2.button(f"🗑️ حذف {comp_id}")
    submitted_archive = col3.button(f"📦 أرشفة {comp_id}")
    submitted_move = col4.button(f"➡️ نقل للمردودة" if not in_responded else f"⬅️ رجوع للنشطة")

    if submitted_save:
        safe_update(sheet_name, f"B{i}", [[new_type]])
        safe_update(sheet_name, f"C{i}", [[new_notes]])
        safe_update(sheet_name, f"D{i}", [[new_action]])
        safe_update(sheet_name, f"G{i}", [[new_outbound]])
        safe_update(sheet_name, f"H{i}", [[new_inbound]])
        st.success(f"✅ تم التعديل {comp_id}")

    if submitted_delete:
        safe_delete(sheet_name, i)
        st.success(f"🗑️ تم حذف {comp_id}")

    if submitted_archive:
        safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
        safe_delete(sheet_name, i)
        st.success(f"♻️ تم أرشفة {comp_id}")

    if submitted_move:
        if not in_responded:
            safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
            safe_delete(sheet_name, i)
            st.success(f"✅ اتنقلت للإجراءات المردودة {comp_id}")
        else:
            safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
            safe_delete(sheet_name, i)
            st.success(f"✅ اتنقلت للنشطة {comp_id}")

# ====== باقي الكود النهائي يشمل تسجيل الشكوى الجديدة، البحث، عرض النشطة، المردودة، الأرشيف، معلق أرامكس وأرشيفه ======
# بسبب الطول، يمكنني إرسال باقي الأجزاء مباشرة الآن مع الحفاظ على جميع الميزات
# ====== البحث عن الشكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")
if search_id.strip():
    found = False
    for i, row in enumerate(st.session_state["complaints_data"], start=2):
        if str(row[0]) == search_id:
            st.success(f"✅ الشكوى موجودة في النشطة")
            render_complaint(complaints_sheet, i, row, in_responded=False)
            found = True
            break
    if not found:
        for i, row in enumerate(st.session_state["responded_data"], start=2):
            if str(row[0]) == search_id:
                st.success(f"✅ الشكوى موجودة في المردودة")
                render_complaint(responded_sheet, i, row, in_responded=True)
                found = True
                break
    if not found:
        for i, row in enumerate(st.session_state["archive_data"], start=2):
            if str(row[0]) == search_id:
                st.success(f"✅ الشكوى موجودة في الأرشيف")
                render_complaint(archive_sheet, i, row, in_archive=True)
                found = True
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
            all_active_ids = [str(c[0]) for c in st.session_state["complaints_data"]] + \
                             [str(r[0]) for r in st.session_state["responded_data"]]
            all_archive_ids = [str(a[0]) for a in st.session_state["archive_data"]]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                for idx, row in enumerate(st.session_state["archive_data"], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes = row[2]
                        restored_action = row[3]
                        restored_type = row[1]
                        restored_outbound = row[6] if len(row) > 6 else ""
                        restored_inbound = row[7] if len(row) > 7 else ""
                        if safe_append(complaints_sheet, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound]):
                            safe_delete(archive_sheet, idx)
                            st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                        break
            else:
                if action.strip():
                    safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb])
                    st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb])
                    st.success("✅ تم تسجيل الشكوى في النشطة")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
if st.session_state["complaints_data"]:
    for i, row in enumerate(st.session_state["complaints_data"], start=2):
        render_complaint(complaints_sheet, i, row, in_responded=False)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== عرض الإجراءات المردودة حسب النوع ======
st.header("✅ الإجراءات المردودة حسب النوع:")
responded_notes = st.session_state["responded_data"]
if responded_notes:
    types_in_responded = list({row[1] for row in responded_notes})
    for complaint_type in types_in_responded:
        st.write(f"## 📌 نوع الشكوى: {complaint_type}")
        type_rows = [(i, row) for i, row in enumerate(responded_notes, start=2) if row[1] == complaint_type]
        for i, row in type_rows:
            comp_id = row[0]
            outbound_awb = row[6] if len(row) > 6 else ""
            inbound_awb = row[7] if len(row) > 7 else ""
            delivered_msgs = []
            for awb, direction in [(outbound_awb, "Outbound"), (inbound_awb, "Inbound")]:
                if awb:
                    status = get_aramex_status(awb)
                    if "Delivered" in status:
                        match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", status)
                        delivered_date = match.group(0) if match else "—"
                        delivered_msgs.append(f"{direction} AWB: {awb} تم توصيلها بتاريخ {delivered_date}")
            rw_record = get_returnwarehouse_record(comp_id)
            rw_msg = None
            if rw_record:
                rw_msg = (
                    f"📦 بيانات ReturnWarehouse للشكوى {comp_id}:\n"
                    f"رقم الطلب: {rw_record['رقم الطلب']}\n"
                    f"الفاتورة: {rw_record['الفاتورة']}\n"
                    f"التاريخ: {rw_record['التاريخ']}\n"
                    f"الزبون: {rw_record['الزبون']}\n"
                    f"المبلغ: {rw_record['المبلغ']}\n"
                    f"رقم الشحنة: {rw_record['رقم الشحنة']}\n"
                    f"البيان: {rw_record['البيان']}"
                )
            if delivered_msgs and rw_msg:
                st.warning(f"🚨🚨🚨 الشكوى {comp_id} تم توصيلها ولديها بيانات ReturnWarehouse!")
                for msg in delivered_msgs:
                    st.write(f"- {msg}")
                st.info(rw_msg)
            elif delivered_msgs:
                st.warning(f"🚨🚨🚨 الشكوى {comp_id} تم توصيلها!")
                for msg in delivered_msgs:
                    st.write(f"- {msg}")
            elif rw_msg:
                st.info(rw_msg)
            render_complaint(responded_sheet, i, row, in_responded=True)
else:
    st.info("لا توجد شكاوى مردودة حالياً.")

# ====== عرض الأرشيف ======
st.header("📦 الأرشيف:")
archived = st.session_state["archive_data"]
if archived:
    for i, row in enumerate(archived, start=2):
        render_complaint(archive_sheet, i, row, in_archive=True)
else:
    st.info("لا يوجد شكاوى في الأرشيف.")

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
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

st.subheader("📋 قائمة الطلبات المعلقة")
aramex_data = st.session_state["aramex_data"]
if aramex_data:
    for i, row in enumerate(aramex_data, start=2):
        order_id, status, date_added, action = row[:4]
        st.write(f"### 📦 طلب {order_id}")
        st.write(f"📌 الحالة الحالية: {status}")
        st.write(f"✅ الإجراء الحالي: {action}")
        st.caption(f"📅 تاريخ الإضافة: {date_added}")
        col1, col2, col3 = st.columns(3)
        submitted_save = col1.button(f"💾 حفظ {order_id}")
        submitted_delete = col2.button(f"🗑️ حذف {order_id}")
        submitted_archive = col3.button(f"📦 أرشفة {order_id}")
        if submitted_save:
            safe_update(aramex_sheet, f"B{i}", [[status]])
            safe_update(aramex_sheet, f"D{i}", [[action]])
            st.success(f"✅ تم تعديل الطلب {order_id}")
        if submitted_delete:
            safe_delete(aramex_sheet, i)
            st.warning(f"🗑️ تم حذف الطلب {order_id}")
        if submitted_archive:
            safe_append(aramex_archive, [order_id, status, date_added, action])
            safe_delete(aramex_sheet, i)
            st.success(f"♻️ تم أرشفة الطلب {order_id}")
