import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import webbrowser

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"

def open_sheet(title):
    for _ in range(5):
        try:
            return client.open(SHEET_NAME).worksheet(title)
        except gspread.exceptions.APIError:
            time.sleep(1)
    st.error(f"❌ فشل فتح ورقة {title}")
    st.stop()

complaints_sheet = open_sheet("Complaints")
responded_sheet = open_sheet("Responded")
archive_sheet = open_sheet("Archive")
types_sheet = open_sheet("Types")
aramex_sheet = open_sheet("معلق ارامكس")
aramex_archive = open_sheet("أرشيف أرامكس")

# ====== صفحة Streamlit ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️")
st.title("⚠️ نظام إدارة الشكاوى")

# تحميل أنواع الشكاوى
types_list = [row[0] for row in types_sheet.get_all_values()[1:]]

# ====== دوال آمنة للتعامل مع Google Sheets ======
def safe_append(sheet, row_data):
    for _ in range(5):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(1)
    st.error("❌ فشل append_row بعد عدة محاولات")
    return False

def safe_update(sheet, cell_range, values):
    for _ in range(5):
        try:
            sheet.update(cell_range, values)
            return True
        except gspread.exceptions.APIError:
            time.sleep(1)
    st.error("❌ فشل update بعد عدة محاولات")
    return False

def safe_delete(sheet, row_index):
    for _ in range(5):
        try:
            sheet.delete_rows(row_index)
            return True
        except gspread.exceptions.APIError:
            time.sleep(1)
    st.error("❌ فشل delete_rows بعد عدة محاولات")
    return False

# ====== دالة عرض الشكوى مع أزرار النقل + زر الفاتورة ======
def render_complaint(sheet, i, row, in_responded=False):
    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""

    # توليد الرابط دائمًا
    invoice_link = f"https://homelamasat.com/wp-admin/admin-ajax.php?action=generate_wpo_wcpdf&document_type=invoice&bulk&_wpnonce=eb55186c83&order_ids={comp_id}"

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored}"):
        st.write(f"📌 النوع: {comp_type}")
        st.write(f"📝 الملاحظات: {notes}")
        st.write(f"✅ الإجراء: {action}")
        st.caption(f"📅 تاريخ التسجيل: {date_added}")

        # زر واضح لفتح الفاتورة
        if st.button("📄 فتح الفاتورة", key=f"invoice_{i}_{sheet.title}"):
            st.write(f"[اضغط هنا لفتح الفاتورة]({invoice_link})")

        new_notes = st.text_area("✏️ عدل الملاحظات", value=notes, key=f"notes_{i}_{sheet.title}")
        new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{i}_{sheet.title}")

        col1, col2, col3, col4 = st.columns(4)

        if col1.button("💾 حفظ", key=f"save_{i}_{sheet.title}"):
            safe_update(sheet, f"C{i}", [[new_notes]])
            safe_update(sheet, f"D{i}", [[new_action]])
            st.success("✅ تم التعديل")
            st.rerun()

        if col2.button("🗑️ حذف", key=f"delete_{i}_{sheet.title}"):
            safe_delete(sheet, i)
            st.warning("🗑️ تم حذف الشكوى")
            st.rerun()

        if col3.button("📦 أرشفة", key=f"archive_{i}_{sheet.title}"):
            safe_append(archive_sheet, [comp_id, comp_type, new_notes, new_action, date_added, restored, invoice_link])
            safe_delete(sheet, i)
            st.success("♻️ الشكوى انتقلت للأرشيف")
            st.rerun()

        if not in_responded:
            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{i}"):
                safe_append(responded_sheet, [comp_id, comp_type, new_notes, new_action, date_added, restored, invoice_link])
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للإجراءات المردودة")
                st.rerun()
        else:
            if col4.button("⬅️ رجوع للنشطة", key=f"to_active_{i}"):
                safe_append(complaints_sheet, [comp_id, comp_type, new_notes, new_action, date_added, restored, invoice_link])
                safe_delete(sheet, i)
                st.success("✅ اتنقلت للنشطة")
                st.rerun()

# ====== البحث عن شكوى ======
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
    submitted = st.form_submit_button("➕ إضافة")

    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints = complaints_sheet.get_all_records()
            responded = responded_sheet.get_all_records()
            archive = archive_sheet.get_all_records()
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            invoice_link = f"https://homelamasat.com/wp-admin/admin-ajax.php?action=generate_wpo_wcpdf&document_type=invoice&bulk&_wpnonce=eb55186c83&order_ids={comp_id}"

            all_active_ids = [str(c["ID"]) for c in complaints] + [str(r["ID"]) for r in responded]
            all_archive_ids = [str(a["ID"]) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                # استرجاع من الأرشيف
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes = row[2]
                        restored_action = row[3]
                        restored_invoice = row[6] if len(row) > 6 else invoice_link
                        safe_append(complaints_sheet, [comp_id, comp_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_invoice])
                        safe_delete(archive_sheet, idx)
                        st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                        st.rerun()
            else:
                if action.strip():
                    safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", invoice_link])
                    st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", invoice_link])
                    st.success("✅ تم تسجيل الشكوى في النشطة")
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")
