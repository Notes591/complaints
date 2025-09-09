import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from datetime import datetime
import tempfile

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# أوراق جوجل شيت
SHEET_NAME = "Complaints"
complaints_sheet = client.open(SHEET_NAME).worksheet("Complaints")
archive_sheet = client.open(SHEET_NAME).worksheet("Archive")
types_sheet = client.open(SHEET_NAME).worksheet("Types")

# ====== Google Drive ======
gauth = GoogleAuth()
gauth.credentials = creds
drive = GoogleDrive(gauth)

# ID المجلد اللي هيتخزن فيه الصور
FOLDER_ID = "1vKqFnvsenuzytMhR4cnz4plenAkIY9yw"

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل الأنواع من Google Sheet
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== 1. تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")

with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    action = st.text_area("✅ الإجراء المتخذ")
    uploaded_file = st.file_uploader("📷 ارفع صورة للشكوى", type=["jpg", "jpeg", "png"])

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints = complaints_sheet.get_all_records()
            archive = archive_sheet.get_all_records()
            active_ids = [str(c["ID"]) for c in complaints]
            archived_ids = [str(a["ID"]) for a in archive]

            if comp_id in active_ids:
                st.error("⚠️ رقم الشكوى موجود بالفعل في الشكاوى النشطة")

            else:
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                image_link = ""

                # رفع الصورة لو موجودة
                if uploaded_file:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        tmp_file.write(uploaded_file.getbuffer())
                        file_drive = drive.CreateFile({
                            "title": uploaded_file.name,
                            "parents": [{"id": FOLDER_ID}]
                        })
                        file_drive.SetContentFile(tmp_file.name)
                        file_drive.Upload()
                        file_drive.InsertPermission({
                            "type": "anyone",
                            "value": "anyone",
                            "role": "reader"
                        })
                        image_link = f"https://drive.google.com/uc?id={file_drive['id']}"

                # إضافة الشكوى
                complaints_sheet.append_row([comp_id, comp_type, action, date_now, image_link])
                st.success("✅ تم تسجيل الشكوى")
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")

# ====== 2. عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")

notes = complaints_sheet.get_all_values()
if len(notes) > 1:
    for i, row in enumerate(notes[1:], start=2):
        comp_id, comp_type, action, date_added, image_link = row[:5]

        with st.expander(f"🆔 شكوى رقم {comp_id}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            # عرض الصورة إن وجدت
            if image_link:
                st.image(image_link, caption="📷 صورة الشكوى", use_column_width=True)
                st.markdown(f"[🔗 فتح الصورة في Google Drive]({image_link})")

            new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"act_{i}")
            col1, col2, col3 = st.columns(3)

            if col1.button("💾 حفظ", key=f"save_{i}"):
                complaints_sheet.update(f"C{i}", [[new_action]])
                st.success("✅ تم تعديل الشكوى")
                st.rerun()

            if col2.button("🗑️ حذف", key=f"delete_{i}"):
                complaints_sheet.delete_rows(i)
                st.warning("🗑️ تم حذف الشكوى")
                st.rerun()

            if col3.button("📦 أرشفة", key=f"archive_{i}"):
                archive_sheet.append_row([comp_id, comp_type, new_action, date_added, image_link])
                complaints_sheet.delete_rows(i)
                st.success("♻️ الشكوى انتقلت للأرشيف")
                st.rerun()
else:
    st.info("لا توجد شكاوى حالياً.")

# ====== 3. عرض الأرشيف ======
st.header("📦 الأرشيف (الشكاوى المحلولة):")

archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, action, date_added, image_link = row[:5]
        with st.expander(f"📦 شكوى رقم {comp_id}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
            if image_link:
                st.image(image_link, caption="📷 صورة الشكوى", use_column_width=True)
                st.markdown(f"[🔗 فتح الصورة في Google Drive]({image_link})")
else:
    st.info("لا يوجد شكاوى في الأرشيف.")
