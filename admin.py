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

# ====== الاتصال بجوجل شيت ======
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
    complaints_sheet = sheet.add_worksheet(title="Complaints", rows="2000", cols="20")


# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False


# ====== دالة التوقيع الإلكتروني — تعمل 100% ======
def draw_signature():
    st.subheader("✍️ التوقيع الإلكتروني")

    canvas = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#FFFFFF",
        width=500,
        height=200,
        drawing_mode="freedraw",
        key=f"sig_{time.time()}",  # مفتاح فريد دائماً
    )

    if canvas.image_data is not None:
        img = Image.fromarray(canvas.image_data.astype("uint8"))
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        sig_b64 = base64.b64encode(buffered.getvalue()).decode()
        return sig_b64

    return None
# ====== واجهة المدير ======

def run_admin():

    st.title("👑 لوحة تحكم المدير")

    # ----- تسجيل دخول -----
    st.subheader("🔐 تسجيل الدخول")
    password = st.text_input("ادخل كلمة المرور", type="password")

    if "admin_password" not in st.session_state:
        st.session_state.admin_password = "1234"  # كلمة مرور افتراضية

    if password == "":
        st.info("من فضلك ادخل كلمة المرور للدخول.")
        return

    if password != st.session_state.admin_password:
        st.error("❌ كلمة المرور غير صحيحة")
        return

    st.success("✔ تم تسجيل الدخول")
    st.write("---")

    option = st.selectbox("اختر وظيفة:", [
        "🔵 الشكاوى المطلوبة اعتماد",
        "🔑 تغيير كلمة المرور",
        "✍️ التوقيع الإلكتروني"
    ])

    # ---------------------------------------------------------
    # (1) الشكاوى المطلوب اعتمادها فقط
    # ---------------------------------------------------------
    if option == "🔵 الشكاوى المطلوبة اعتماد":

        st.header("🔵 الشكاوى المطلوب اعتمادها الآن")

        data = complaints_sheet.get_all_values()

        if len(data) <= 1:
            st.info("لا توجد شكاوى مطلوبة اعتماد.")
            return

        found_any = False

        for i, row in enumerate(data[1:], start=2):

            # تأمين طول الصف
            while len(row) < 9:
                row.append("")

            comp_id = row[0]
            comp_type = row[1]
            notes = row[2]
            action = row[3]
            outbound = row[6]
            inbound = row[7]
            old_signature = row[8]

            # نعرض فقط الشكاوى التي عليها "🔵 بانتظار اعتماد المدير"
            if action.strip() == "🔵 بانتظار اعتماد المدير":

                found_any = True

                with st.expander(f"🆔 {comp_id} | 📌 {comp_type}"):

                    st.write(f"📝 الملاحظات: {notes}")
                    st.warning("🔵 هذه الشكوى بانتظار اعتماد المدير")

                    st.write("✍️ **ارسم التوقيع بالأسفل:**")
                    signature_img = draw_signature()

                    if st.button(f"✔ اعتماد الشكوى {comp_id}", key=f"approve_{comp_id}"):

                        if not signature_img:
                            st.error("⚠ يجب رسم التوقيع قبل الاعتماد")
                            st.stop()

                        # ===== إنشاء الصف الجديد بعد الاعتماد =====
                        updated_row = [
                            comp_id,           # ID
                            comp_type,         # نوع الشكوى
                            notes,             # ملاحظات
                            "✔ تم اعتماد المدير",  # حالة الإجراء بعد الاعتماد
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # التاريخ
                            "",                # Restored
                            outbound,          # Outbound
                            inbound,           # Inbound
                            signature_img      # التوقيع الإلكتروني
                        ]

                        # إضافة الصف الجديد
                        safe_append(complaints_sheet, updated_row)
                        # حذف الصف القديم
                        safe_delete(complaints_sheet, i)

                        st.success(f"✔ تم اعتماد الشكوى رقم {comp_id}")
                        st.experimental_rerun()

        if not found_any:
            st.info("لا توجد شكاوى عليها طلب اعتماد.")
    # ---------------------------------------------------------
    # (2) تغيير كلمة المرور
    # ---------------------------------------------------------
    if option == "🔑 تغيير كلمة المرور":

        st.header("🔑 تغيير كلمة المرور")

        current_pw = st.text_input("كلمة المرور الحالية", type="password")
        new_pw = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")

        if st.button("💾 تغيير كلمة المرور"):

            if current_pw != st.session_state.admin_password:
                st.error("❌ كلمة المرور الحالية غير صحيحة")

            elif new_pw != confirm_pw:
                st.error("⚠ كلمة المرور الجديدة غير متطابقة")

            elif new_pw.strip() == "":
                st.error("⚠ كلمة المرور الجديدة لا يمكن أن تكون فارغة")

            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")


    # ---------------------------------------------------------
    # (3) صفحة التوقيع الإلكتروني (عرض فقط)
    # ---------------------------------------------------------
    if option == "✍️ التوقيع الإلكتروني":

        st.header("✍️ إنشاء / اختبار التوقيع الإلكتروني")

        st.write("يمكنك رسم التوقيع بالأسفل — هذا للتجربة فقط، لا يتم حفظه هنا.")

        signature_img = draw_signature()

        if signature_img:
            st.success("✔ تم إنشاء التوقيع بنجاح")
            st.code(signature_img, language="text")


# ====== تشغيل النظام ======
if __name__ == "__main__":
    run_admin()
