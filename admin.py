# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time


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



# ====== دالة التوقيع (HTML + JS تعمل على Streamlit Cloud 100%) ======
def draw_signature(unique_key):
    st.subheader("✍️ التوقيع الإلكتروني")

    canvas_id = f"canvas_{unique_key}"

    html_code = f"""
    <style>
    #{canvas_id} {{
        border: 2px solid #000;
        border-radius: 5px;
        touch-action: none;
    }}
    </style>

    <canvas id="{canvas_id}" width="450" height="200"></canvas><br>

    <button onclick="clearCanvas_{unique_key}()">مسح</button>
    <button onclick="saveCanvas_{unique_key}()">حفظ</button>

    <script>
    const canvas_{unique_key} = document.getElementById("{canvas_id}");
    const ctx_{unique_key} = canvas_{unique_key}.getContext("2d");
    let drawing_{unique_key} = false;

    canvas_{unique_key}.addEventListener("mousedown", () => drawing_{unique_key} = true);
    canvas_{unique_key}.addEventListener("mouseup", () => drawing_{unique_key} = false);
    canvas_{unique_key}.addEventListener("mouseout", () => drawing_{unique_key} = false);

    canvas_{unique_key}.addEventListener("mousemove", function(e) {{
        if (!drawing_{unique_key}) return;
        const rect = canvas_{unique_key}.getBoundingClientRect();
        ctx_{unique_key}.lineWidth = 3;
        ctx_{unique_key}.lineCap = "round";
        ctx_{unique_key}.strokeStyle = "black";
        ctx_{unique_key}.lineTo(e.clientX - rect.left, e.clientY - rect.top);
        ctx_{unique_key}.stroke();
        ctx_{unique_key}.beginPath();
        ctx_{unique_key}.moveTo(e.clientX - rect.left, e.clientY - rect.top);
    }});

    function clearCanvas_{unique_key}() {{
        ctx_{unique_key}.clearRect(0, 0, canvas_{unique_key}.width, canvas_{unique_key}.height);
    }}

    function saveCanvas_{unique_key}() {{
        const dataURL = canvas_{unique_key}.toDataURL("image/png");
        const input = window.parent.document.getElementById("{canvas_id}_data");
        input.value = dataURL;
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
    }}
    </script>

    <input type="hidden" id="{canvas_id}_data" name="{canvas_id}_data">
    """

    st.components.v1.html(html_code, height=330)

    data_input = st.text_input("", key=f"{canvas_id}_data", label_visibility="collapsed")

    if data_input and "base64" in data_input:
        return data_input.split(",")[1]

    return None



# =========================================================
# واجهة المدير
# =========================================================
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


    # ======================================================
    # (1) الشكاوى المطلوب اعتمادها
    # ======================================================
    if option == "🔵 الشكاوى المطلوب اعتمادها":

        st.header("🔵 الشكاوى المطلوب اعتمادها")

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



    # ======================================================
    # (2) تغيير كلمة المرور
    # ======================================================
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
                st.error("⚠ كلمة المرور لا يمكن أن تكون فارغة")

            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")



    # ======================================================
    # (3) صفحة اختبار التوقيع
    # ======================================================
    if option == "✍️ التوقيع الإلكتروني":

        st.header("✍️ تجربة رسم التوقيع")

        sig_test = draw_signature("preview")

        if sig_test:
            st.success("✔ تم إنشاء التوقيع")
            st.code(sig_test)



# ===== تشغيل النظام =====
if __name__ == "__main__":
    run_admin()
