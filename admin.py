# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
from datetime import datetime
import time
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import io


# =======================================
#   Google Sheet اتصال
# =======================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("Complaints")
try:
    complaints = sheet.worksheet("Complaints")
except:
    complaints = sheet.add_worksheet("Complaints", rows="2000", cols="20")


# =======================================
#   دالة توقيع بسيطة وثابتة
# =======================================
def signature_pad(key_id):

    st.subheader("✍️ التوقيع الإلكتروني")

    if "sig" not in st.session_state:
        st.session_state.sig = {}

    if key_id not in st.session_state.sig:
        st.session_state.sig[key_id] = None

    result = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#FFFFFF",
        height=200,
        width=450,
        drawing_mode="freedraw",
        key=f"canvas_{key_id}",
        update_streamlit=False              # ← يمنع الريفرش
    )

    if result.image_data is not None:
        img = Image.fromarray(result.image_data.astype("uint8"), "RGBA")
        img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        st.session_state.sig[key_id] = base64.b64encode(buffer.getvalue()).decode()

    return st.session_state.sig[key_id]


# =======================================
#     لوحة تحكم المدير
# =======================================
def run():

    st.title("👑 لوحة تحكم المدير")

    # تسجيل الدخول
    pw = st.text_input("كلمة المرور:", type="password")
    if pw != "1234":
        st.stop()

    st.success("✔ تم تسجيل الدخول")
    st.write("---")

    st.header("🔵 الشكاوى المطلوب اعتمادها")

    data = complaints.get_all_values()
    if len(data) <= 1:
        st.info("لا توجد شكاوى مطلوبة اعتماد.")
        st.stop()

    for i, row in enumerate(data[1:], start=2):

        if len(row) < 9:
            row += [""] * (9 - len(row))

        comp_id, comp_type, notes, status = row[0], row[1], row[2], row[3]

        if status != "🔵 بانتظار اعتماد المدير":
            continue

        with st.expander(f"🆔 {comp_id} | {comp_type}"):

            st.write(f"📝 الملاحظات: {notes}")
            st.warning("🔵 هذه الشكوى بانتظار الاعتماد")

            sig = signature_pad(comp_id)

            if st.button(f"✔ اعتماد الشكوى {comp_id}", key=f"appr_{comp_id}"):

                if not sig:
                    st.error("⚠ يجب رسم التوقيع")
                    st.stop()

                new_row = [
                    comp_id,
                    comp_type,
                    notes,
                    "✔ تم اعتماد المدير",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "",
                    row[6], row[7],
                    sig
                ]

                complaints.append_row(new_row)
                complaints.delete_rows(i)
                st.success("✔ تم الاعتماد")
                st.experimental_rerun()


if __name__ == "__main__":
    run()
