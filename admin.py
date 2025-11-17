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

# إنشاء / جلب الورقة
try:
    complaints_sheet = sheet.worksheet("Complaints")
except Exception:
    complaints_sheet = sheet.add_worksheet(title="Complaints", rows="2000", cols="20")


# ====== دوال المزامنة ======
def safe_append(sheet, row_data, retries=4, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد محاولات.")
    return False

def safe_delete(sheet, row_index, retries=4, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except:
            time.sleep(delay)
    st.error("❌ فشل delete_rows.")
    return False


# ====== دالة رسم التوقيع الإلكتروني ======
def draw_signature():
    st.subheader("✍️ التوقيع الإلكتروني للمدير")
    canvas = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#FFFFFF",
        width=500,
        height=200,
        drawing_mode="freedraw",
        key="admin_sig",
    )

    if canvas.image_data is not None:
        img = Image.fromarray(canvas.image_data.astype("uint8"))
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        sig_base64 = base64.b64encode(buffered.getvalue()).decode()
        st.success("✔ تم إنشاء التوقيع")
        return sig_base64

    return None
# ====== واجهة المدير ======
def run_admin():

    st.title("👑 لوحة تحكم المدير")

    # --- تسجيل الدخول ---
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
        "الشكاوى المطلوبة اعتماد",
        "تغيير كلمة المرور",
        "التوقيع الإلكتروني"
    ])

    # ---------------------------------------------------------
    # 1) الشكاوى التي تم الضغط لها على زر (🔵 طلب اعتماد)
    # ---------------------------------------------------------
    if option == "الشكاوى المطلوبة اعتماد":

        st.header("🔵 الشكاوى المطلوبة اعتماد")

        data = complaints_sheet.get_all_values()

        if len(data) <= 1:
            st.info("لا توجد شكاوى مطلوبة اعتماد حالياً.")
            return

        found_any = False

        for i, row in enumerate(data[1:], start=2):

            # التأكد من وجود عمود الإجراء
            while len(row) < 4:
                row.append("")

            comp_id = row[0]
            comp_type = row[1]
            notes = row[2]
            action = row[3]

            # نعرض فقط الشكاوى التي كتب فيها (🔵 بانتظار اعتماد المدير)
            if action.strip() == "🔵 بانتظار اعتماد المدير":
                found_any = True

                with st.expander(f"🆔 {comp_id} | 📌 {comp_type}"):

                    st.write(f"📝 الملاحظات: {notes}")
                    st.warning("🔵 هذه الشكوى بانتظار الاعتماد")

                    signature_img = draw_signature()

                    if st.button(f"✔ اعتماد الشكوى {comp_id}"):

                        if not signature_img:
                            st.error("⚠ يجب رسم التوقيع أولاً.")
                            st.stop()

                        # إعادة كتابة السطر مع حفظ التوقيع
                        updated_row = [
                            comp_id,
                            comp_type,
                            notes,
                            "✔ تم اعتماد المدير",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "", "", "", signature_img
                        ]

                        safe_append(complaints_sheet, updated_row)
                        safe_delete(complaints_sheet, i)

                        st.success(f"✔ تم اعتماد الشكوى {comp_id}")
                        st.stop()

        if not found_any:
            st.info("لا توجد شكاوى عليها طلب اعتماد.")
    # ---------------------------------------------------------
    # 2) تغيير كلمة المرور
    # ---------------------------------------------------------
    if option == "تغيير كلمة المرور":

        st.header("🔑 تغيير كلمة المرور")

        current_pw = st.text_input("كلمة المرور الحالية", type="password")
        new_pw = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")

        if st.button("💾 تغيير"):

            if current_pw != st.session_state.admin_password:
                st.error("❌ كلمة المرور الحالية غير صحيحة")

            elif new_pw != confirm_pw:
                st.error("⚠ كلمة المرور الجديدة غير متطابقة")

            elif new_pw.strip() == "":
                st.error("⚠ لا يمكن ترك كلمة المرور فارغة")

            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")


    # ---------------------------------------------------------
    # 3) التوقيع الإلكتروني (عرض التوقيع فقط)
    # ---------------------------------------------------------
    if option == "التوقيع الإلكتروني":

        st.header("✍️ إنشاء / اختبار التوقيع الإلكتروني")

        st.write("يمكنك رسم توقيعك بالأسفل وسيتم تحويله مباشرة إلى Base64")

        signature_img = draw_signature()

        if signature_img:
            st.code(signature_img)
            st.info("✔ هذا هو التوقيع بصيغة Base64، يتم استخدامه عند اعتماد الشكاوى.")
# ====== تشغيل النظام ======
if __name__ == "__main__":
    run_admin()
