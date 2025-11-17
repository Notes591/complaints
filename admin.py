# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import base64

# ====== ختم مضمّن (Base64 PNG صغير) ======
# هذا ختم مصغر أسود دائري عليه "APPROVED" و إشارة صح — تم تضمينه داخل الكود
# (ممكن استبداله بأي Base64 آخر، لكن يفضل تتركه كما هو للحماية)
SEAL_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAABaUlEQVR4nO3WsQ3CMAwEwWf//"
    "7u4kY2kq0p0m0kY0bK6r7ufZ1hYAAAAAAAAAAB8G8wN0g0wG3gD9gA9gA9gA9gA9gA9gA9gA9"
    "gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9g"
    "A9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9"
    "gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9"
    "gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9gA9"
    "gA+4Dzc3wGqqqk5XG2QAAAABJRU5ErkJggg=="
)
# (ملاحظة: السلسلة أعلاه هي مثال مختصر/صغير كـ placeholder — استبدلها بBase64 كامل ودقيق للختم الحقيقي عند الحاجة)

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
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


# ====== دوال آمنة للشيت ======
def safe_append(sheet, values, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.append_row(values)
            return True
        except:
            time.sleep(delay)
    return False

def safe_delete(sheet, index, retries=5, delay=1):
    for _ in range(retries):
        try:
            sheet.delete_rows(index)
            return True
        except:
            time.sleep(delay)
    return False


# ====== واجهة الأدمن ======
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
        "🔑 تغيير كلمة المرور"
    ])

    # =====================================================
    # (1) الشكاوى المطلوب اعتمادها — تظهر فقط الشكاوى المطلوبة اعتماد
    # =====================================================
    if option == "🔵 الشكاوى المطلوب اعتمادها":

        st.header("🔵 الشكاوى المطلوب اعتمادها")

        try:
            data = complaints_sheet.get_all_values()
        except Exception:
            st.error("❌ فشل في تحميل بيانات الشكاوى")
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

        for row_index, row in pending:
            comp_id = row[0]
            comp_type = row[1]
            notes = row[2]
            outbound = row[6] if len(row) > 6 else ""
            inbound = row[7] if len(row) > 7 else ""

            with st.expander(f"🆔 {comp_id} | 📌 {comp_type}"):
                st.write(f"📝 الملاحظات: {notes}")
                st.warning("🔵 هذه الشكوى بانتظار الاعتماد")

                # زر الاعتماد — عند الضغط سيكتب صف جديد مع ختم مضمّن (SEAL_B64)
                if st.button(f"✔ اعتماد الشكوى {comp_id}", key=f"approve_{comp_id}"):

                    # صف جديد مع الختم المضمّن في العمود الأخير
                    updated_row = [
                        comp_id,
                        comp_type,
                        notes,
                        "✔ تم اعتماد المدير",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "",
                        outbound,
                        inbound,
                        SEAL_B64
                    ]

                    ok = safe_append(complaints_sheet, updated_row)
                    if ok:
                        # نحذف السطر القديم
                        safe_delete(complaints_sheet, row_index)
                        st.success(f"✔ تم اعتماد الشكوى {comp_id} وختمها.")
                        st.experimental_rerun()
                    else:
                        st.error("❌ فشل في اعتماد الشكوى — حاول مرة أخرى")

    # =====================================================
    # (2) تغيير كلمة المرور
    # =====================================================
    if option == "🔑 تغيير كلمة المرور":

        st.header("🔑 تغيير كلمة المرور")

        current_pw = st.text_input("كلمة المرور الحالية", type="password")
        new_pw = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")

        if st.button("💾 حفظ كلمة المرور"):
            if current_pw != st.session_state.admin_password:
                st.error("❌ كلمة المرور الحالية غير صحيحة")
            elif new_pw != confirm_pw:
                st.error("⚠ كلمة المرور الجديدة غير متطابقة")
            elif new_pw.strip() == "":
                st.error("⚠ لا يمكن ترك كلمة المرور فارغة")
            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")


# ===== تشغيل الادمن =====
if __name__ == "__main__":
    run_admin()
