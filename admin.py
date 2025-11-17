# -*- coding: utf-8 -*-
import streamlit as st
import gspread
import base64
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io

# ===========================================
#        GOOGLE SHEET CONNECT
# ===========================================
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


# ===========================================
# SAFE SHEET FUNCTIONS
# ===========================================
def safe_append(sheet, values):
    for _ in range(4):
        try:
            sheet.append_row(values)
            return True
        except:
            time.sleep(1)
    return False

def safe_delete(sheet, index):
    for _ in range(4):
        try:
            sheet.delete_rows(index)
            return True
        except:
            time.sleep(1)
    return False


# ===========================================
# SIGNATURE CANVAS  (NO REFRESH / PIL ONLY)
# ===========================================
def draw_signature(unique_key):
    st.subheader("✍️ التوقيع الإلكتروني")
    
    canvas_key = f"sig_{unique_key}"

    # session state to avoid REFRESH issues
    if canvas_key not in st.session_state:
        st.session_state[canvas_key] = None

    canvas = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#FFFFFF",
        width=450,
        height=200,
        drawing_mode="freedraw",
        key=canvas_key,
        update_streamlit=False   # ← يمنع أي Refresh
    )

    if canvas.image_data is not None:
        img = Image.fromarray(canvas.image_data.astype("uint8"), "RGBA")
        img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        b64 = base64.b64encode(img_bytes).decode()

        st.session_state[canvas_key] = b64

    return st.session_state[canvas_key]


# ===========================================
#                ADMIN PANEL
# ===========================================
def run_admin():

    st.title("👑 لوحة تحكم المدير")

    # ------------------ LOGIN --------------------
    with st.form("login_form"):
        st.subheader("🔐 تسجيل الدخول")
        password = st.text_input("كلمة المرور:", type="password")
        login = st.form_submit_button("دخول")

    if login:
        if "admin_password" not in st.session_state:
            st.session_state.admin_password = "1234"

        if password != st.session_state.admin_password:
            st.error("❌ كلمة المرور خاطئة")
            st.stop()
        else:
            st.session_state.logged = True

    if "logged" not in st.session_state:
        st.info("الرجاء تسجيل الدخول…")
        return

    st.success("✔ تم تسجيل الدخول")
    st.write("---")

    option = st.selectbox("اختر:", [
        "🔵 الشكاوى المطلوب اعتمادها",
        "✍️ تجربة التوقيع",
        "🔑 تغيير كلمة المرور"
    ])

    # ===========================================
    #          شكاوى تحتاج اعتماد
    # ===========================================
    if option == "🔵 الشكاوى المطلوب اعتمادها":

        st.header("📂 الشكاوى بانتظار الاعتماد")

        try:
            data = complaints_sheet.get_all_values()
        except:
            st.error("❌ لا يمكن تحميل البيانات")
            return

        pending = []

        for i, row in enumerate(data[1:], start=2):
            while len(row) < 9:
                row.append("")

            if row[3] == "🔵 بانتظار اعتماد المدير":
                pending.append((i, row))

        if not pending:
            st.info("لا توجد شكاوى مطلوبة اعتماد.")
            return

        for row_index, row in pending:
            cid = row[0]
            ctype = row[1]
            note = row[2]
            outbound = row[6]
            inbound = row[7]

            with st.expander(f"🆔 {cid} | {ctype}"):

                st.write(f"📝 الملاحظات: {note}")
                st.warning("🔵 مطلوب اعتماد المدير")

                st.write("✍️ ارسم التوقيع:")

                signature = draw_signature(cid)

                with st.form(f"approve_{cid}"):
                    submit = st.form_submit_button(f"✔ اعتماد الشكوى {cid}")

                    if submit:
                        if not signature:
                            st.error("⚠ ارسم التوقيع أولًا")
                            st.stop()

                        new_row = [
                            cid,
                            ctype,
                            note,
                            "✔ تم اعتماد المدير",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "",
                            outbound,
                            inbound,
                            signature
                        ]

                        safe_append(complaints_sheet, new_row)
                        safe_delete(complaints_sheet, row_index)

                        st.success(f"✔ تم اعتماد الشكوى {cid}")
                        st.experimental_rerun()

    # ===========================================
    #         TEST SIGNATURE
    # ===========================================
    if option == "✍️ تجربة التوقيع":

        st.header("✍️ تجربة التوقيع")
        sig = draw_signature("test")

        if sig:
            st.success("✔ تم التقاط التوقيع!")
            st.image(base64.b64decode(sig))


    # ===========================================
    #          تغيير كلمة المرور
    # ===========================================
    if option == "🔑 تغيير كلمة المرور":

        st.header("🔑 تغيير كلمة المرور")

        with st.form("pw_change"):
            old = st.text_input("كلمة المرور الحالية:", type="password")
            new = st.text_input("كلمة المرور الجديدة:", type="password")
            cnew = st.text_input("تأكيد كلمة المرور:", type="password")

            save = st.form_submit_button("حفظ")

            if save:
                if old != st.session_state.admin_password:
                    st.error("❌ كلمة المرور الحالية غير صحيحة")
                elif new != cnew:
                    st.error("⚠ غير متطابقة")
                elif new.strip() == "":
                    st.error("⚠ غير صالحة")
                else:
                    st.session_state.admin_password = new
                    st.success("✔ تم تغيير كلمة المرور")


# ===========================================
# RUN
# ===========================================
if __name__ == "__main__":
    run_admin()
