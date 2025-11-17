# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
from streamlit_signature_pad import st_signature_pad


# ====== الاتصال بجوجل شيت ======
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

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
def safe_update(sheet, cell, value):
    for _ in range(5):
        try:
            sheet.update(cell, value)
            return True
        except:
            time.sleep(1)
    return False


def safe_delete(sheet, index):
    for _ in range(5):
        try:
            sheet.delete_rows(index)
            return True
        except:
            time.sleep(1)
    return False


def safe_append(sheet, values):
    for _ in range(5):
        try:
            sheet.append_row(values)
            return True
        except:
            time.sleep(1)
    return False


# ===== التوقيع الإلكتروني باستخدام streamlit-signature-pad =====
def draw_signature(unique_key):
    st.subheader("✍️ التوقيع الإلكتروني")

    signature_data = st_signature_pad(
        key=f"sig_{unique_key}",
        height=200,
        pen_color="black",
        background_color="white"
    )

    if signature_data:
        # signature_data = "data:image/png;base64,xxxxxx"
        sig_b64 = signature_data.split(",")[1]   # إزالة header
        return sig_b64

    return None



# ========== واجهة المدير ==========
def run_admin():

    st.title("👑 لوحة تحكم المدير")

    # ---- تسجيل الدخول ----
    st.subheader("🔐 تسجيل الدخول")
    password = st.text_input("ادخل كلمة المرور", type="password")

    if "admin_password" not in st.session_state:
        st.session_state.admin_password = "1234"

    if password == "":
        st.info("من فضلك ادخل كلمة المرور.")
        return

    if password != st.session_state.admin_password:
        st.error("❌ كلمة المرور غير صحيحة")
        return

    st.success("✔ تم تسجيل الدخول")
    st.write("---")

    option = st.selectbox("اختر وظيفة:", [
        "🔵 الشكاوى المطلوب اعتمادها",
        "🔑 تغيير كلمة المرور",
        "✍️ التوقيع الإلكتروني"
    ])

    # -----------------------------------------------------------
    # (1) الشكاوى المطلوب اعتمادها
    # -----------------------------------------------------------
    if option == "🔵 الشكاوى المطلوب اعتمادها":

        st.header("🔵 الشكاوى المطلوب اعتمادها")

        # قراءة الشيت مرة واحدة فقط
        try:
            data = complaints_sheet.get_all_values()
        except Exception:
            st.error("❌ فشل في تحميل البيانات من الشيت")
            return

        if len(data) <= 1:
            st.info("لا توجد شكاوى مطلوبة اعتماد.")
            return

        pending = []
        for i, row in enumerate(data[1:], start=2):
            while len(row) < 9:
                row.append("")

            if row[3].strip() == "🔵 بانتظار اعتماد المدير":
                pending.append((i, row))

        if not pending:
            st.info("لا توجد شكاوى عليها طلب اعتماد.")
            return

        # عرض كل شكوى مطلوبة اعتماد
        for row_index, row in pending:

            comp_id = row[0]
            comp_type = row[1]
            notes = row[2]
            outbound = row[6]
            inbound = row[7]

            with st.expander(f"🆔 {comp_id} | 📌 {comp_type}"):

                st.write(f"📝 الملاحظات: {notes}")
                st.warning("🔵 هذه الشكوى بانتظار الاعتماد")

                st.write("✍️ **ارسم التوقيع بالأسفل:**")
                signature = draw_signature(comp_id)

                if st.button(f"✔ اعتماد الشكوى {comp_id}", key=f"approve_{comp_id}"):

                    if not signature:
                        st.error("⚠ يجب رسم التوقيع أولاً.")
                        st.stop()

                    updated_row = [
                        comp_id,
                        comp_type,
                        notes,
                        "✔ تم اعتماد المدير",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "",
                        outbound,
                        inbound,
                        signature
                    ]

                    safe_append(complaints_sheet, updated_row)
                    safe_delete(complaints_sheet, row_index)

                    st.success(f"✔ تم اعتماد الشكوى {comp_id}")
                    st.experimental_rerun()



    # -----------------------------------------------------------
    # (2) تغيير كلمة المرور
    # -----------------------------------------------------------
    if option == "🔑 تغيير كلمة المرور":

        st.header("🔑 تغيير كلمة المرور")

        current_pw = st.text_input("كلمة المرور الحالية", type="password")
        new_pw = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")

        if st.button("💾 حفظ كلمة المرور"):

            if current_pw != st.session_state.admin_password:
                st.error("❌ كلمة المرور الحالية غير صحيحة")

            elif new_pw != confirm_pw:
                st.error("⚠ كلمة المرور لا تتطابق")

            elif new_pw.strip() == "":
                st.error("⚠ كلمة المرور لا يمكن أن تكون فارغة")

            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")



    # -----------------------------------------------------------
    # (3) صفحة التجربة (لا يتم حفظ التوقيع)
    # -----------------------------------------------------------
    if option == "✍️ التوقيع الإلكتروني":

        st.header("✍️ تجربة التوقيع الإلكتروني")

        signature_preview = draw_signature("preview")

        if signature_preview:
            st.success("✔ تم إنشاء التوقيع")
            st.code(signature_preview)



# ===== تشغيل النظام =====
if __name__ == "__main__":
    run_admin()
