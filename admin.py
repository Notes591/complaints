# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import io
import base64
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# ====== إعداد الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق الشيت ======
SHEET_NAME = "Complaints"
sheet = client.open(SHEET_NAME)

try:
    complaints_sheet = sheet.worksheet("Complaints")
except Exception:
    complaints_sheet = sheet.add_worksheet(title="Complaints", rows="1000", cols="20")

# ====== دوال مساعدة ======
def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

# ====== قراءة كلمة مرور المدير من Streamlit Secrets ======
admin_password = st.secrets["admin"]["password"]

# ====== دالة رسم التوقيع الإلكتروني ======
def draw_signature():
    st.subheader("✍️ التوقيع الإلكتروني")
    st.write("قم برسم توقيعك داخل المربع أدناه:")

    canvas = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#FFFFFF",
        width=500,
        height=200,
        drawing_mode="freedraw",
        key="canvas_signature",
    )

    if canvas.image_data is not None:
        img = Image.fromarray(canvas.image_data.astype("uint8"))
        st.image(img, caption="التوقيع الذي تم رسمه")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        signature_base64 = base64.b64encode(buffered.getvalue()).decode()
        return signature_base64
    return None

# ====== واجهة المدير ======
st.title("👑 لوحة تحكم المدير")

# --- تسجيل الدخول ---
password = st.text_input("🔐 ادخل كلمة المرور", type="password")
if not password:
    st.info("ادخل كلمة المرور للدخول")
    st.stop()
elif password != admin_password:
    st.error("❌ كلمة المرور غير صحيحة")
    st.stop()
else:
    st.success("✔ تم تسجيل الدخول بنجاح")

# --- اختيار وظيفة المدير ---
option = st.selectbox("اختر وظيفة:", [
    "اعتماد شكوى",
    "رفض شكوى",
    "عرض الشكاوى",
    "تغيير كلمة المرور"
])

# ====== اعتماد الشكوى ======
if option == "اعتماد شكوى":
    st.header("✔ اعتماد شكوى")
    comp_id = st.text_input("أدخل رقم الشكوى لاعتمادها")
    signature_img = draw_signature()
    if st.button("اعتماد الشكوى"):
        if not comp_id:
            st.error("⚠️ ادخل رقم الشكوى")
        elif signature_img is None:
            st.error("⚠️ يجب رسم التوقيع أولاً")
        else:
            data = complaints_sheet.get_all_values()
            for i, row in enumerate(data[1:], start=2):
                if row[0] == comp_id:
                    safe_update(complaints_sheet, f"E{i}", [[f"✔ تم اعتمادها {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]])
                    safe_update(complaints_sheet, f"F{i}", [[signature_img]])
                    st.success(f"✅ تم اعتماد الشكوى {comp_id}")
                    st.experimental_rerun()
                    break
            else:
                st.error("⚠️ لم يتم العثور على الشكوى")

# ====== رفض الشكوى ======
elif option == "رفض شكوى":
    st.header("❌ رفض شكوى")
    comp_id = st.text_input("أدخل رقم الشكوى لرفضها")
    signature_img = draw_signature()
    if st.button("رفض الشكوى"):
        if not comp_id:
            st.error("⚠️ ادخل رقم الشكوى")
        elif signature_img is None:
            st.error("⚠️ يجب رسم التوقيع أولاً")
        else:
            data = complaints_sheet.get_all_values()
            for i, row in enumerate(data[1:], start=2):
                if row[0] == comp_id:
                    safe_update(complaints_sheet, f"E{i}", [[f"❌ تم رفضها {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]])
                    safe_update(complaints_sheet, f"F{i}", [[signature_img]])
                    st.success(f"✅ تم رفض الشكوى {comp_id}")
                    st.experimental_rerun()
                    break
            else:
                st.error("⚠️ لم يتم العثور على الشكوى")

# ====== عرض الشكاوى ======
elif option == "عرض الشكاوى":
    st.header("📋 الشكاوى")
    data = complaints_sheet.get_all_values()
    if len(data) > 1:
        for row in data[1:]:
            while len(row) < 6:
                row.append("")
            comp_id, comp_type, notes, action, status, signature = row[:6]
            st.info(f"🆔 {comp_id} | 📌 {comp_type} | {status}")
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            if signature:
                st.image(Image.open(io.BytesIO(base64.b64decode(signature))), caption="التوقيع")
    else:
        st.info("لا توجد شكاوى حالياً")

# ====== تغيير كلمة المرور ======
elif option == "تغيير كلمة المرور":
    st.header("🔑 تغيير كلمة المرور")
    current_pw = st.text_input("كلمة المرور الحالية", type="password")
    new_pw = st.text_input("كلمة المرور الجديدة", type="password")
    confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
    if st.button("تغيير كلمة المرور"):
        if current_pw != admin_password:
            st.error("⚠ كلمة المرور الحالية غير صحيحة")
        elif new_pw != confirm_pw:
            st.error("⚠ كلمة المرور الجديدة لا تتطابق")
        else:
            st.success("✔ كلمة المرور الجديدة جاهزة للتطبيق")
            st.info("⚠️ لتطبيق التغيير عدل كلمة المرور في Streamlit Secrets يدويًا")
