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

# ====== دالة render_complaint كاملة مع callbacks ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5]
    outbound_awb = row[6]
    inbound_awb = row[7]

    order_status = get_order_status(comp_id)
    key_prefix = f"{sheet.title}_{comp_id}"

    if key_prefix not in st.session_state:
        st.session_state[key_prefix] = {
            "type": comp_type,
            "notes": notes,
            "action": action,
            "outbound": outbound_awb,
            "inbound": inbound_awb
        }

    def save_callback(s=sheet, idx=i, key=key_prefix):
        vals = st.session_state[key]
        safe_update(s, f"B{idx}", [[vals["type"]]])
        safe_update(s, f"C{idx}", [[vals["notes"]]])
        safe_update(s, f"D{idx}", [[vals["action"]]])
        safe_update(s, f"G{idx}", [[vals["outbound"]]])
        safe_update(s, f"H{idx}", [[vals["inbound"]]])
        st.success("✅ تم التعديل")

    def delete_callback(s=sheet, idx=i):
        safe_delete(s, idx)
        st.warning("🗑️ تم حذف الشكوى")

    def archive_callback(s=sheet, idx=i, key=key_prefix):
        vals = st.session_state[key]
        safe_append(archive_sheet, [comp_id, vals["type"], vals["notes"], vals["action"], date_added, restored, vals["outbound"], vals["inbound"]])
        safe_delete(s, idx)
        st.success("♻️ الشكوى انتقلت للأرشيف")

    def move_callback(s=sheet, idx=i, key=key_prefix):
        vals = st.session_state[key]
        if not in_responded:
            safe_append(responded_sheet, [comp_id, vals["type"], vals["notes"], vals["action"], date_added, restored, vals["outbound"], vals["inbound"]])
            safe_delete(s, idx)
            st.success("✅ انتقلت للإجراءات المردودة")
        else:
            safe_append(complaints_sheet, [comp_id, vals["type"], vals["notes"], vals["action"], date_added, restored, vals["outbound"], vals["inbound"]])
            safe_delete(s, idx)
            st.success("✅ انتقلت للنشطة")

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        st.selectbox("✏️ عدل نوع الشكوى", [st.session_state[key_prefix]["type"]] + [t for t in types_list if t != st.session_state[key_prefix]["type"]],
                     index=0, key=f"{key_prefix}_type", on_change=lambda k=key_prefix: st.session_state[key]["type"] = st.session_state[f"{k}_type"])
        st.text_area("✏️ عدل الملاحظات", value=st.session_state[key_prefix]["notes"], key=f"{key_prefix}_notes", on_change=lambda k=key_prefix: st.session_state[key]["notes"] = st.session_state[f"{k}_notes"])
        st.text_area("✏️ عدل الإجراء", value=st.session_state[key_prefix]["action"], key=f"{key_prefix}_action", on_change=lambda k=key_prefix: st.session_state[key]["action"] = st.session_state[f"{k}_action"])
        st.text_input("✏️ Outbound AWB", value=st.session_state[key_prefix]["outbound"], key=f"{key_prefix}_outbound", on_change=lambda k=key_prefix: st.session_state[key]["outbound"] = st.session_state[f"{k}_outbound"])
        st.text_input("✏️ Inbound AWB", value=st.session_state[key_prefix]["inbound"], key=f"{key_prefix}_inbound", on_change=lambda k=key_prefix: st.session_state[key]["inbound"] = st.session_state[f"{k}_inbound"])

        if st.session_state[key_prefix]["outbound"]:
            st.info(f"🚚 Outbound AWB: {st.session_state[key_prefix]['outbound']} | الحالة: {get_aramex_status(st.session_state[key_prefix]['outbound'])}")
        if st.session_state[key_prefix]["inbound"]:
            st.info(f"📦 Inbound AWB: {st.session_state[key_prefix]['inbound']} | الحالة: {get_aramex_status(st.session_state[key_prefix]['inbound'])}")

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

        col1, col2, col3, col4 = st.columns(4)
        col1.button("💾 حفظ", key=f"{key_prefix}_save", on_click=save_callback)
        col2.button("🗑️ حذف", key=f"{key_prefix}_delete", on_click=delete_callback)
        col3.button("📦 أرشفة", key=f"{key_prefix}_archive", on_click=archive_callback)
        if not in_responded:
            col4.button("➡️ نقل للإجراءات المردودة", key=f"{key_prefix}_move", on_click=move_callback)
        else:
            col4.button("⬅️ رجوع للنشطة", key=f"{key_prefix}_move", on_click=move_callback)

# ====== البحث عن شكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")
if search_id.strip():
    found = False
    for sheet, in_responded, in_archive in [(complaints_sheet, False, False), (responded_sheet, True, False), (archive_sheet, False, True)]:
        data = sheet.get_all_values()
        for i, row in enumerate(data[1:], start=2):
            if str(row[0]) == search_id:
                st.success(f"✅ الشكوى موجودة في {'المردودة' if in_responded else 'الأرشيف' if in_archive else 'النشطة'}")
                render_complaint(sheet, i, row, in_responded=in_responded, in_archive=in_archive)
                found = True
                break
        if found: break
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
            complaints = complaints_sheet.get_all_records()
            responded = responded_sheet.get_all_records()
            archive = archive_sheet.get_all_records()
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_active_ids = [str(c["ID"]) for c in complaints] + [str(r["ID"]) for r in responded]
            all_archive_ids = [str(a["ID"]) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
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
active_notes = complaints_sheet.get_all_values()
if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== عرض الإجراءات المردودة حسب النوع ======
st.header("✅ الإجراءات المردودة حسب النوع:")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    types_in_responded = list({row[1] for row in responded_notes[1:]})
    for complaint_type in types_in_responded:
        with st.expander(f"📌 نوع الشكوى: {complaint_type}"):
            type_rows = [(i, row) for i, row in enumerate(responded_notes[1:], start=2) if row[1] == complaint_type]

            followup_1 = []
            followup_2 = []
            others = []

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
                elif delivered and not rw_record:
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

# ====== عرض الأرشيف ======
st.header("📦 الأرشيف:")
archived = archive_sheet.get_all_values()
if len(archived) > 1:
    if "archive_show_count" not in st.session_state:
        st.session_state["archive_show_count"] = 50
    show_count = st.session_state["archive_show_count"]
    for i, row in enumerate(archived[1:show_count], start=2):
        render_complaint(archive_sheet, i, row, in_archive=True)
    if len(archived) - 1 > show_count:
        if st.button("عرض المزيد من الأرشيف"):
            st.session_state["archive_show_count"] += 50
            st.experimental_rerun()
else:
    st.info("لا توجد شكاوى مؤرشفة حالياً.")

# ====== عرض معلق أرامكس ======
st.header("📦 معلق أرامكس:")
aramex_pending = aramex_sheet.get_all_values()
if len(aramex_pending) > 1:
    for i, row in enumerate(aramex_pending[1:], start=2):
        render_complaint(aramex_sheet, i, row)
else:
    st.info("لا توجد شكاوى أرامكس معلقة.")

# ====== عرض أرشيف أرامكس ======
st.header("📦 أرشيف أرامكس:")
aramex_archived = aramex_archive.get_all_values()
if len(aramex_archived) > 1:
    for i, row in enumerate(aramex_archived[1:], start=2):
        render_complaint(aramex_archive, i, row, in_archive=True)
else:
    st.info("لا توجد شكاوى أرامكس مؤرشفة.")
