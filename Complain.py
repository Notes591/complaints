import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Google Drive API
drive_service = build("drive", "v3", credentials=creds)

# ID الفولدر اللي هيتخزن فيه الصور
FOLDER_ID = "1vKqFnvsenuzytMhR4cnz4plenAkIY9yw"

# أوراق جوجل شيت
SHEET_NAME = "Complaints"
complaints_sheet = client.open(SHEET_NAME).worksheet("Complaints")
archive_sheet = client.open(SHEET_NAME).worksheet("Archive")
types_sheet = client.open(SHEET_NAME).worksheet("Types")

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل الأنواع
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== 1. البحث ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("🆔 اكتب رقم الشكوى")

if st.button("🔍 بحث"):
    if search_id.strip():
        complaints = complaints_sheet.get_all_values()
        archive = archive_sheet.get_all_values()
        found = False

        # بحث في الشكاوى النشطة
        for i, row in enumerate(complaints[1:], start=2):
            if row[0] == search_id:
                found = True
                with st.expander(f"🆔 شكوى رقم {row[0]}"):
                    comp_id, comp_type, action, date_added = row[:4]
                    restored = row[4] if len(row) > 4 else ""
                    image_url = row[5] if len(row) > 5 else ""

                    st.write(f"📌 النوع: {comp_type}")
                    st.write(f"✅ الإجراء: {action}")
                    st.caption(f"📅 تاريخ التسجيل: {date_added}")
                    if image_url:
                        st.image(image_url, caption="📷 صورة الشكوى", width=300)

                    new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"search_act_{i}")
                    col1, col2, col3 = st.columns(3)

                    if col1.button("💾 حفظ", key=f"search_save_{i}"):
                        complaints_sheet.update(f"C{i}", [[new_action]])
                        st.success("✅ تم تعديل الشكوى")
                        st.rerun()

                    if col2.button("🗑️ حذف", key=f"search_del_{i}"):
                        complaints_sheet.delete_rows(i)
                        st.warning("🗑️ تم حذف الشكوى")
                        st.rerun()

                    if col3.button("📦 أرشفة", key=f"search_arc_{i}"):
                        archive_sheet.append_row([comp_id, comp_type, new_action, date_added, restored, image_url])
                        complaints_sheet.delete_rows(i)
                        st.success("♻️ الشكوى اتنقلت للأرشيف")
                        st.rerun()

        # بحث في الأرشيف
        for i, row in enumerate(archive[1:], start=2):
            if row[0] == search_id:
                found = True
                with st.expander(f"📦 شكوى رقم {row[0]} (في الأرشيف)"):
                    comp_id, comp_type, action, date_added = row[:4]
                    restored = row[4] if len(row) > 4 else ""
                    image_url = row[5] if len(row) > 5 else ""

                    st.write(f"📌 النوع: {comp_type}")
                    st.write(f"✅ الإجراء: {action}")
                    st.caption(f"📅 تاريخ التسجيل: {date_added}")
                    if image_url:
                        st.image(image_url, caption="📷 صورة الشكوى", width=300)

                    if st.button("♻️ استرجاع", key=f"search_restore_{i}"):
                        complaints_sheet.append_row([comp_id, comp_type, action, date_added, "🔄 مسترجعة", image_url])
                        archive_sheet.delete_rows(i)
                        st.success("✅ تم استرجاع الشكوى")
                        st.rerun()

        if not found:
            st.error("❌ لم يتم العثور على الشكوى")

# ====== 2. تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")

with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    action = st.text_area("✅ الإجراء المتخذ")
    uploaded_file = st.file_uploader("📷 إرفاق صورة", type=["png", "jpg", "jpeg"])

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints = complaints_sheet.get_all_records()
            archive = archive_sheet.get_all_records()
            active_ids = [str(c["ID"]) for c in complaints]
            archived_ids = [str(a["ID"]) for a in archive]
            image_url = ""

            # لو فيه صورة مرفوعة نرفعها عالدرايف
            if uploaded_file is not None:
                file_stream = io.BytesIO(uploaded_file.read())
                file_metadata = {"name": uploaded_file.name, "parents": [FOLDER_ID]}
                media = MediaIoBaseUpload(file_stream, mimetype=uploaded_file.type, resumable=True)
                file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
                file_id = file.get("id")
                drive_service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
                image_url = f"https://drive.google.com/uc?id={file_id}"

            if comp_id in active_ids:
                st.error("⚠️ رقم الشكوى موجود بالفعل في الشكاوى النشطة")

            elif comp_id in archived_ids:
                # استرجاع من الأرشيف
                for i, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if row[0] == comp_id:
                        archive_sheet.delete_rows(i)
                        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        complaints_sheet.append_row([comp_id, comp_type, action, date_now, "🔄 مسترجعة", image_url])
                        st.success("✅ تم استرجاع الشكوى من الأرشيف وإعادة تفعيلها")
                        st.rerun()
            else:
                # إضافة جديدة
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                complaints_sheet.append_row([comp_id, comp_type, action, date_now, "", image_url])
                st.success("✅ تم تسجيل الشكوى")
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")

# ====== 3. عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")

notes = complaints_sheet.get_all_values()
if len(notes) > 1:
    for i, row in enumerate(notes[1:], start=2):
        comp_id, comp_type, action, date_added = row[:4]
        restored = row[4] if len(row) > 4 else ""
        image_url = row[5] if len(row) > 5 else ""

        with st.expander(f"🆔 شكوى رقم {comp_id} {restored}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
            if image_url:
                st.image(image_url, caption="📷 صورة الشكوى", width=300)

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
                archive_sheet.append_row([comp_id, comp_type, new_action, date_added, restored, image_url])
                complaints_sheet.delete_rows(i)
                st.success("♻️ الشكوى انتقلت للأرشيف")
                st.rerun()
else:
    st.info("لا توجد شكاوى حالياً.")

# ====== 4. عرض الأرشيف ======
st.header("📦 الأرشيف (الشكاوى المحلولة):")

archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, action, date_added = row[:4]
        restored = row[4] if len(row) > 4 else ""
        image_url = row[5] if len(row) > 5 else ""

        with st.expander(f"📦 شكوى رقم {comp_id} {restored}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
            if image_url:
                st.image(image_url, caption="📷 صورة الشكوى", width=300)
else:
    st.info("لا يوجد شكاوى في الأرشيف.")
