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
# القيمة بالمللي ثانية - الافتراضي 20 دقيقة (1200000). لو تريد 60 ثانية ضع 60000.
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
# أضفنا ورقة PendingApproval هنا لتخزين الشكاوى المرسلة لانتظار الاعتماد
sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number",
    "PendingApproval"  # ورقة جديدة لانتظار الاعتماد
]

sheets_dict = {}
for title in sheet_titles:
    time.sleep(1)  # تأخير لتفادي API quota
    try:
        sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
    except Exception as e:
        # محاولة إنشاء الورقة لو مش موجودة لتفادي الأخطاء
        try:
            ss = client.open(SHEET_NAME)
            sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")
        except Exception as e2:
            st.error(f"خطأ في الوصول/إنشاء ورقة: {title} - {e2}")
            raise

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]
# الورقة الجديدة لانتظار الاعتماد
pending_approval_sheet = sheets_dict.get("PendingApproval")

# ====== إعداد الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== دوال Retry (احتفظنا بها كما طلبت) ======
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

# ====== إعداد Aramex (مثل الموجود في كودك) ======
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

# ====== Cache لحالات Aramex لتقليل النداءات ======
@st.cache_data(ttl=300)
def cached_aramex_status(awb):
    if not awb or str(awb).strip() == "":
        return ""
    return get_aramex_status(awb)

# ====== قسم المدير: إدارة كلمة المرور واعتماد الشكاوى (قسم منفصل) ======
# هذه الواجهة تم إضافتها لتسمح للمدير بتسجيل الدخول، رؤية الشكاوى المعلقة، وتغيير كلمة المرور
st.markdown("---")
st.header("🔐 قسم المدير - اعتماد الشكاوى (خاص)")

# كلمة مرور المدير مخزنة في st.secrets تحت المفتاح admin_pass إن وُجد، وإلا نستخدم القيمة الافتراضية
DEFAULT_ADMIN_PASS = st.secrets.get("admin_pass", "Admin123")

# جلسة لتخزين حالة تسجيل دخول المدير داخل الجلسة الحالية
if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False

# حالة إظهار/إخفاء إعدادات
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
    st.stop()  # منع التحديث المتكرر بعد تسجيل الخروج أو الدخول

with col_b:
    # زر لإظهار/إخفاء إعدادات المدير (حقل تغيير كلمة المرور) — يظهر فقط بعد تسجيل الدخول
    if st.button("⚙️ Settings"):
        # نبدّل حالة الظهور
        st.session_state["show_admin_settings"] = not st.session_state["show_admin_settings"]

with col_c:
    st.write("")  # مسافة للحفظ في الشكل

# إعدادات تغيير كلمة المرور (مخفية عن الموظفين) — تظهر فقط لو ضغط المدير زر Settings
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
                # ملاحظة: st.secrets لا يمكن تعديله من التطبيق، لذا نعرض تعليمات لحفظها يدويا
                st.info("🔔 لتنفيذ التغيير بشكل دائم: اضبط القيمة 'admin_pass' في إعدادات secrets لتطبيق Streamlit (ستحتاج لتحديث التطبيق).")
                st.success("✅ كلمة المرور الجديدة جاهزة - (تأكد من حفظها في st.secrets لاحقًا)")

# إذا المدير مسجل دخول، نعرض جدول الانتظار لاعتماد الشكاوى
if st.session_state.get("admin_logged_in"):
    st.markdown("---")
    st.subheader("📋 الشكاوى في انتظار الاعتماد")

    # قراءة مرنة لورقة PendingApproval: نأخذ كل الصفوف (بغض النظر عن وجود Header أم لا)
    try:
        pending_data_raw = pending_approval_sheet.get_all_values()
    except Exception:
        pending_data_raw = []

    # نتعامل مع القائمة حتى لو لم يكن فيها عنوان
    if len(pending_data_raw) > 0:
        # إذا الصفحة فارغة أو تحتوي على صف واحد فارغ -> لا شكاوى
        # سنعرض كل الصفوف من index 0 إن لم تكن صف عناوين واضح
        # للتحقق إذا كان الصف الأول يشبه header نقدر نفحص عناصره، لكن لتبسيط:
        # سنعتبر أن كل صف يحتوي على ID (العمود 0). إن لم يوجد ID -> نتجاهل الصف.
        pending_rows = []
        for row in pending_data_raw:
            # تجاهل الصفوف الفارغة تمامًا
            if not any(cell.strip() for cell in row):
                continue
            # بعض الصفوف قد تكون أقصر؛ نملأها بقيم فارغة
            while len(row) < 10:
                row.append("")
            # الآن إضافة
            pending_rows.append(row)

        if len(pending_rows) == 0:
            st.info("لا توجد شكاوى في انتظار الاعتماد حالياً.")
        else:
            # نعرض كل صف لديه قيمة في العمود 0 (ID)
            for idx, prow in enumerate(pending_rows, start=1):
                comp_id = prow[0]
                # إذا لا يوجد ID، نتخطاه
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

                    # ==== هنا إضافة واجهة التوقيع الإلكتروني بالرسم + حقل نصي احتياطي ====
                    st.write("✍️ رسم التوقيع أدناه (يمكن الرسم بالماوس أو اللمس):")
                    canvas_result = st_canvas(
                        fill_color="rgba(0,0,0,0)",  # شفاف
                        stroke_width=2,
                        stroke_color="#000000",
                        background_color="#fff",
                        height=150,
                        width=400,
                        drawing_mode="freedraw",
                        key=f"canvas_{comp_id}"
                    )

                    signer_text = st.text_input(f"أو اكتب توقيع المدير (خيار احتياطي) - {comp_id}", key=f"sign_text_{comp_id}")

                    # تحويل الرسم إلى Base64 ليتم تخزينه في الشيت (إن وُجد)
                    signer_image_str = ""
                    if canvas_result.image_data is not None:
                        try:
                            img = Image.fromarray(np.uint8(canvas_result.image_data))
                            buffered = io.BytesIO()
                            img.save(buffered, format="PNG")
                            signer_image_str = base64.b64encode(buffered.getvalue()).decode()
                            # عرض الصورة المصغرة للتأكيد
                            st.image(img, caption="معاينة التوقيع المرسوم", width=200)
                        except Exception as e:
                            st.error(f"خطأ في معالجة صورة التوقيع: {e}")

                    col1, col2 = st.columns(2)
                    # عندما يضغط المدير "تم الاعتماد" نعيد السجل إلى الورقة المصدر مع توقيع وتاريخ الاعتماد
                    if col1.button(f"✅ تم الاعتماد - {comp_id}", key=f"approve_{comp_id}"):
                        # نتحقق من وجود توقيع إما نصي أو رسمة
                        if not signer_text.strip() and not signer_image_str:
                            st.warning("⚠️ أضف توقيع المدير (مرسومًا أو نصيًا) قبل الضغط على تم الاعتماد.")
                        else:
                            approval_note = f"{action}\n\n✅ تم الاعتماد بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            if signer_text.strip():
                                approval_note += f" | اعتمد بواسطة: {signer_text}"
                            if signer_image_str:
                                approval_note += " | توقيع المدير محفوظ كصورة Base64"
                            # نضمّن توقيع Base64 كحقل إضافي في السطر (قد تراه في العمود الأخير)
                            row_to_return = [comp_id, comp_type, notes, approval_note, date_added, "✅ معتمدة", outbound_awb, inbound_awb, signer_image_str]
                            target_sheet = complaints_sheet if source_sheet == "Complaints" else responded_sheet
                            # append إلى الورقة الهدف ثم إزالة من pending (نبحث عن السطر المطابق ونحذفه)
                            appended = safe_append(target_sheet, row_to_return)
                            if appended:
                                # محاولة حذف أول صف مطابق في pending_approval_sheet
                                # نبحث في ورقة Google فعليًا للحصول على الفهرس الحقيقي وحذفه
                                try:
                                    all_pending = pending_approval_sheet.get_all_values()
                                except Exception:
                                    all_pending = []
                                deleted = False
                                for p_i, p_row in enumerate(all_pending, start=1):
                                    if len(p_row) > 0 and str(p_row[0]) == str(comp_id):
                                        # حذف الصف (p_i هو index في Google Sheet بداية من 1)
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
                    # زر الرفض: إرجاع للنشطة بدون اعتماد
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
    else:
        st.info("لا توجد شكاوى في انتظار الاعتماد حالياً.")

# ====== دالة عرض الشكوى (كما في كودك) مع بعض تحسينات session_state لتسريع التفاعل ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    # نتأكد من طول الصف
    while len(row) < 8:
        row.append("")

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

            new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0)
            new_notes = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb)
            new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb)

            if new_outbound:
                st.info(f"🚚 Outbound AWB: {new_outbound} | الحالة: {cached_aramex_status(new_outbound)}")
            if new_inbound:
                st.info(f"📦 Inbound AWB: {new_inbound} | الحالة: {cached_aramex_status(new_inbound)}")

            col1, col2, col3, col4 = st.columns(4)
            submitted_save = col1.form_submit_button("💾 حفظ")
            submitted_delete = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")
            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ نقل للإجراءات المردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع للنشطة")

            # زر جديد: إرسال لانتظار الاعتماد (ينقل الشكوى لورقة PendingApproval مع حفظ مصدرها)
            submitted_pending = col4.form_submit_button("⏳ انتظار الاعتماد")

            if submitted_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                st.success("✅ تم التعديل")

            if submitted_delete:
                if safe_delete(sheet, i):
                    st.warning("🗑️ تم حذف الشكوى")

            if submitted_archive:
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        st.success("♻️ الشكوى انتقلت للأرشيف")

            if submitted_move:
                if not in_responded:
                    if safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            st.success("✅ انتقلت للإجراءات المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            st.success("✅ انتقلت للنشطة")

            if submitted_pending:
                # نص محفوظ يوضح من أين أرسلت الشكوى
                original_sheet = "Responded" if in_responded else "Complaints"
                pending_row = [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound, original_sheet, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                if safe_append(pending_approval_sheet, pending_row):
                    if safe_delete(sheet, i):
                        st.info("⏳ تم إرسال الشكوى لانتظار الاعتماد")

# ====== البحث عن شكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")
if search_id.strip():
    found = False
    for sheet_obj, in_responded, in_archive in [
        (complaints_sheet, False, False),
        (responded_sheet, True, False),
        (archive_sheet, False, True)
    ]:
        try:
            data = sheet_obj.get_all_values()
        except Exception:
            data = []
        for i, row in enumerate(data[1:], start=2) if data else []:
            if len(row) > 0 and str(row[0]) == search_id:
                st.success(f"✅ الشكوى موجودة في {'المردودة' if in_responded else 'الأرشيف' if in_archive else 'النشطة'}")
                render_complaint(sheet_obj, i, row, in_responded=in_responded, in_archive=in_archive)
                found = True
                break
        if found:
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
            try:
                complaints = complaints_sheet.get_all_records()
            except Exception:
                complaints = []
            try:
                responded = responded_sheet.get_all_records()
            except Exception:
                responded = []
            try:
                archive = archive_sheet.get_all_records()
            except Exception:
                archive = []

            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_active_ids = [str(c.get("ID", "")) for c in complaints] + [str(r.get("ID", "")) for r in responded]
            all_archive_ids = [str(a.get("ID", "")) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes = row[2] if len(row) > 2 else ""
                        restored_action = row[3] if len(row) > 3 else ""
                        restored_type = row[1] if len(row) > 1 else ""
                        restored_outbound = row[6] if len(row) > 6 else ""
                        restored_inbound = row[7] if len(row) > 7 else ""
                        if safe_append(complaints_sheet, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound]):
                            if safe_delete(archive_sheet, idx):
                                st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                        break
            else:
                if action.strip():
                    if safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb]):
                        st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb]):
                        st.success("✅ تم تسجيل الشكوى في النشطة")
        else:
            st.error("⚠️ لازم تدخل رقم الشكوى وتختار نوع صحيح")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
active_notes = complaints_sheet.get_all_values()
if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== عرض الإجراءات المردودة ======
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
                    if awb and "Delivered" in cached_aramex_status(awb):
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

# ====== قسم إضافة "معلق أرامكس" (كما طلبت قبل عرض المعلق) ======
st.markdown("---")
st.header("🚚 معلق ارامكس")
with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input("📌 الحالة")
    action = st.text_area("✅ الإجراء المتخذ")
    submitted = st.form_submit_button("➕ إضافة")
    if submitted:
        if order_id.strip() and status.strip() and action.strip():
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if safe_append(aramex_sheet, [order_id, status, date_now, action]):
                st.success("✅ تم تسجيل الطلب")
            else:
                st.error("❌ فشل في تسجيل الطلب")
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

# ====== عرض معلق أرامكس (القائمة + تعديل/حذف/أرشفة) ======
st.subheader("📋 قائمة الطلبات المعلقة")
aramex_pending = aramex_sheet.get_all_values()
if len(aramex_pending) > 1:
    for i, row in enumerate(aramex_pending[1:], start=2):
        # نتأكد من طول الصف
        while len(row) < 4:
            row.append("")
        order_id = row[0]
        status = row[1]
        date_added = row[2]
        action = row[3]
        with st.expander(f"📦 طلب {order_id}"):
            st.write(f"📌 الحالة الحالية: {status}")
            st.write(f"✅ الإجراء الحالي: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            with st.form(key=f"form_aramex_{order_id}"):
                new_status = st.text_input("✏️ عدل الحالة", value=status)
                new_action = st.text_area("✏️ عدل الإجراء", value=action)
                col1, col2, col3 = st.columns(3)
                submitted_save = col1.form_submit_button("💾 حفظ")
                submitted_delete = col2.form_submit_button("🗑️ حذف")
                submitted_archive = col3.form_submit_button("📦 أرشفة")
                if submitted_save:
                    if safe_update(aramex_sheet, f"B{i}", [[new_status]]) and safe_update(aramex_sheet, f"D{i}", [[new_action]]):
                        st.success("✅ تم تعديل الطلب")
                if submitted_delete:
                    if safe_delete(aramex_sheet, i):
                        st.warning("🗑️ تم حذف الطلب")
                if submitted_archive:
                    if safe_append(aramex_archive, [order_id, new_status, date_added, new_action]):
                        if safe_delete(aramex_sheet, i):
                            st.success("♻️ تم أرشفة الطلب")
else:
    st.info("لا توجد شكاوى أرامكس معلقة.")

# ====== عرض أرشيف أرامكس ======
st.markdown("---")
st.header("📦 أرشيف أرامكس:")
aramex_archived = aramex_archive.get_all_values()
if len(aramex_archived) > 1:
    for i, row in enumerate(aramex_archived[1:], start=2):
        while len(row) < 4:
            row.append("")
        order_id = row[0]
        status = row[1]
        date_added = row[2]
        action = row[3]
        with st.expander(f"📦 أرشيف طلب {order_id}"):
            st.write(f"📌 الحالة عند الأرشفة: {status}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            col1, col2 = st.columns(2)
            if col1.button(f"⬅️ إرجاع {order_id} إلى معلق ارامكس"):
                if safe_append(aramex_sheet, [order_id, status, date_added, action]):
                    if safe_delete(aramex_archive, i):
                        st.success(f"✅ تم إعادة {order_id} لمعلق ارامكس")
            if col2.button(f"🗑️ حذف {order_id} من الأرشيف"):
                if safe_delete(aramex_archive, i):
                    st.warning(f"🗑️ تم حذف {order_id} من أرشيف أرامكس")
else:
    st.info("لا توجد شكاوى أرامكس مؤرشفة.")

# ====== تذكير ختامي ======
st.caption("التغييرات تحفظ في Google Sheets عند كل عملية (append/update/delete). استعلامات Aramex تظهر في الواجهة عند وجود أرقام AWB لكنها لا تُخزن تلقائيًا في الشيت إلا إذا ضفت تحديث لحفظها هناك.")
