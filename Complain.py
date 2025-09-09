import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# ====== إعداد Google Sheets ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Sheets
SHEET_COMPLAINTS = "Complaints"    # الشكاوى الحالية
SHEET_ARCHIVE = "Complaints_Archive"  # الأرشيف
SHEET_TYPES = "Complaint_Types"   # جدول أنواع الشكاوى

sheet = client.open(SHEET_COMPLAINTS).sheet1
archive_sheet = client.open(SHEET_ARCHIVE).sheet1
types_sheet = client.open(SHEET_TYPES).sheet1

# ====== إعداد Google Drive ======
drive_service = build("drive", "v3", credentials=creds)
FOLDER_ID = "1vKqFnvsenuzytMhR4cnz4plenAkIY9yw"  # فولدر جوجل درايف


# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")


# ====== دالة رفع الملفات إلى Drive ======
def upload_to_drive(file):
    file_metadata = {"name": file.name, "parents": [FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=file.type)
    uploaded = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    file_id = uploaded.get("id")
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


# ====== دالة البحث ======
def search_complaint(comp_id):
    complaints = sheet.get_all_values()[1:]
    archive = archive_sheet.get_all_values()[1:]

    for i, row in enumerate(complaints, start=2):
        if row[0] == comp_id:
            return row, i, "current"
    for i, row in enumerate(archive, start=2):
        if row[0] == comp_id:
            return row, i, "archive"
    return None, None, None


# ====== إضافة شكوى ======
st.subheader("➕ تسجيل شكوى جديدة")

types = [t[0] for t in types_sheet.get_all_values()[1:]]  # الأنواع من الشيت
with st.form("add_complaint"):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", [""] + types)
    action = st.text_area("✅ الإجراء المتخذ")
    uploaded_file = st.file_uploader("📎 إرفاق صورة/ملف", type=["png", "jpg", "jpeg", "pdf"])

    submitted = st.form_submit_button("إضافة")
    if submitted:
        if not comp_id.strip():
            st.error("❌ رقم الشكوى مطلوب")
        else:
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_url = upload_to_drive(uploaded_file) if uploaded_file else ""

            sheet.append_row([comp_id, comp_type, action, date_now, file_url])
            st.success("✅ تم تسجيل الشكوى")
            st.rerun()


# ====== البحث ======
st.subheader("🔍 بحث عن شكوى")
search_id = st.text_input("ادخل رقم الشكوى")

if st.button("بحث") and search_id:
    row, idx, location = search_complaint(search_id)
    if row:
        st.info(f"📋 الشكوى موجودة في: {'الأرشيف' if location=='archive' else 'الشكاوى الجارية'}")

        comp_id, comp_type, action, date_added, file_url = row[:5]

        st.write(f"### 🆔 {comp_id}")
        st.write(f"📌 النوع: {comp_type}")
        st.write(f"✅ الإجراء: {action}")
        st.write(f"📅 التاريخ: {date_added}")
        if file_url:
            st.markdown(f"[📎 الملف المرفق]({file_url})")

        # تعديل / حذف / نقل بين الأرشيف والجاري
        new_type = st.selectbox("📌 نوع الشكوى", types, index=types.index(comp_type) if comp_type in types else 0)
        new_action = st.text_area("✅ الإجراء المتخذ", value=action)

        col1, col2, col3 = st.columns(3)

        if col1.button("💾 حفظ التعديلات"):
            if location == "current":
                sheet.update(f"B{idx}:C{idx}", [[new_type, new_action]])
            else:
                archive_sheet.update(f"B{idx}:C{idx}", [[new_type, new_action]])
            st.success("✅ تم التعديل")
            st.rerun()

        if col2.button("🗑️ حذف"):
            if location == "current":
                sheet.delete_rows(idx)
            else:
                archive_sheet.delete_rows(idx)
            st.warning("🗑️ تم الحذف")
            st.rerun()

        if col3.button("📂 نقل"):
            if location == "current":
                archive_sheet.append_row(row)
                sheet.delete_rows(idx)
                st.success("📦 تم النقل إلى الأرشيف")
            else:
                sheet.append_row(row + ["🔄 مسترجعة من الأرشيف"])
                archive_sheet.delete_rows(idx)
                st.success("♻️ تم الاسترجاع من الأرشيف")
            st.rerun()
    else:
        st.error("❌ لا يوجد شكوى بهذا الرقم")
