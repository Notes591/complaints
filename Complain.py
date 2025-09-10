import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheets_dict = {}
for title in ["Complaints", "Responded", "Archive", "Types", "معلق ارامكس", "أرشيف أرامكس"]:
    sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل الأنواع
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== دالة عرض الشكوى مع تعديل النوع ======
def render_complaint(sheet, i, row, in_responded=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
        st.write(f"📌 النوع الحالي: {comp_type}")
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        st.caption(f"📅 تاريخ التسجيل: {date_added}")

        # تعديل النوع
        new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type],
                                index=0, key=f"type_{i}_{sheet.title}")
        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{i}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{i}_{sheet.title}")

        col1, col2, col3, col4 = st.columns(4)

        if col1.button("💾 حفظ", key=f"save_{i}_{sheet.title}"):
            safe_update(sheet, f"B{i}", [[new_type]])  # تحديث النوع
            safe_update(sheet, f"C{i}", [[new_notes]])
            safe_update(sheet, f"D{i}", [[new_action]])
            st.success("✅ تم التعديل")
            st.rerun()

        if col2.button("🗑️ حذف", key=f"delete_{i}_{sheet.title}"):
            safe_delete(sheet, i)
            st.warning("🗑️ تم حذف الشكوى")
            st.rerun()

        if col3.button("📦 أرشفة", key=f"archive_{i}_{sheet.title}"):
            safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored])
            time.sleep(0.5)
            safe_delete(sheet, i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.rerun()

        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{i}"):
                safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للإجراءات المردودة")
                st.rerun()
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{i}"):
                safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored])
                time.sleep(0.5)
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للنشطة")
                st.rerun()

# ====== البحث ======
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

# ====== تسجيل شكوى جديدة ======
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
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            all_active_ids = [str(c["ID"]) for c in complaints] + [str(r["ID"]) for r in responded]
            all_archive_ids = [str(a["ID"]) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                # إرجاع الشكوى من الأرشيف
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes = row[2]
                        restored_action = row[3]
                        restored_type = row[1]
                        if safe_append(complaints_sheet, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة"]):
                            time.sleep(0.5)
                            safe_delete(archive_sheet, idx)
                            st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                            st.rerun()
            else:
                if action.strip():
                    safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, ""])
                    st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, ""])
                    st.success("✅ تم تسجيل الشكوى في النشطة")
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")

# ====== عرض الشكاوى ======
st.header("📋 الشكاوى النشطة:")
active_notes = complaints_sheet.get_all_values()
if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row, in_responded=False)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

st.header("✅ الإجراءات المردودة:")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    for i, row in enumerate(responded_notes[1:], start=2):
        render_complaint(responded_sheet, i, row, in_responded=True)
else:
    st.info("لا توجد شكاوى مردودة حالياً.")

st.header("📦 الأرشيف:")
archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, notes, action, date_added = row[:5]
        restored = row[5] if len(row) > 5 else ""
        with st.expander(f"📦 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
            # عرض النوع في الأرشيف فقط (لا تعديل مباشر هنا)
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
else:
    st.info("لا يوجد شكاوى في الأرشيف.")

# ====== معلق أرامكس ======
st.header("🚚 معلق ارامكس")

with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input("📌 الحالة")
    action = st.text_area("✅ الإجراء المتخذ")
    submitted = st.form_submit_button("➕ إضافة")
    
    if submitted:
        if order_id.strip() and status.strip() and action.strip():
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            safe_append(aramex_sheet, [order_id, status, date_now, action])
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
        with st.expander(f"📦 طلب {order_id}"):
            st.write(f"📌 الحالة الحالية: {status}")
            st.write(f"✅ الإجراء الحالي: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")

            new_status = st.text_input("✏️ عدل الحالة", value=status, key=f"status_{i}")
            new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{i}")

            col1, col2, col3 = st.columns(3)

            if col1.button("💾 حفظ", key=f"save_aramex_{i}"):
                safe_update(aramex_sheet, f"B{i}", [[new_status]])
                safe_update(aramex_sheet, f"D{i}", [[new_action]])
                st.success("✅ تم تعديل الطلب")
                st.rerun()

            if col2.button("🗑️ حذف", key=f"delete_aramex_{i}"):
                safe_delete(aramex_sheet, i)
                st.warning("🗑️ تم حذف الطلب")
                st.rerun()

            if col3.button("📦 أرشفة", key=f"archive_aramex_{i}"):
                safe_append(aramex_archive, [order_id, new_status, date_added, new_action])
                time.sleep(0.5)
                safe_delete(aramex_sheet, i)
                st.success("♻️ الطلب اتنقل لأرشيف أرامكس")
                st.rerun()
else:
    st.info("لا توجد طلبات معلقة حالياً.")
