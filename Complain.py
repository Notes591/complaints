import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import xml.etree.ElementTree as ET
import re
from fpdf import FPDF

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

# ====== تحميل الأنواع مع scrollable selectbox ======
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

# ====== دالة طباعة PDF للشكوى ======
def print_complaint_pdf(row):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"فورم الشكوى رقم {comp_id}", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"نوع الشكوى: {comp_type}", ln=True)
    pdf.cell(0, 8, f"ملاحظات: {notes}", ln=True)
    pdf.cell(0, 8, f"الإجراء المتخذ: {action}", ln=True)
    pdf.cell(0, 8, f"تاريخ التسجيل: {date_added}", ln=True)
    pdf.cell(0, 8, f"مسترجعة: {restored}", ln=True)
    pdf.cell(0, 8, f"Outbound AWB: {outbound_awb}", ln=True)
    pdf.cell(0, 8, f"Inbound AWB: {inbound_awb}", ln=True)

    filename = f"complaint_{comp_id}.pdf"
    pdf.output(filename)
    st.success(f"✅ تم إنشاء PDF: {filename}")
    with open(filename, "rb") as f:
        st.download_button("⬇️ حمل PDF", f, file_name=filename)

# ====== دالة عرض الشكوى داخل form ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
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

            new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0, key=f"type_{comp_id}")
            new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{comp_id}")
            new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{comp_id}")
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb, key=f"out_{comp_id}")
            new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb, key=f"in_{comp_id}")

            col1, col2, col3, col4, col5 = st.columns(5)
            submitted_save = col1.form_submit_button("💾 حفظ")
            submitted_delete = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")
            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ نقل للإجراءات المردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع للنشطة")
            submitted_print = col5.form_submit_button("🖨️ طباعة PDF")

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

            if submitted_print:
                print_complaint_pdf([comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])

# ====== زر تحديث أرامكس ======
st.header("🚚 تحديث حالات أرامكس")
if st.button("🔄 تحديث جميع الشحنات المعلقة"):
    aramex_data = aramex_sheet.get_all_values()[1:]
    for i, row in enumerate(aramex_data, start=2):
        order_id = row[0]
        awb = order_id  # يمكن تعديل إذا AWB مختلف
        status = get_aramex_status(awb)
        safe_update(aramex_sheet, f"B{i}", [[status]])
    st.success("✅ تم تحديث جميع الحالات")

# ====== البحث عن الشكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")
if search_id.strip():
    found = False
    active_notes = complaints_sheet.get_all_values()
    for i, row in enumerate(active_notes[1:], start=2):
        if str(row[0]) == search_id:
            st.success(f"✅ الشكوى موجودة في النشطة")
            render_complaint(complaints_sheet, i, row, in_responded=False)
            found = True
    responded_notes = responded_sheet.get_all_values()
    for i, row in enumerate(responded_notes[1:], start=2):
        if str(row[0]) == search_id:
            st.success(f"✅ الشكوى موجودة في المردودة")
            render_complaint(responded_sheet, i, row, in_responded=True)
            found = True
    archive_notes = archive_sheet.get_all_values()
    for i, row in enumerate(archive_notes[1:], start=2):
        if str(row[0]) == search_id:
            st.success(f"✅ الشكوى موجودة في الأرشيف")
            render_complaint(archive_sheet, i, row, in_archive=True)
            found = True
    if not found:
        st.warning("❌ لم يتم العثور على الشكوى")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة")
active_notes = complaints_sheet.get_all_values()
for i, row in enumerate(active_notes[1:], start=2):
    render_complaint(complaints_sheet, i, row, in_responded=False)

# ====== عرض الشكاوى المردودة ======
st.header("📋 الإجراءات المردودة")
responded_notes = responded_sheet.get_all_values()
for i, row in enumerate(responded_notes[1:], start=2):
    render_complaint(responded_sheet, i, row, in_responded=True)

# ====== عرض الأرشيف مع تحميل المزيد ======
st.header("🗄️ الأرشيف")
archive_data = archive_sheet.get_all_values()[1:]
show_count = st.session_state.get("archive_show_count", 50)
for i, row in enumerate(archive_data[:show_count], start=2):
    render_complaint(archive_sheet, i, row, in_archive=True)
if show_count < len(archive_data):
    if st.button("عرض المزيد"):
        st.session_state["archive_show_count"] = show_count + 50
