# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import numpy as np
from PIL import Image
import io
import base64
from streamlit_drawable_canvas import st_canvas
from gspread.exceptions import APIError

# ====== إعداد الصفحة ======
st.set_page_config(page_title="🔐 قسم المدير - نظام الشكاوى", page_icon="⚙️", layout="wide")
st.title("🔐 قسم المدير - اعتماد الشكاوى")

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "Complaints"

# نحاول الوصول فقط لورقة PendingApproval لتقليل الطلبات
try:
    ss = client.open(SHEET_NAME)
    pending_approval_sheet = ss.worksheet("PendingApproval")
except Exception as e:
    st.error(f"❌ خطأ في الوصول إلى ورقة PendingApproval: {e}")
    st.stop()

# ====== دوال الحفظ الآمن ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except APIError:
            time.sleep(delay)
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except APIError:
            time.sleep(delay)
    return False

# ====== تسجيل الدخول ======
DEFAULT_ADMIN_PASS = st.secrets.get("admin_pass", "Admin123")

if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False

if not st.session_state["admin_logged_in"]:
    admin_pass_input = st.text_input("🔑 أدخل كلمة مرور المدير:", type="password")
    if st.button("تسجيل دخول"):
        if admin_pass_input == DEFAULT_ADMIN_PASS:
            st.session_state["admin_logged_in"] = True
            st.success("✅ تم تسجيل الدخول بنجاح")
            st.experimental_rerun()
        else:
            st.error("❌ كلمة المرور غير صحيحة")
    st.stop()

st.success("✅ المدير مسجل دخول")

if st.button("🚪 تسجيل خروج"):
    st.session_state["admin_logged_in"] = False
    st.experimental_rerun()

# ====== تحميل بيانات الشكاوى المعلقة ======
@st.cache_data(ttl=60)
def get_pending_data():
    try:
        return pending_approval_sheet.get_all_values()
    except Exception:
        return []

pending_data_raw = get_pending_data()

if not pending_data_raw or len(pending_data_raw) <= 1:
    st.info("لا توجد شكاوى في انتظار الاعتماد حالياً.")
    st.stop()

st.markdown("---")
st.subheader("📋 الشكاوى في انتظار الاعتماد")

for idx, row in enumerate(pending_data_raw, start=1):
    if not any(row):
        continue
    while len(row) < 10:
        row.append("")

    comp_id = row[0]
    comp_type = row[1]
    notes = row[2]
    action = row[3]
    date_added = row[4]
    restored = row[5]
    outbound_awb = row[6]
    inbound_awb = row[7]
    source_sheet = row[8] if len(row) > 8 and row[8].strip() else "Complaints"
    sent_time = row[9] if len(row) > 9 else ""

    with st.expander(f"📌 {comp_id} | {comp_type} | من: {source_sheet}"):
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        st.caption(f"📅 تاريخ الإرسال: {sent_time or date_added}")

        st.write("✍️ توقيع المدير (يمكن الرسم بالماوس أو اللمس):")
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

        signer_text = st.text_input(f"أو توقيع نصي - {comp_id}", key=f"sign_text_{comp_id}")

        signer_image_str = ""
        if canvas_result.image_data is not None:
            try:
                img = Image.fromarray(np.uint8(canvas_result.image_data))
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                signer_image_str = base64.b64encode(buffered.getvalue()).decode()
                st.image(img, caption="✅ معاينة التوقيع", width=200)
            except Exception as e:
                st.error(f"خطأ في معالجة التوقيع: {e}")

        col1, col2 = st.columns(2)
        if col1.button(f"✅ اعتماد - {comp_id}"):
            if not signer_text.strip() and not signer_image_str:
                st.warning("⚠️ أضف توقيع المدير أولاً.")
            else:
                approval_note = f"{action}\n\n✅ تم الاعتماد بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                if signer_text.strip():
                    approval_note += f" | اعتمد بواسطة: {signer_text}"
                if signer_image_str:
                    approval_note += " | توقيع المدير محفوظ كصورة Base64"

                target_sheet = ss.worksheet(source_sheet)
                row_to_return = [
                    comp_id, comp_type, notes, approval_note,
                    date_added, "✅ معتمدة", outbound_awb, inbound_awb, signer_image_str
                ]
                if safe_append(target_sheet, row_to_return):
                    all_pending = pending_approval_sheet.get_all_values()
                    for p_i, p_row in enumerate(all_pending, start=1):
                        if len(p_row) > 0 and str(p_row[0]) == str(comp_id):
                            safe_delete(pending_approval_sheet, p_i)
                            st.success(f"✅ تم اعتماد الشكوى {comp_id} وإعادتها إلى {source_sheet}")
                            st.cache_data.clear()
                            st.experimental_rerun()

        if col2.button(f"❌ رفض - {comp_id}"):
            target_sheet = ss.worksheet(source_sheet)
            row_to_return = [comp_id, comp_type, notes, action, date_added, restored, outbound_awb, inbound_awb]
            if safe_append(target_sheet, row_to_return):
                all_pending = pending_approval_sheet.get_all_values()
                for p_i, p_row in enumerate(all_pending, start=1):
                    if len(p_row) > 0 and str(p_row[0]) == str(comp_id):
                        safe_delete(pending_approval_sheet, p_i)
                        st.info(f"ℹ️ تم رفض الشكوى {comp_id} وإعادتها إلى {source_sheet}")
                        st.cache_data.clear()
                        st.experimental_rerun()
