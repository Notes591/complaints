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

# مكتبات جديدة للتوقيع الإلكتروني بالرسم
from streamlit_drawable_canvas import st_canvas
import numpy as np
from PIL import Image
import io
import base64

# ====== تحديث تلقائي (قابلة للتعديل) ======
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

# تخزين client في session_state لتجنب إعادة الاتصال المتكرر
if "gspread_client" not in st.session_state:
    client = gspread.authorize(creds)
    st.session_state["gspread_client"] = client
else:
    client = st.session_state["gspread_client"]

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number",
    "PendingApproval"
]

# تخزين sheets_dict في session_state لتجنب إعادة القراءة المتكررة
if "sheets_dict" not in st.session_state:
    sheets_dict = {}
    for title in sheet_titles:
        try:
            sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
        except Exception as e:
            try:
                ss = client.open(SHEET_NAME)
                sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")
            except Exception as e2:
                st.error(f"خطأ في الوصول/إنشاء ورقة: {title} - {e2}")
                raise
    st.session_state["sheets_dict"] = sheets_dict
else:
    sheets_dict = st.session_state["sheets_dict"]

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]
pending_approval_sheet = sheets_dict.get("PendingApproval")

# ====== إعداد الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
        except Exception:
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
        except Exception:
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
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== تحميل الأنواع ومصادر البيانات ======
@st.cache_data(ttl=60)
def get_types_list():
    try:
        return [row[0] for row in types_sheet.get_all_values()[1:]]
    except Exception:
        return []

types_list = get_types_list()

@st.cache_data(ttl=60)
def get_return_warehouse_data():
    try:
        return return_warehouse_sheet.get_all_values()[1:]
    except Exception:
        return []

return_warehouse_data = get_return_warehouse_data()

def get_returnwarehouse_record(order_id):
    for row in return_warehouse_data:
        if len(row) > 0 and str(row[0]) == str(order_id):
            return {
                "رقم الطلب": row[0],
                "الفاتورة": row[1] if len(row) > 1 else "",
                "التاريخ": row[2] if len(row) > 2 else "",
                "الزبون": row[3] if len(row) > 3 else "",
                "المبلغ": row[4] if len(row) > 4 else "",
                "رقم الشحنة": row[5] if len(row) > 5 else "",
                "البيان": row[6] if len(row) > 6 else ""
            }
    return None

@st.cache_data(ttl=60)
def get_order_number_data():
    try:
        return order_number_sheet.get_all_values()[1:]
    except Exception:
        return []

order_number_data = get_order_number_data()

def get_order_status(order_id):
    for row in order_number_data:
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f"الطلب الاساسي🚚 مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "الطلب الاساسي⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"

# ====== إعداد Aramex ======
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

@st.cache_data(ttl=300)
def cached_aramex_status(awb):
    if not awb or str(awb).strip() == "":
        return ""
    return get_aramex_status(awb)

# ====== قسم المدير ======
st.markdown("---")
st.header("🔐 قسم المدير - اعتماد الشكاوى (خاص)")
DEFAULT_ADMIN_PASS = st.secrets.get("admin_pass", "Admin123")

if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False
if "show_admin_settings" not in st.session_state:
    st.session_state["show_admin_settings"] = False

col_a, col_b, col_c = st.columns([2, 1, 1])
with col_a:
    if not st.session_state["admin_logged_in"]:
        admin_pass_input = st.text_input("🔑 أدخل كلمة مرور المدير لتسجيل الدخول:", type="password", key="admin_login_input")
        if st.button("تسجيل دخول كمدير"):
            current_pass = st.secrets.get("admin_pass", DEFAULT_ADMIN_PASS)
            if admin_pass_input == current_pass:
                st.session_state["admin_logged_in"] = True
                st.success("✅ تم تسجيل الدخول كمدير")
            else:
                st.error("❌ كلمة المرور غير صحيحة")
    else:
        st.success("✅ المدير مسجل دخول")
        if st.button("تسجيل خروج (الخروج من وضع المدير)"):
            st.session_state["admin_logged_in"] = False
            st.experimental_rerun()

with col_b:
    if st.button("⚙️ Settings"):
        st.session_state["show_admin_settings"] = not st.session_state["show_admin_settings"]

with col_c:
    st.write("")

if st.session_state.get("show_admin_settings"):
    st.markdown("#### 🔧 إعدادات المدير (تغيير كلمة المرور)")
    cur = st.text_input("🔒 كلمة المرور الحالية:", type="password", key="admin_cur_pass")
    newp = st.text_input("🔐 كلمة المرور الجديدة:", type="password", key="admin_new_pass")
    newp2 = st.text_input("🔐 تأكيد كلمة المرور الجديدة:", type="password", key="admin_new_pass2")
    if st.button("تغيير كلمة المرور"):
        stored = st.secrets.get("admin_pass", DEFAULT_ADMIN_PASS)
        if cur != stored:
            st.error("❌ كلمة المرور الحالية غير صحيحة. لا يمكن تغييرها.")
        else:
            if not newp or newp != newp2:
                st.error("⚠️ تأكد من إدخال كلمة المرور الجديدة ومطابقتها في الحقلين.")
            else:
                st.info("🔔 لضبط القيمة بشكل دائم: غيّر admin_pass في إعدادات secrets لتطبيق Streamlit")
                st.success("✅ كلمة المرور الجديدة جاهزة - (تأكد من حفظها في st.secrets لاحقًا)")

# ====== واجهة PendingApproval والتوقيع الإلكتروني ======
if st.session_state.get("admin_logged_in"):
    st.markdown("---")
    st.subheader("📋 الشكاوى في انتظار الاعتماد")

    try:
        pending_data_raw = pending_approval_sheet.get_all_values()
    except Exception:
        pending_data_raw = []

    pending_rows = []
    if len(pending_data_raw) > 0:
        for row in pending_data_raw:
            if not any(cell.strip() for cell in row):
                continue
            while len(row) < 10:
                row.append("")
            pending_rows.append(row)

    if len(pending_rows) == 0:
        st.info("لا توجد شكاوى في انتظار الاعتماد حالياً.")
    else:
        for idx, prow in enumerate(pending_rows, start=1):
            comp_id = prow[0]
            if not str(comp_id).strip():
                continue
            comp_type = prow[1]
            notes = prow[2]
            action = prow[3]
            date_added = prow[4]
            restored = prow[5]
            outbound_awb = prow[6]
            inbound_awb = prow[7]
            source_sheet = prow[8] if len(prow) > 8 and prow[8].strip() else "Complaints"
            sent_time = prow[9] if len(prow) > 9 else ""

            with st.expander(f"📌 {comp_id} | {comp_type} | من: {source_sheet}"):
                st.write(f"📝 الملاحظات: {notes}")
                st.write(f"✅ الإجراء: {action}")
                if sent_time:
                    st.caption(f"📅 تم إرسالها لانتظار الاعتماد بتاريخ: {sent_time}")
                else:
                    st.caption(f"📅 مصدر الإرسال: {source_sheet}")

                st.write("✍️ رسم التوقيع أدناه (يمكن الرسم بالماوس أو اللمس):")
                canvas_result = st_canvas(
                    fill_color="rgba(0,0,0,0)",
                    stroke_width=2,
                    stroke_color="#000000",
                    background_color="#fff",
                    height=150,
                    width=400,
                    drawing_mode="freedraw",
                    key=f"canvas_{comp_id}"
                )

                signer_text = st.text_input(f"أو اكتب توقيع المدير (خيار احتياطي) - {comp_id}", key=f"sign_text_{comp_id}")

                signer_image_str = ""
                if canvas_result.image_data is not None:
                    try:
                        img = Image.fromarray(np.uint8(canvas_result.image_data))
                        buffered = io.BytesIO()
                        img.save(buffered, format="PNG")
                        signer_image_str = base64.b64encode(buffered.getvalue()).decode()
                        st.image(img, caption="معاينة التوقيع المرسوم", width=200)
                    except Exception as e:
                        st.error(f"خطأ في معالجة صورة التوقيع: {e}")

                col1, col2 = st.columns(2)
                if col1.button(f"✅ تم الاعتماد - {comp_id}", key=f"approve_{comp_id}"):
                    if not signer_text.strip() and not signer_image_str:
                        st.warning("⚠️ أضف توقيع المدير (مرسومًا أو نصيًا) قبل الضغط على تم الاعتماد.")
                    else:
                        approval_note = f"{action}\n\n✅ تم الاعتماد بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        if signer_text.strip():
                            approval_note += f" | اعتمد بواسطة: {signer_text}"
                        if signer_image_str:
                            approval_note += " | توقيع المدير محفوظ كصورة Base64"
                        row_to_return = [comp_id, comp_type, notes, approval_note, date_added, "✅ معتمدة", outbound_awb, inbound_awb, signer_image_str]
                        target_sheet = complaints_sheet if source_sheet == "Complaints" else responded_sheet
                        appended = safe_append(target_sheet, row_to_return)
                        if appended:
                            try:
                                all_pending = pending_approval_sheet.get_all_values()
                            except Exception:
                                all_pending = []
                            deleted = False
                            for p_i, p_row in enumerate(all_pending, start=1):
                                if len(p_row) > 0 and str(p_row[0]) == str(comp_id):
                                    try:
                                        safe_delete(pending_approval_sheet, p_i)
                                        deleted = True
                                    except Exception:
                                        deleted = False
                                    break
                            if deleted:
                                st.success(f"✅ تم اعتماد الشكوى {comp_id} وإعادتها إلى {source_sheet}")
                            else:
                                st.warning(f"⚠️ تمت إعادة الشكوى ولكن لم أتمكن من حذفها من PendingApproval تلقائيًا. تأكد وحذفها يدويًا إن لزم.")
                if col2.button(f"❌ رفض وإرجاع للنشاط - {comp_id}", key=f"reject_{comp_id}"):
                    row_to_return = [comp_id, comp_type, notes, action, date_added, restored, outbound_awb, inbound_awb]
                    target_sheet = complaints_sheet if source_sheet == "Complaints" else responded_sheet
                    appended = safe_append(target_sheet, row_to_return)
                    if appended:
                        try:
                            all_pending = pending_approval_sheet.get_all_values()
                        except Exception:
                            all_pending = []
                        deleted = False
                        for p_i, p_row in enumerate(all_pending, start=1):
                            if len(p_row) > 0 and str(p_row[0]) == str(comp_id):
                                try:
                                    safe_delete(pending_approval_sheet, p_i)
                                    deleted = True
                                except Exception:
                                    deleted = False
                                break
                        if deleted:
                            st.info(f"ℹ️ تم رفض الشكوى {comp_id} وإعادتها إلى {source_sheet}")
                        else:
                            st.warning(f"ℹ️ تم إرجاع الشكوى {comp_id} لكن لم أتمكن من حذفها من PendingApproval تلقائيًا.")

# ====== دالة عرض الشكوى ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    with st.expander(f"📌 {comp_id} | {comp_type} | من: {'Responded' if in_responded else 'Archive' if in_archive else 'Complaints'}"):
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        if date_added:
            st.caption(f"📅 أضيفت بتاريخ: {date_added}")

        if outbound_awb:
            st.write(f"📦 رقم الشحنة الصادرة: {outbound_awb} | الحالة: {cached_aramex_status(outbound_awb)}")
        if inbound_awb:
            st.write(f"📦 رقم الشحنة الواردة: {inbound_awb} | الحالة: {cached_aramex_status(inbound_awb)}")

# ====== عرض الشكاوى الحالية ======
st.markdown("---")
st.subheader("📄 عرض الشكاوى الحالية")
try:
    complaints_data = complaints_sheet.get_all_values()[1:]
except Exception:
    complaints_data = []

if len(complaints_data) == 0:
    st.info("لا توجد شكاوى حالياً.")
else:
    for i, row in enumerate(complaints_data):
        render_complaint(complaints_sheet, i, row)

# ====== عرض الشكاوى المردودة (Responded) ======
st.markdown("---")
st.subheader("✅ الشكاوى المعتمدة (Responded)")
try:
    responded_data = responded_sheet.get_all_values()[1:]
except Exception:
    responded_data = []

if len(responded_data) == 0:
    st.info("لا توجد شكاوى معتمدة حالياً.")
else:
    for i, row in enumerate(responded_data):
        render_complaint(responded_sheet, i, row, in_responded=True)

# ====== عرض أرشيف الشكاوى (Archive) ======
st.markdown("---")
st.subheader("🗄️ أرشيف الشكاوى")
try:
    archive_data = archive_sheet.get_all_values()[1:]
except Exception:
    archive_data = []

if len(archive_data) == 0:
    st.info("لا يوجد أرشيف شكاوى حالياً.")
else:
    for i, row in enumerate(archive_data):
        render_complaint(archive_sheet, i, row, in_archive=True)
