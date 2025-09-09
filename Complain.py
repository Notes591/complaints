import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from datetime import datetime

# ====== إعداد Google Sheets ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "Complaints"
sheet = client.open(SHEET_NAME).sheet1

# ====== إعداد Google Drive API ======
drive_service = build("drive", "v3", credentials=creds)

# ضع هنا Folder ID بتاع Google Drive
FOLDER_ID = "1vKqFnvsenuzytMhR4cnz4plenAkIY9yw"

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== إضافة شكوى ======
with st.form("add_complaint"):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.text_input("📌 نوع الشكوى")
    action = st.text_area("✅ الإجراء المتخذ")
    file = st.file_uploader("📎 ارفق صورة / ملف", type=["png", "jpg", "jpeg", "pdf"])

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted and comp_id.strip():
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_link = ""

        # رفع الملف لو موجود
        if file is not None:
            file_metadata = {
                "name": file.name,
                "parents": [FOLDER_ID]
            }
            media = MediaIoBaseUpload(io.BytesIO(file.getbuffer()), mimetype=file.type, resumable=True)
            uploaded_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()

            file_link = f"https://drive.google.com/file/d/{uploaded_file.get('id')}/view"

        # تسجيل البيانات في Google Sheet
        sheet.append_row([comp_id, comp_type, action, date_now, file_link])
        st.success("✅ تم تسجيل الشكوى")

# ====== عرض الشكاوى ======
st.subheader("📋 كل الشكاوى:")

rows = sheet.get_all_values()

if len(rows) > 1:
    for i, row in enumerate(rows[1:], start=2):
        comp_id, comp_type, action, date_added, file_link = row + [""] * (5 - len(row))

        with st.expander(f"🆔 شكوى رقم {comp_id}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            if file_link:
                st.markdown(f"📎 [رابط المرفق]({file_link})")
else:
    st.info("لا توجد شكاوى حتى الآن.")
