# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import streamlit.components.v1 as components


# =====================================================
#             جافاسكربت listener لاستقبال التوقيع
# =====================================================
if "js_listener_added" not in st.session_state:
    st.session_state.js_listener_added = True

    components.html("""
    <script>
    window.addEventListener("message", (event) => {
        if (event.data.type === "save_sig") {
            const key = event.data.key;
            const data = event.data.data;
            const input = window.parent.document.querySelector(`input[id='${key}']`);

            if (input) {
                input.value = data.split(",")[1];     // Base64 بدون header
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
    });
    </script>
    """, height=0)



# =====================================================
#       دالة التوقيع الإلكتروني (HTML + JS)
# =====================================================
def draw_signature(unique_key):
    st.subheader("✍️ التوقيع الإلكتروني")

    canvas_id = f"canvas_{unique_key}"
    hidden_id = f"hidden_{unique_key}"

    html_code = f"""
    <style>
        #{canvas_id} {{
            border: 2px solid black;
            border-radius: 5px;
            touch-action: none;
        }}
    </style>

    <canvas id="{canvas_id}" width="450" height="200"></canvas><br>

    <button onclick="clearCanvas()">مسح</button>
    <button onclick="saveSignature()">حفظ</button>

    <script>

        let canvas = document.getElementById("{canvas_id}");
        let ctx = canvas.getContext("2d");
        let drawing = false;

        canvas.addEventListener("mousedown", () => drawing = true);
        canvas.addEventListener("mouseup", () => drawing = false);
        canvas.addEventListener("mouseout", () => drawing = false);

        canvas.addEventListener("mousemove", function(e) {{
            if (!drawing) return;

            let rect = canvas.getBoundingClientRect();
            ctx.lineWidth = 3;
            ctx.lineCap = "round";
            ctx.strokeStyle = "black";

            ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
        }});

        function clearCanvas() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }}

        function saveSignature() {{
            const dataUrl = canvas.toDataURL("image/png");
            window.parent.postMessage({{
                "type": "save_sig",
                "key": "{hidden_id}",
                "data": dataUrl
            }}, "*");
        }}

    </script>
    <input type="hidden" id="{hidden_id}">
    """

    st.components.v1.html(html_code, height=320)

    # استقبال التوقيع من JS
    signature_b64 = st.text_input("", key=hidden_id, label_visibility="collapsed")

    return signature_b64 if signature_b64 else None



# =====================================================
#                 الاتصال بجوجل شيت
# =====================================================
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



# =====================================================
#              دوال retry للشيت
# =====================================================
def safe_append(sheet, values):
    for _ in range(5):
        try:
            sheet.append_row(values)
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





# =====================================================
#                واجهة المدير الرئيسية
# =====================================================
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


    # قائمة وظائف المدير
    option = st.selectbox("اختر وظيفة:", [
        "🔵 الشكاوى المطلوب اعتمادها",
        "🔑 تغيير كلمة المرور",
        "✍️ التوقيع الإلكتروني"
    ])



    # =====================================================
    #      (1) الشكاوى المطلوبة اعتمادها
    # =====================================================
    if option == "🔵 الشكاوى المطلوب اعتمادها":

        st.header("🔵 الشكاوى المطلوبة اعتمادها")

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

                st.write("✍️ **ارسم التوقيع ثم اضغط حفظ:**")
                signature = draw_signature(comp_id)

                if st.button(f"✔ اعتماد الشكوى {comp_id}", key=f"approve_{comp_id}"):

                    if not signature:
                        st.error("⚠ يجب رسم التوقيع ثم الضغط على حفظ")
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



    # =====================================================
    #      (2) تغيير كلمة المرور
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
                st.error("⚠ كلمة المرور لا يمكن أن تكون فارغة")

            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")



    # =====================================================
    #      (3) تجربة التوقيع
    # =====================================================
    if option == "✍️ التوقيع الإلكتروني":

        st.header("✍️ تجربة رسم التوقيع")

        sig_test = draw_signature("preview")
        if sig_test:
            st.success("✔ تم استقبال التوقيع!")
            st.code(sig_test)



# =====================================================
#                    تشغيل النظام
# =====================================================
if __name__ == "__main__":
    run_admin()
