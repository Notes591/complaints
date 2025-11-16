# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import io
import base64
from PIL import Image
from streamlit_drawable_canvas import st_canvas
import time

# ====== إعدادات الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق الشيت ======
SHEET_NAME = "Complaints"
try:
    sheet = client.open(SHEET_NAME)
except Exception as e:
    st.error(f"❌ خطأ في فتح الشيت: {e}")
    st.stop()

try:
    complaints_sheet = sheet.worksheet("Complaints")
except Exception:
    complaints_sheet = sheet.add_worksheet(title="Complaints", rows="1000", cols="20")

# ====== دوال مساعدة ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== دالة رسم التوقيع الإلكتروني ======
def draw_signature():
    st.subheader("✍️ التوقيع الإلكتروني للمدير")
    st.write("قم برسم توقيعك داخل المربع أدناه:")

    canvas = st_canvas(
        fill_color="rgba(0, 0, 0, 0)",
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

        st.success("✔ تم إنشاء التوقيع بنجاح")
        return signature_base64
    return None

# ====== النظام الرئيسي للمدير ======
def run_admin_system():
    st.title("👑 لوحة تحكم المدير")

    # --- تسجيل الدخول ---
    st.subheader("🔐 تسجيل الدخول كمدير")
    password = st.text_input("ادخل كلمة المرور", type="password")
    admin_password = "1234"  # يمكنك تعديلها هنا

    if password == "":
        st.info("من فضلك ادخل كلمة المرور للدخول.")
        return

    if password != admin_password:
        st.error("❌ كلمة المرور غير صحيحة")
        return

    st.success("✔ تم تسجيل الدخول بنجاح")
    st.write("---")

    # --- اختيار وظيفة المدير ---
    option = st.selectbox("اختر وظيفة:", [
        "عرض الشكاوى",
        "اعتماد شكوى",
        "رفض شكوى",
        "إدارة كلمات المرور",
        "التوقيع الإلكتروني"
    ])

    # ====== عرض الشكاوى ======
    if option == "عرض الشكاوى":
        st.header("📋 الشكاوى النشطة")
        data = complaints_sheet.get_all_values()
        if len(data) > 1:
            for i, row in enumerate(data[1:], start=2):
                while len(row) < 4:
                    row.append("")
                comp_id, comp_type, notes, action = row[:4]
                st.info(f"🆔 {comp_id} | 📌 {comp_type}")
                st.write(f"📝 الملاحظات: {notes}")
                st.write(f"✅ الإجراء: {action}")
        else:
            st.info("لا توجد شكاوى حالياً.")

    # ====== اعتماد الشكوى ======
    elif option == "اعتماد شكوى":
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
                        updated_row = row[:]
                        updated_row.append(f"✔ تم اعتمادها بواسطة المدير {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        updated_row.append(signature_img)
                        safe_append(complaints_sheet, updated_row)
                        safe_delete(complaints_sheet, i)
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
                        updated_row = row[:]
                        updated_row.append(f"❌ تم رفضها بواسطة المدير {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        updated_row.append(signature_img)
                        safe_append(complaints_sheet, updated_row)
                        safe_delete(complaints_sheet, i)
                        st.success(f"✅ تم رفض الشكوى {comp_id}")
                        st.experimental_rerun()
                        break
                else:
                    st.error("⚠️ لم يتم العثور على الشكوى")

    # ====== إدارة كلمات المرور ======
    elif option == "إدارة كلمات المرور":
        st.header("🔑 إدارة كلمة المرور")
        current_pw = st.text_input("كلمة المرور الحالية", type="password")
        new_pw = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
        if st.button("تغيير كلمة المرور"):
            if current_pw != admin_password:
                st.error("⚠ كلمة المرور الحالية غير صحيحة")
            elif new_pw != confirm_pw:
                st.error("⚠ كلمة المرور الجديدة لا تتطابق")
            else:
                admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")

    # ====== التوقيع الإلكتروني فقط ======
    elif option == "التوقيع الإلكتروني":
        st.header("✍️ توقيع المدير")
        signature_img = draw_signature()
        if signature_img:
            st.write("🔽 هذا هو التوقيع بصيغة Base64:")
            st.code(signature_img)
            st.info("يمكنك نسخ هذا الكود أو حفظه في Google Sheet كما تريد.")
