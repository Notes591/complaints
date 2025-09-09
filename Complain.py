import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import tempfile
from datetime import datetime

# ====== إعداد Google Sheets ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "Complaints"
sheet = client.open(SHEET_NAME).sheet1

# ====== إعداد Google Drive ======
gauth = GoogleAuth()
gauth.credentials = creds
drive = GoogleDrive(gauth)

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
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(file.getbuffer())
                tmp_file_path = tmp_file.name

            gfile = drive.CreateFile({
                "parents": [{"id": FOLDER_ID}],
                "title": file.name
            })
            gfile.SetContentFile(tmp_file_path)
            gfile.Upload()

            # رابط الملف بعد الرفع
            file_link = f"https://drive.google.com/file/d/{gfile['id']}/view"

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
