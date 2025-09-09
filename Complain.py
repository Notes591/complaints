import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# اسم الشيت
SHEET_NAME = "Complaints"
complaints_sheet = client.open(SHEET_NAME).worksheet("Complaints")
archive_sheet = client.open(SHEET_NAME).worksheet("Archive")
types_sheet = client.open(SHEET_NAME).worksheet("Types")

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل الأنواع من الورقة
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# 🟡 متغير لتخزين IDs اللي رجعت من الأرشيف
if "restored_ids" not in st.session_state:
    st.session_state.restored_ids = []

# ====== 1. البحث ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("🆔 اكتب رقم الشكوى")
if st.button("🔍 بحث"):
    if search_id.strip():
        complaints = complaints_sheet.get_all_records()
        archive = archive_sheet.get_all_records()
        found = False

        for row in complaints:
            if str(row["ID"]) == search_id:
                st.success(f"✅ تم العثور على الشكوى في **الشكاوى النشطة**")
                st.write(row)
                found = True

        for row in archive:
            if str(row["ID"]) == search_id:
                st.info(f"📦 تم العثور على الشكوى في **الأرشيف**")
                st.write(row)
                found = True

        if not found:
            st.error("❌ لم يتم العثور على الشكوى")

# ====== 2. إضافة نوع جديد ======
with st.expander("➕ إضافة نوع شكوى جديد"):
    new_type = st.text_input("🆕 اكتب نوع جديد")
    if st.button("إضافة النوع"):
        if new_type.strip() and new_type not in types_list:
            types_sheet.append_row([new_type])
            st.success("✅ تم إضافة النوع الجديد!")
            st.rerun()
        else:
            st.warning("⚠️ النوع موجود بالفعل أو فارغ")

# ====== 3. تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")

# session_state لمسح الحقول
if "comp_id" not in st.session_state:
    st.session_state.comp_id = ""
if "comp_type" not in st.session_state:
    st.session_state.comp_type = "اختر نوع الشكوى..."
if "action" not in st.session_state:
    st.session_state.action = ""

with st.form("add_complaint"):
    comp_id = st.text_input("🆔 رقم الشكوى", value=st.session_state.comp_id, key="comp_id")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list,
                             index=0 if st.session_state.comp_type == "اختر نوع الشكوى..." else types_list.index(st.session_state.comp_type)+1,
                             key="comp_type")
    action = st.text_area("✅ الإجراء المتخذ", value=st.session_state.action, key="action")

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints = complaints_sheet.get_all_records()
            archive = archive_sheet.get_all_records()
            all_ids = [str(c["ID"]) for c in complaints] + [str(a["ID"]) for a in archive]

            if comp_id in all_ids:
                # لو موجود في الأرشيف → نرجعه للشكاوى النشطة
                for i, row in enumerate(archive, start=2):
                    if str(row["ID"]) == comp_id:
                        complaints_sheet.append_row([row["ID"], row["نوع الشكوى"], row["الإجراء"], row["التاريخ"], "🔄 مسترجعة من الأرشيف"])
                        archive_sheet.delete_rows(i)
                        st.session_state.restored_ids.append(comp_id)
                        st.success("♻️ الشكوى استرجعت من الأرشيف")
                        st.rerun()
                st.error("⚠️ رقم الشكوى موجود بالفعل في الشكاوى الحالية")
            else:
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                complaints_sheet.append_row([comp_id, comp_type, action, date_now, ""])
                st.success("✅ تم تسجيل الشكوى")

                st.session_state.comp_id = ""
                st.session_state.comp_type = "اختر نوع الشكوى..."
                st.session_state.action = ""
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")

# ====== 4. عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")

notes = complaints_sheet.get_all_values()
if len(notes) > 1:
    for i, row in enumerate(notes[1:], start=2):
        comp_id = row[0]
        comp_type = row[1]
        action = row[2]
        date_added = row[3]
        restored = row[4] if len(row) > 4 else ""

        with st.expander(f"🆔 شكوى رقم {comp_id} {restored}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

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

            if col3.checkbox("✅ تم الحل", key=f"done_{i}"):
                archive_sheet.append_row([comp_id, comp_type, new_action, date_added])
                complaints_sheet.delete_rows(i)
                st.success("♻️ الشكوى انتقلت للأرشيف")
                st.rerun()
else:
    st.info("لا توجد شكاوى حالياً.")

# ====== 5. عرض الأرشيف ======
st.header("📦 الأرشيف (الشكاوى المحلولة):")

archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, action, date_added = row
        with st.expander(f"📦 شكوى رقم {comp_id}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
else:
    st.info("لا يوجد شكاوى في الأرشيف.")
