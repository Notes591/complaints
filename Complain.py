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
SHEET_NAME = "Complaints"   # اسم الشيت الجديد
sheet = client.open(SHEET_NAME).sheet1

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== إضافة شكوى ======
with st.form("add_complaint"):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.text_input("📌 نوع الشكوى")
    action = st.text_area("✅ الإجراء المتخذ")

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted and (comp_id.strip() or comp_type.strip() or action.strip()):
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([comp_id, comp_type, action, date_now])
        st.success("✅ تم تسجيل الشكوى")
        st.rerun()

# ====== عرض الشكاوى ======
st.subheader("📋 كل الشكاوى:")

notes = sheet.get_all_values()

if len(notes) > 1:  # فيه بيانات
    for i, row in enumerate(notes[1:], start=2):  # تجاهل الهيدر
        comp_id = row[0] if len(row) > 0 else ""
        comp_type = row[1] if len(row) > 1 else ""
        action = row[2] if len(row) > 2 else ""
        date_added = row[3] if len(row) > 3 else ""

        with st.expander(f"🆔 شكوى رقم {comp_id}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            # خانات التعديل
            new_id = st.text_input("🆔 رقم الشكوى", value=comp_id, key=f"id_{i}")
            new_type = st.text_input("📌 نوع الشكوى", value=comp_type, key=f"type_{i}")
            new_action = st.text_area("✅ الإجراء المتخذ", value=action, key=f"act_{i}")

            col1, col2 = st.columns(2)

            if col1.button("💾 حفظ التعديلات", key=f"save_{i}"):
                # نخلي التاريخ زي ما هو (مش بيتعدل)
                sheet.update(f"A{i}:C{i}", [[new_id, new_type, new_action]])
                st.success("✅ تم الحفظ")
                st.rerun()

            if col2.button("🗑️ حذف", key=f"delete_{i}"):
                sheet.delete_rows(i)
                st.warning("🗑️ تم الحذف")
                st.rerun()
else:
    st.info("لا توجد شكاوى حتى الآن.")
