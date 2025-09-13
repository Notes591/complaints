# app.py
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone, timedelta, time as dtime
import time
import gspread.exceptions
import requests
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io
import json

# ====== تحديث تلقائي كل 60 ثانية ======
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=360*1000, key="auto_refresh")  # 360000 ms = 6 minutes; تعديل إن أحببت

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

# ====== دالة عرض الشكوى مع إدارة إعادة التشغيل ======
def render_complaint(sheet, i, row, in_responded=False):
    if 'rerun_flag' not in st.session_state:
        st.session_state.rerun_flag = False

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
        st.write(f"📌 النوع الحالي: {comp_type}")
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        st.caption(f"📅 تاريخ التسجيل: {date_added}")

        new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0, key=f"type_{comp_id}_{sheet.title}")
        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{comp_id}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{comp_id}_{sheet.title}")
        new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb, key=f"outbound_{comp_id}_{sheet.title}")
        new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb, key=f"inbound_{comp_id}_{sheet.title}")

        # ====== تحديث مباشر لكل حالات أرامكس ======
        if new_outbound:
            status_out = get_aramex_status(new_outbound)
            st.info(f"🚚 Outbound AWB: {new_outbound} | الحالة: {status_out}")
        if new_inbound:
            status_in = get_aramex_status(new_inbound)
            st.info(f"📦 Inbound AWB: {new_inbound} | الحالة: {status_in}")

        col1, col2, col3, col4 = st.columns(4)
        if col1.button("💾 حفظ", key=f"save_{comp_id}_{sheet.title}"):
            safe_update(sheet, f"B{i}", [[new_type]])
            safe_update(sheet, f"C{i}", [[new_notes]])
            safe_update(sheet, f"D{i}", [[new_action]])
            safe_update(sheet, f"G{i}", [[new_outbound]])
            safe_update(sheet, f"H{i}", [[new_inbound]])
            st.success("✅ تم التعديل")
            st.session_state.rerun_flag = True

        if col2.button("🗑️ حذف", key=f"delete_{comp_id}_{sheet.title}"):
            safe_delete(sheet, i)
            st.warning("🗑️ تم حذف الشكوى")
            st.session_state.rerun_flag = True

        if col3.button("📦 أرشفة", key=f"archive_{comp_id}_{sheet.title}"):
            safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
            time.sleep(0.5)
            safe_delete(sheet, i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.session_state.rerun_flag = True

        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{comp_id}_{sheet.title}"):
                safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للإجراءات المردودة")
                st.session_state.rerun_flag = True
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{comp_id}_{sheet.title}"):
                safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للنشطة")
                st.session_state.rerun_flag = True

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
                st.info(f"🚚 Outbound AWB: {outbound_awb} | الحالة: {get_aramex_status(outbound_awb)}")
            if inbound_awb:
                st.info(f"📦 Inbound AWB: {inbound_awb} | الحالة: {get_aramex_status(inbound_awb)}")
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
            st.session_state.rerun_flag = True
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

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
            col1, col2, col3 = st.columns(3)
            if col1.button("💾 حفظ", key=f"save_aramex_{order_id}"):
                safe_update(aramex_sheet, f"B{i}", [[new_status]])
                safe_update(aramex_sheet, f"D{i}", [[new_action]])
                st.success("✅ تم تعديل الطلب")
                st.session_state.rerun_flag = True
            if col2.button("🗑️ حذف", key=f"delete_aramex_{order_id}"):
                safe_delete(aramex_sheet, i)
                st.warning("🗑️ تم حذف الطلب")
                st.session_state.rerun_flag = True
            if col3.button("📦 أرشفة", key=f"archive_aramex_{order_id}"):
                safe_append(aramex_archive, [order_id, new_status, date_added, new_action])
                time.sleep(0.5)
                safe_delete(aramex_sheet, i)
                st.success("♻️ تم أرشفة الطلب")
                st.session_state.rerun_flag = True

# ====== إعادة التشغيل إذا تم تعديل أي شيء ======
if 'rerun_flag' in st.session_state and st.session_state.rerun_flag:
    st.session_state.rerun_flag = False
    st.experimental_rerun()

# ======================================================
# ====== قسم محمي: شحن / طلب مندوب / إرجاع  (باسورد) ======
# ======================================================

def check_password():
    """
    يتحقق من st.secrets['1234'].
    ضع كلمة السر في Streamlit Secrets كـ admin_password.
    """
    def password_entered():
        # تستخدم st.session_state["password"] للمقارنة
        if st.session_state.get("password") == st.secrets.get("admin_password"):
            st.session_state["password_correct"] = True
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔑 أدخل كلمة السر للوصول لقسم الشحن/المندوب/الإرجاع:", type="password", key="password", on_change=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔑 أدخل كلمة السر للوصول لقسم الشحن/المندوب/الإرجاع:", type="password", key="password", on_change=password_entered)
        st.error("❌ كلمة السر غير صحيحة")
        return False
    else:
        return True

# دوال مساعدة لشحن/مندوب/ارجاع (مقتبسة من ملفاتك المرفوعة، مع بعض التكييف لـ Streamlit)
def to_aramex_datetime(dt):
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    ms = int((dt - epoch).total_seconds() * 1000)
    return f"/Date({ms})/"

def to_aramex_datetime_from_time(t):
    now = datetime.now(timezone.utc)
    dt = datetime.combine(now.date(), t, tzinfo=timezone.utc)
    ms = int(dt.timestamp() * 1000)
    return f"/Date({ms})/"

# دالة إنشاء بوالص - تدعم وضعية return_mode (لعكس الشاحن/المتلقي عند الإرجاع)
def create_shipments_from_df(df, save_pdf=False, default_pieces=1, return_mode=False):
    """
    يعيد df محدثاً مع TrackingNumber و LabelURL.
    إذا return_mode=True ستُبنى الشحنة كإرجاع (الشركة تصبح Consignee والعكس).
    """
    url = "https://ws.aramex.net/ShippingAPI.V2/Shipping/Service_1_0.svc/json/CreateShipments"
    headers = {"Content-Type": "application/json"}

    if "LabelURL" not in df.columns:
        df["LabelURL"] = ""
    if "TrackingNumber" not in df.columns:
        df["TrackingNumber"] = ""

    for index, row in df.iterrows():
        order_number = str(row.get("OrderNumber", row.get("ReferenceNumber", "")))
        # عدد القطع
        try:
            num_pieces = int(row.get("Pieces", default_pieces))
        except:
            num_pieces = default_pieces

        # إعداد أسماء وهواتف
        consignee_name = str(row.get("CustomerName", "")).strip()
        if not consignee_name:
            # نتخطى السطر إن لم يوجد اسم
            continue

        try:
            customer_phone = str(int(row.get("CustomerPhone"))) if pd.notna(row.get("CustomerPhone")) and row.get("CustomerPhone") != "" else "0000000000"
        except:
            customer_phone = str(row.get("CustomerPhone", "0000000000"))

        shipping_dt = datetime.now(timezone.utc)
        due_dt = shipping_dt + timedelta(days=2)

        # اعتماداً على return_mode، نبدل الشاحن والمتلقي
        if not return_mode:
            shipper_party_address = {
                "Line1": row.get("AddressLine", ""),
                "City": row.get("City", ""),
                "PostCode": str(row.get("PostalCode", "")),
                "CountryCode": row.get("CountryCode", "SA")
            }
            shipper_contact = {
                "PersonName": consignee_name,
                "CompanyName": consignee_name,
                "PhoneNumber1": customer_phone,
                "PhoneNumber2": customer_phone,
                "CellPhone": customer_phone,
                "EmailAddress": row.get("CustomerEmail", "")
            }
            consignee_party_address = {
                "Line1": "الرياض حي السلي شارع ابن ماجه",
                "City": "Riyadh",
                "PostCode": "14265",
                "CountryCode": "SA"
            }
            consignee_contact = {
                "PersonName": "شركة عالم الرشاقة للتجارة",
                "CompanyName": "شركة عالم الرشاقة للتجارة",
                "PhoneNumber1": "00966560000496",
                "PhoneNumber2": "00966560000496",
                "CellPhone": "00966560000496",
                "EmailAddress": "world-fitness@outlook.sa"
            }
        else:
            # في حالة الإرجاع: الشاحن هو المستلم الأصلي، والمتلقي هو الشركة
            shipper_party_address = {
                "Line1": "الرياض حي السلي شارع ابن ماجه",
                "City": "Riyadh",
                "PostCode": "14265",
                "CountryCode": "SA"
            }
            shipper_contact = {
                "PersonName": "شركة عالم الرشاقة للتجارة",
                "CompanyName": "شركة عالم الرشاقة للتجارة",
                "PhoneNumber1": "00966560000496",
                "PhoneNumber2": "00966560000496",
                "CellPhone": "00966560000496",
                "EmailAddress": "world-fitness@outlook.sa"
            }
            consignee_party_address = {
                "Line1": row.get("AddressLine", ""),
                "City": row.get("City", ""),
                "PostCode": str(row.get("PostalCode", "")),
                "CountryCode": row.get("CountryCode", "SA")
            }
            consignee_contact = {
                "PersonName": consignee_name,
                "CompanyName": consignee_name,
                "PhoneNumber1": customer_phone,
                "PhoneNumber2": customer_phone,
                "CellPhone": customer_phone,
                "EmailAddress": row.get("CustomerEmail", "")
            }

        payload = {
            "ClientInfo": client_info,
            "LabelInfo": {"ReportID": 9729, "ReportType": "URL"},
            "Shipments": [{
                "Reference1": row.get("ReferenceNumber", order_number),
                "Reference2": "",
                "Shipper": {
                    "Reference1": row.get("ReferenceNumber", ""),
                    "Reference2": "",
                    "AccountNumber": client_info["AccountNumber"],
                    "PartyAddress": shipper_party_address,
                    "Contact": shipper_contact
                },
                "Consignee": {
                    "Reference1": row.get("ReferenceNumber", ""),
                    "Reference2": "",
                    "AccountNumber": "",
                    "PartyAddress": consignee_party_address,
                    "Contact": consignee_contact
                },
                "ShippingDateTime": to_aramex_datetime(shipping_dt),
                "DueDate": to_aramex_datetime(due_dt),
                "Comments": "",
                "PickupLocation": "",
                "Details": {
                    "Dimensions": None,
                    "ActualWeight": {"Value": float(row.get("WeightKG", 1.0)), "Unit": "KG"},
                    "ChargeableWeight": {"Value": float(row.get("WeightKG", 1.0)), "Unit": "KG"},
                    "DescriptionOfGoods": row.get("Description", ""),
                    "GoodsOriginCountry": "SA",
                    "NumberOfPieces": num_pieces,
                    "ProductGroup": row.get("ProductGroup", "DOM"),
                    "ProductType": row.get("ProductType", "CDS"),
                    "PaymentType": row.get("PaymentType", "P"),
                    "PaymentOptions": "",
                    "CustomsValueAmount": {"Value": row.get("CustomsValue", 0) or 0, "CurrencyCode": "SAR"},
                    "CashOnDeliveryAmount": {"Value": float(row.get("CODAmount", 0) or 0), "CurrencyCode": "SAR"},
                    "InsuranceAmount": {"Value": 0, "CurrencyCode": "SAR"},
                    "CashAdditionalAmount": {"Value": 0, "CurrencyCode": "SAR"},
                    "CashAdditionalAmountDescription": "",
                    "CollectAmount": {"Value": 0, "CurrencyCode": "SAR"},
                    "Services": "",
                    "Items": []
                }
            }]
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
        except Exception as e:
            st.warning(f"❌ خطأ في إرسال الطلب للأرامكس للطلب {order_number}: {e}")
            continue

        if response.status_code == 200:
            try:
                # نتحسس إن الرد ربما XML، نحلله بعناية
                root = ET.fromstring(response.text)
                # محاولة العثور على ProcessedShipment ضمن الـ namespace المعتاد
                ns = {'ns': 'http://ws.aramex.net/ShippingAPI/v1/'}
                processed_shipment = root.find('.//ns:ProcessedShipment', ns)
                if processed_shipment is not None:
                    has_errors = processed_shipment.find('ns:HasErrors', ns)
                    if has_errors is not None and has_errors.text.lower() == 'true':
                        st.warning(f"❌ أرامكس أبلغ عن خطأ لشحنة {order_number}")
                    else:
                        tracking_id_elem = processed_shipment.find('ns:ID', ns)
                        label_url_elem = processed_shipment.find('.//ns:ShipmentLabel/ns:LabelURL', ns)
                        tracking_id = tracking_id_elem.text if tracking_id_elem is not None else ""
                        label_url = label_url_elem.text if label_url_elem is not None else ""
                        df.at[index, "TrackingNumber"] = tracking_id
                        df.at[index, "LabelURL"] = label_url
                        st.success(f"✅ بوليصة {order_number} : {tracking_id}")
                else:
                    st.info(f"رد أرامكس غير متوقع للطلب {order_number}. راجع السجل.")
            except Exception as e:
                st.info(f"⚠️ لم يتم تحليل رد أرامكس للطلب {order_number}: {e}")
        else:
            st.warning(f"❌ HTTP {response.status_code} من أرامكس للطلب {order_number}")

    return df

# دالة طلب المندوب (CreatePickup)
def request_pickup_for_df(df):
    url_pickup = "https://ws.aramex.net/ShippingAPI.V2/Shipping/Service_1_0.svc/json/CreatePickup"
    headers = {"Content-Type": "application/json"}

    if "PickupReference" not in df.columns:
        df["PickupReference"] = ""

    for idx, row in df.iterrows():
        order_number = row.get("ReferenceNumber", row.get("OrderNumber", "unknown"))
        shipper_data = {
            "PartyAddress": {
                "Line1": row.get("PickupAddress", row.get("AddressLine", "")),
                "City": row.get("City", "Riyadh"),
                "PostCode": row.get("PostalCode", ""),
                "CountryCode": "SA"
            },
            "Contact": {
                "PersonName": row.get("CustomerName", ""),
                "CompanyName": row.get("CustomerName", ""),
                "PhoneNumber1": str(row.get("CustomerPhone", "0000000000")),
                "PhoneNumber2": str(row.get("CustomerPhone", "0000000000")),
                "CellPhone": str(row.get("CustomerPhone", "0000000000")),
                "EmailAddress": row.get("CustomerEmail", "")
            }
        }
        num_pieces = int(row.get("Pieces", 1)) if pd.notna(row.get("Pieces")) else 1
        weight_kg = float(row.get("WeightKG", 1.0)) if pd.notna(row.get("WeightKG")) else 1.0

        pickup_date_str = to_aramex_datetime(datetime.now(timezone.utc))
        pickup_time_str = to_aramex_datetime_from_time(dtime(9,0))
        ready_time_str = to_aramex_datetime_from_time(dtime(9,0))
        last_pickup_time_str = to_aramex_datetime_from_time(dtime(18,0))
        closing_time_str = to_aramex_datetime_from_time(dtime(19,0))

        payload_pickup = {
            "ClientInfo": client_info,
            "Pickup": {
                "PickupLocation": shipper_data["PartyAddress"]["City"],
                "PickupAddress": {
                    "Line1": shipper_data["PartyAddress"].get("Line1", ""),
                    "City": shipper_data["PartyAddress"].get("City", ""),
                    "PostCode": shipper_data["PartyAddress"].get("PostCode", ""),
                    "CountryCode": shipper_data["PartyAddress"].get("CountryCode", "SA")
                },
                "PickupContact": shipper_data["Contact"],
                "PickupItems": [{
                    "PackageType": "Box",
                    "Quantity": num_pieces,
                    "ProductGroup": "DOM",
                    "ProductType": "PPX",
                    "NumberOfShipments": 1,
                    "Payment": "P",
                    "ShipmentWeight": {"Value": weight_kg, "Unit": "KG"},
                    "NumberOfPieces": num_pieces
                }],
                "PickupDate": pickup_date_str,
                "PickupTime": pickup_time_str,
                "ReadyTime": ready_time_str,
                "LastPickupTime": last_pickup_time_str,
                "ClosingTime": closing_time_str,
                "Comments": "طلب مندوب من البرنامج",
                "PickupLocationDetails": shipper_data["PartyAddress"].get("Line1",""),
                "AccountNumber": client_info["AccountNumber"],
                "AccountPin": client_info["AccountPin"],
                "AccountEntity": client_info["AccountEntity"],
                "AccountCountryCode": client_info["AccountCountryCode"],
                "Reference1": str(order_number),
                "Status": "Ready"
            }
        }

        try:
            response = requests.post(url_pickup, json=payload_pickup, headers=headers, timeout=60)
        except Exception as e:
            st.warning(f"❌ خطأ في طلب المندوب للطلب {order_number}: {e}")
            df.at[idx, "PickupReference"] = f"خطأ: {e}"
            continue

        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                ns = {'ns': 'http://ws.aramex.net/ShippingAPI/v1/'}
                pickup_ref_elem = root.find('.//ns:ID', ns)
                if pickup_ref_elem is not None and pickup_ref_elem.text:
                    df.at[idx, "PickupReference"] = pickup_ref_elem.text
                    st.success(f"✅ طلب مندوب للطلب {order_number}: {pickup_ref_elem.text}")
                else:
                    df.at[idx, "PickupReference"] = "لم يتم الحصول على رقم"
                    st.info(f"رد بدون رقم مندوب لِـ {order_number}")
            except Exception as e:
                df.at[idx, "PickupReference"] = "خطأ تحليل الرد"
                st.info(f"⚠️ لم يتم تحليل رد المندوب للطلب {order_number}: {e}")
        else:
            df.at[idx, "PickupReference"] = f"HTTP {response.status_code}"
            st.warning(f"❌ HTTP {response.status_code} لطلب المندوب {order_number}")

    return df

# واجهة القسم المحمي
st.markdown("---")
st.header("🔒 قسم الشحن / المندوب / الإرجاع (محمي بكلمة سر)")
if check_password():
    st.success("🔓 تمت المصادقة — يمكنك الوصول لميزات الشحن/المندوب/الإرجاع")

    # --- إدارة الشحنات: رفع ملف أو استخدام ملف محلي ---
    st.subheader("📦 إدارة الشحنات - إنشاء بوليصات وطلب مندوب وإرجاع")
    st.markdown("رفع ملف Excel بشحناتك. الأعمدة المقترحة: ReferenceNumber/OrderNumber, CustomerName, CustomerPhone, AddressLine, City, PostalCode, WeightKG, CODAmount, Description, Pieces, ProductGroup, ProductType, PaymentType, CustomsValue")

    uploaded_file = st.file_uploader("رفع ملف إكسل للشحن (أو اترك لاستخدام الملف المحلي)", type=["xlsx","xls"])
    use_local_if_exists = st.checkbox("استخدام ملف محلي shipments_with_tracking.xlsx إن وجد", value=True)

    df = None
    input_filename = "shipments_with_tracking.xlsx"
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            st.success("تم تحميل الملف بنجاح")
        except Exception as e:
            st.error(f"فشل قراءة الإكسل المرفوع: {e}")
    else:
        if use_local_if_exists:
            try:
                df = pd.read_excel(input_filename)
                st.info(f"تم فتح الملف المحلي: {input_filename}")
            except Exception:
                df = None

    if df is None:
        st.info("لم يتم تحميل ملف بيانات الشحن بعد.")
    else:
        st.dataframe(df.head(10))

        col1, col2 = st.columns(2)
        default_pieces = col1.number_input("عدد القطع الافتراضي", min_value=1, value=1)
        do_create = col2.button("🚚 إنشاء بوليصات (CreateShipments)")
        do_pickup = st.button("📝 طلب مندوب لكل الشحنات (CreatePickup)")
        do_return = st.button("🔄 إنشاء بوالص إرجاع (Return Shipments)")

        if do_create:
            with st.spinner("جاري إنشاء البوالص ..."):
                df_out = create_shipments_from_df(df.copy(), default_pieces=default_pieces, return_mode=False)
                out_buf = io.BytesIO()
                df_out.to_excel(out_buf, index=False)
                out_buf.seek(0)
                st.success("انتهى إنشاء البوالص — تم تحديث الملف أدناه.")
                st.download_button("⬇️ تنزيل الملف المحدث (مع Tracking/LabelURL)", data=out_buf, file_name="shipments_with_tracking_updated.xlsx")
                try:
                    df_out.to_excel("shipments_with_tracking_updated.xlsx", index=False)
                except Exception:
                    pass

        if do_pickup:
            with st.spinner("جاري طلب المندوب ..."):
                try:
                    df_to_pick = pd.read_excel("shipments_with_tracking_updated.xlsx")
                except Exception:
                    df_to_pick = df.copy()
                df_with_pick = request_pickup_for_df(df_to_pick)
                buf2 = io.BytesIO()
                df_with_pick.to_excel(buf2, index=False)
                buf2.seek(0)
                st.success("انتهت أوامر المندوب — تم تحديث ملف الإكسل برقم المندوب.")
                st.download_button("⬇️ تنزيل ملف المندوب المحدث", data=buf2, file_name="shipments_with_pickup.xlsx")
                try:
                    df_with_pick.to_excel("shipments_with_pickup.xlsx", index=False)
                except Exception:
                    pass

        if do_return:
            with st.spinner("جاري إنشاء بوالص الإرجاع ..."):
                df_returns = create_shipments_from_df(df.copy(), default_pieces=default_pieces, return_mode=True)
                buf3 = io.BytesIO()
                df_returns.to_excel(buf3, index=False)
                buf3.seek(0)
                st.success("✅ تم إنشاء بوالص الإرجاع — يمكنك تنزيل الملف")
                st.download_button("⬇️ تنزيل ملف الإرجاع", data=buf3, file_name="returns_with_tracking.xlsx")
                try:
                    df_returns.to_excel("returns_with_tracking.xlsx", index=False)
                except Exception:
                    pass

    st.markdown("**تنبيه أمني:** فقط الأشخاص الذين يعرفون `admin_password` في `st.secrets` بإمكانهم رؤية هذا القسم وتشغيله.")

# === نهاية الملف ===
