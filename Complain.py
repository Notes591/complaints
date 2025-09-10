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

# أوراق جوجل شيت
SHEET_NAME = "Complaints"
complaints_sheet = client.open(SHEET_NAME).worksheet("Complaints")
responded_sheet = client.open(SHEET_NAME).worksheet("Responded")
archive_sheet = client.open(SHEET_NAME).worksheet("Archive")
types_sheet = client.open(SHEET_NAME).worksheet("Types")
aramex_sheet = client.open(SHEET_NAME).worksheet("معلق ارامكس")
aramex_archive = client.open(SHEET_NAME).worksheet("أرشيف أرامكس")

# ====== واجهة التطبيق ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل الأنواع
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== دالة عرض الشكوى ======
def render_complaint(sheet, i, row, in_responded=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""

    with st.expander(f"🆔 شكوى {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
        st.write(f"📌 النوع: {comp_type}")
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        st.caption(f"📅 تاريخ التسجيل: {date_added}")

        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{i}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{i}_{sheet.title}")

        col1, col2, col3, col4 = st.columns(4)

        # حفظ التعديلات
        if col1.button("💾 حفظ", key=f"save_{i}_{sheet.title}"):
            sheet.update(f"C{i}", [[new_notes]])
            sheet.update(f"D{i}", [[new_action]])
            st.success("✅ تم التعديل")
            st.rerun()

        # حذف الشكوى
        if col2.button("🗑️ حذف", key=f"delete_{i}_{sheet.title}"):
            sheet.delete_rows(i)
            st.warning("🗑️ تم حذف الشكوى")
            st.rerun()

        # أرشفة الشكوى
        if col3.button("📦 أرشفة", key=f"archive_{i}_{sheet.title}"):
            archive_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
            sheet.delete_rows(i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.rerun()

        # أزرار النقل دائمًا ظاهرة
        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{i}"):
                responded_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
                sheet.delete_rows(i)
                st.success("✅ اتنقلت لقائمة الإجراءات المردودة")
                st.rerun()
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{i}"):
                complaints_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
                sheet.delete_rows(i)
                st.success("✅ اتنقلت تاني لقائمة النشطة")
                st.rerun()

# ====== 1. البحث ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("🆔 اكتب رقم الشكوى")

if st.button("🔍 بحث"):
    if search_id.strip():
        found = False
        for sheet in [complaints_sheet, responded_sheet, archive_sheet]:
            data = sheet.get_all_values()
            for i, row in enumerate(data[1:], start=2):
                if row[0] == search_id:
                    found = True
                    render_complaint(sheet, i, row, in_responded=(sheet==responded_sheet))
        if not found:
            st.error("❌ لم يتم العثور على الشكوى")

# ====== 2. تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")

with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    notes = st.text_area("📝 ملاحظات الشكوى")
    action = st.text_area("✅ الإجراء المتخذ")

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints = complaints_sheet.get_all_records()
            responded = responded_sheet.get_all_records()
            archive = archive_sheet.get_all_records()

            all_ids = [str(c["ID"]) for c in complaints] + \
                      [str(r["ID"]) for r in responded] + \
                      [str(a["ID"]) for a in archive]

            if comp_id in all_ids:
                st.error("⚠️ رقم الشكوى موجود بالفعل")
            else:
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if action.strip():
                    responded_sheet.append_row([comp_id, comp_type, notes, action, date_now, ""])
                    st.success("✅ تم تسجيل الشكوى في الإجراءات المردودة")
                else:
                    complaints_sheet.append_row([comp_id, comp_type, notes, "", date_now, ""])
                    st.success("✅ تم تسجيل الشكوى في النشطة")
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")

# ====== 3. عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة (بدون إجراء):")
active_notes = complaints_sheet.get_all_values()
if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row, in_responded=False)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== 4. عرض الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة:")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    for i, row in enumerate(responded_notes[1:], start=2):
        render_complaint(responded_sheet, i, row, in_responded=True)
else:
    st.info("لا توجد شكاوى مردودة حالياً.")

# ====== 5. عرض الأرشيف ======
st.header("📦 الأرشيف (الشكاوى المحلولة):")
archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, notes, action, date_added = row[:5]
        restored = row[5] if len(row) > 5 else ""
        with st.expander(f"📦 شكوى {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
else:
    st.info("لا يوجد شكاوى في الأرشيف.")

# ====== 6. معلق ارامكس ======
st.header("🚚 معلق ارامكس")
with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input("📌 الحالة")
    action = st.text_area("✅ الإجراء المتخذ")
    submitted = st.form_submit_button("➕ إضافة")
    
    if submitted:
        if order_id.strip() and status.strip() and action.strip():
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            aramex_sheet.append_row([order_id, status, date_now, action])
            st.success("✅ تم تسجيل الطلب")
            st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

# عرض الطلبات المعلقة
st.subheader("📋 قائمة الطلبات المعلقة")
aramex_data = aramex_sheet.get_all_values()
if len(aramex_data) > 1:
    for i, row in enumerate(aramex_data[1:], start=2):
        order_id, status, date_added, action = row[:4]
        with st.expander(f"📦 طلب {order_id} | 📌 {status} | 📅 {date_added}"):
            st.write(f"📌 الحالة الحالية: {status}")
            st.write(f"✅ الإجراء الحالي: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            
            new_status = st.text_input("✏️ عدل الحالة", value=status, key=f"status_{i}")
            new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{i}")
            
            col1, col2, col3 = st.columns(3)
            
            if col1.button("💾 حفظ", key=f"save_aramex_{i}"):
                aramex_sheet.update(f"B{i}", [[new_status]])
                aramex_sheet.update(f"D{i}", [[new_action]])
                st.success("✅ تم تعديل الطلب")
                st.rerun()
            
            if col2.button("🗑️ حذف", key=f"delete_aramex_{i}"):
                aramex_sheet.delete_rows(i)
                st.warning("🗑️ تم حذف الطلب")
                st.rerun()
            
            if col3.button("📦 أرشفة", key=f"archive_aramex_{i}"):
                aramex_archive.append_row([order_id, new_status, date_added, new_action])
                aramex_sheet.delete_rows(i)
                st.success("♻️ الطلب اتنقل لأرشيف أرامكس")
                st.rerun()
else:
    st.info("لا توجد طلبات معلقة حالياً.")
