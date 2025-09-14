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

# ====== تحديث تلقائي كل 6 دقائق ======
st_autorefresh(interval=360*1000, key="auto_refresh")

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

# ====== دالة عرض الشكوى مع Form لتجنب التحديث التلقائي ======
def render_complaint(sheet, i, row, in_responded=False):
    if 'rerun_flag' not in st.session_state:
        st.session_state.rerun_flag = False

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    keys = {
        "type": f"type_{comp_id}_{sheet.title}",
        "notes": f"notes_{comp_id}_{sheet.title}",
        "action": f"action_{comp_id}_{sheet.title}",
        "outbound": f"outbound_{comp_id}_{sheet.title}",
        "inbound": f"inbound_{comp_id}_{sheet.title}"
    }

    # تهيئة session_state
    for k, key in keys.items():
        if key not in st.session_state:
            if k == "type": st.session_state[key] = comp_type
            elif k == "notes": st.session_state[key] = notes
            elif k == "action": st.session_state[key] = action
            elif k == "outbound": st.session_state[key] = outbound_awb
            elif k == "inbound": st.session_state[key] = inbound_awb

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
        with st.form(key=f"form_{comp_id}_{sheet.title}", clear_on_submit=False):
            st.selectbox("✏️ عدل نوع الشكوى", [st.session_state[keys["type"]]] + [t for t in types_list if t != st.session_state[keys["type"]]], index=0, key=keys["type"])
            st.text_area("✏️ عدل الملاحظات", value=st.session_state[keys["notes"]], key=keys["notes"])
            st.text_area("✏️ عدل الإجراء", value=st.session_state[keys["action"]], key=keys["action"])
            st.text_input("✏️ Outbound AWB", value=st.session_state[keys["outbound"]], key=keys["outbound"])
            st.text_input("✏️ Inbound AWB", value=st.session_state[keys["inbound"]], key=keys["inbound"])

            col1, col2, col3, col4, col5, col6 = st.columns(6)

            # أزرار التحقق من AWB
            if st.session_state[keys["outbound"]]:
                if col5.form_submit_button("🚚 تحقق Outbound"):
                    status_out = get_aramex_status(st.session_state[keys["outbound"]])
                    st.info(f"🚚 Outbound AWB: {st.session_state[keys['outbound']]} | الحالة: {status_out}")

            if st.session_state[keys["inbound"]]:
                if col6.form_submit_button("📦 تحقق Inbound"):
                    status_in = get_aramex_status(st.session_state[keys["inbound"]])
                    st.info(f"📦 Inbound AWB: {st.session_state[keys['inbound']]} | الحالة: {status_in}")

            # ====== أزرار الحفظ والحذف والأرشفة والنقل ======
            if col1.form_submit_button("💾 حفظ"):
                safe_update(sheet, f"B{i}", [[st.session_state[keys["type"]]]])
                safe_update(sheet, f"C{i}", [[st.session_state[keys["notes"]]]])
                safe_update(sheet, f"D{i}", [[st.session_state[keys["action"]]]])
                safe_update(sheet, f"G{i}", [[st.session_state[keys["outbound"]]]])
                safe_update(sheet, f"H{i}", [[st.session_state[keys["inbound"]]]])
                st.success("✅ تم التعديل")
                st.session_state.rerun_flag = True

            if col2.form_submit_button("🗑️ حذف"):
                safe_delete(sheet, i)
                st.warning("🗑️ تم حذف الشكوى")
                st.session_state.rerun_flag = True

            if col3.form_submit_button("📦 أرشفة"):
                safe_append(archive_sheet, [comp_id, st.session_state[keys["type"]], st.session_state[keys["notes"]], st.session_state[keys["action"]], date_added, restored, st.session_state[keys["outbound"]], st.session_state[keys["inbound"]]])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("♻️ الشكوى انتقلت للأرشيف")
                st.session_state.rerun_flag = True

            if not in_responded:
                if col4.form_submit_button("➡️ نقل للإجراءات المردودة"):
                    safe_append(responded_sheet, [comp_id, st.session_state[keys["type"]], st.session_state[keys["notes"]], st.session_state[keys["action"]], date_added, restored, st.session_state[keys["outbound"]], st.session_state[keys["inbound"]]])
                    time.sleep(0.5)
                    safe_delete(sheet, i)
                    st.success("✅ اتنقلت للإجراءات المردودة")
                    st.session_state.rerun_flag = True
            else:
                if col4.form_submit_button("⬅️ رجوع للنشطة"):
                    safe_append(complaints_sheet, [comp_id, st.session_state[keys["type"]], st.session_state[keys["notes"]], st.session_state[keys["action"]], date_added, restored, st.session_state[keys["outbound"]], st.session_state[keys["inbound"]]])
                    time.sleep(0.5)
                    safe_delete(sheet, i)
                    st.success("✅ اتنقلت للنشطة")
                    st.session_state.rerun_flag = True

# ====== البحث عن شكوى ======
st.header("🔍 البحث عن شكوى")
with st.form("search_form"):
    search_id = st.text_input("🆔 اكتب رقم الشكوى")
    submitted_search = st.form_submit_button("🔍 بحث")
    if submitted_search:
        if search_id.strip():
            found = False
            for sheet in [complaints_sheet, responded_sheet, archive_sheet]:
                data = sheet.get_all_values()
                for i, row in enumerate(data[1:], start=2):
                    if row[0] == search_id:
                        found = True
                        render_complaint(sheet, i, row, in_responded=(sheet == responded_sheet))
                        break
            if not found:
                st.error("❌ لم يتم العثور على الشكوى")

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
                            st.session_state.rerun_flag = True
            else:
                if action.strip():
                    safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb])
                    st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb])
                    st.success("✅ تم تسجيل الشكوى في النشطة")
                st.session_state.rerun_flag = True

# ====== عرض الشكاوى النشطة ======
st.header("📌 الشكاوى النشطة")
complaints_data = complaints_sheet.get_all_values()[1:]
for i, row in enumerate(complaints_data, start=2):
    render_complaint(complaints_sheet, i, row)

# ====== عرض الإجراءات المردودة ======
st.header("📝 الإجراءات المردودة")
responded_data = responded_sheet.get_all_values()[1:]
for i, row in enumerate(responded_data, start=2):
    render_complaint(responded_sheet, i, row, in_responded=True)

# ====== عرض الأرشيف ======
st.header("🗄️ الأرشيف")
archive_data = archive_sheet.get_all_values()[1:]
for i, row in enumerate(archive_data, start=2):
    render_complaint(archive_sheet, i, row)

# ====== إعادة التشغيل إذا تم تعديل أي شيء ======
if 'rerun_flag' in st.session_state and st.session_state.rerun_flag:
    st.session_state.rerun_flag = False
    st.experimental_rerun()
