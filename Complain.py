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
types_sheet = client.open(SHEET_NAME).worksheet("Types")  # ورقة لأنواع الشكاوى

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== تحميل الأنواع من الورقة ======
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]  # نتجاهل الهيدر

# ====== إضافة نوع جديد ======
with st.expander("➕ إضافة نوع شكوى جديد"):
    new_type = st.text_input("🆕 اكتب نوع جديد")
    if st.button("إضافة النوع"):
        if new_type.strip() and new_type not in types_list:
            types_sheet.append_row([new_type])
            st.success("✅ تم إضافة النوع الجديد!")
            st.rerun()
        else:
            st.warning("⚠️ النوع موجود بالفعل أو فارغ")

# ====== إضافة شكوى ======
with st.form("add_complaint"):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", types_list)
    action = st.text_area("✅ الإجراء المتخذ")

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted and comp_id.strip():
        # تحقق من التكرار
        complaints = complaints_sheet.get_all_records()
        archive = archive_sheet.get_all_records()

        all_ids = [str(c["ID"]) for c in complaints] + [str(a["ID"]) for a in archive]

        if comp_id in all_ids:
            # لو موجود في الأرشيف → نرجعه للشكاوى النشطة
            for i, row in enumerate(archive, start=2):
                if str(row["ID"]) == comp_id:
                    complaints_sheet.append_row([comp_id, row["نوع الشكوى"], row["الإجراء"], row["التاريخ"]])
                    archive_sheet.delete_rows(i)
                    st.info("♻️ الشكوى موجودة بالأرشيف وتم استرجاعها للشكاوى النشطة")
                    st.rerun()
            st.warning("⚠️ رقم الشكوى موجود بالفعل في الشكاوى الحالية")
        else:
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            complaints_sheet.append_row([comp_id, comp_type, action, date_now])
            st.success("✅ تم تسجيل الشكوى")
            st.rerun()

# ====== عرض الشكاوى ======
st.subheader("📋 الشكاوى النشطة:")

notes = complaints_sheet.get_all_values()

if len(notes) > 1:
    for i, row in enumerate(notes[1:], start=2):
        comp_id = row[0]
        comp_type = row[1]
        action = row[2]
        date_added = row[3]

        with st.expander(f"🆔 شكوى رقم {comp_id}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            # تعديل
            new_type = st.selectbox("📌 نوع الشكوى", types_list, index=types_list.index(comp_type) if comp_type in types_list else 0, key=f"type_{i}")
            new_action = st.text_area("✅ الإجراء المتخذ", value=action, key=f"act_{i}")

            col1, col2, col3 = st.columns(3)

            if col1.button("💾 حفظ", key=f"save_{i}"):
                complaints_sheet.update(f"B{i}:C{i}", [[new_type, new_action]])
                st.success("✅ تم تعديل الشكوى")
                st.rerun()

            if col2.button("🗑️ حذف", key=f"delete_{i}"):
                complaints_sheet.delete_rows(i)
                st.warning("🗑️ تم حذف الشكوى")
                st.rerun()

            if col3.checkbox("✅ تم الحل", key=f"done_{i}"):
                archive_sheet.append_row([comp_id, comp_type, action, date_added])
                complaints_sheet.delete_rows(i)
                st.success("♻️ الشكوى انتقلت للأرشيف")
                st.rerun()
else:
    st.info("لا توجد شكاوى حالياً.")
