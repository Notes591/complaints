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
archive_sheet = client.open(SHEET_NAME).worksheet("Archive")
types_sheet = client.open(SHEET_NAME).worksheet("Types")
aramex_sheet = client.open(SHEET_NAME).worksheet("معلق ارامكس")
aramex_archive = client.open(SHEET_NAME).worksheet("أرشيف أرامكس")
responded_sheet = client.open(SHEET_NAME).worksheet("Responded")

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
        responded = responded_sheet.get_all_values()
        found = False

        # بحث في الشكاوى النشطة
        for i, row in enumerate(complaints[1:], start=2):
            if row[0] == search_id:
                found = True
                with st.expander(f"🆔 شكوى رقم {row[0]} (نشطة)"):
                    comp_id, comp_type, notes, action, date_added, restored = row[:6] + [""]*(6-len(row))
                    st.write(f"📌 النوع: {comp_type}")
                    st.write(f"📝 ملاحظات الشكوى: {notes}")
                    st.write(f"✅ الإجراء: {action}")
                    st.caption(f"📅 تاريخ التسجيل: {date_added}")

                    new_notes = st.text_area("✏️ عدل ملاحظات الشكوى", value=notes, key=f"notes_{i}")
                    new_action = st.text_area("✏️ اكتب الإجراء المتخذ", value=action, key=f"action_{i}")
                    col1, col2, col3, col4 = st.columns(4)

                    # حفظ التعديلات
                    if col1.button("💾 حفظ", key=f"save_{i}"):
                        complaints_sheet.update(f"C{i}", [[new_notes]])
                        st.success("✅ تم تعديل الشكوى")
                        st.rerun()

                    # حذف
                    if col2.button("🗑️ حذف", key=f"delete_{i}"):
                        complaints_sheet.delete_rows(i)
                        st.warning("🗑️ تم حذف الشكوى")
                        st.rerun()

                    # أرشفة
                    if col3.button("📦 أرشفة", key=f"archive_{i}"):
                        archive_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
                        complaints_sheet.delete_rows(i)
                        st.success("♻️ الشكوى انتقلت للأرشيف")
                        st.rerun()

                    # نقل للإجراءات المردودة
                    if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{i}") and new_action.strip():
                        try:
                            responded_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
                            complaints_sheet.delete_rows(i)
                            st.success("✅ اتنقلت لقائمة الإجراءات المردودة")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ حدث خطأ أثناء النقل: {e}")

        # بحث في الإجراءات المردودة
        for i, row in enumerate(responded[1:], start=2):
            if row[0] == search_id:
                found = True
                with st.expander(f"📝 شكوى رقم {row[0]} (الإجراءات المردودة)"):
                    comp_id, comp_type, notes, action, date_added, restored = row[:6] + [""]*(6-len(row))
                    st.write(f"📌 النوع: {comp_type}")
                    st.write(f"📝 ملاحظات الشكوى: {notes}")
                    st.write(f"✅ الإجراء: {action}")
                    st.caption(f"📅 تاريخ التسجيل: {date_added}")

                    new_notes = st.text_area("✏️ عدل ملاحظات الشكوى", value=notes, key=f"rnotes_{i}")
                    new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"raction_{i}")
                    col1, col2 = st.columns(2)

                    # إذا كتبوا ملاحظات جديدة ترجع للنشطة
                    if col1.button("⬅️ رجوع للنشطة", key=f"to_active_{i}") and new_notes.strip():
                        try:
                            complaints_sheet.append_row([comp_id, comp_type, new_notes, "", date_added, restored])
                            responded_sheet.delete_rows(i)
                            st.success("✅ اتنقلت تاني لقائمة النشطة")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ حدث خطأ أثناء النقل: {e}")

                    # حذف
                    if col2.button("🗑️ حذف", key=f"rdelete_{i}"):
                        responded_sheet.delete_rows(i)
                        st.warning("🗑️ تم حذف الشكوى من الإجراءات المردودة")
                        st.rerun()

        # بحث في الأرشيف
        for i, row in enumerate(archive[1:], start=2):
            if row[0] == search_id:
                found = True
                with st.expander(f"📦 شكوى رقم {row[0]} (في الأرشيف)"):
                    comp_id, comp_type, notes, action, date_added, restored = row[:6] + [""]*(6-len(row))
                    st.write(f"📌 النوع: {comp_type}")
                    st.write(f"📝 ملاحظات الشكوى: {notes}")
                    st.write(f"✅ الإجراء: {action}")
                    st.caption(f"📅 تاريخ التسجيل: {date_added}")

        if not found:
            st.error("❌ لم يتم العثور على الشكوى")

# ====== 2. تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")
with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    notes = st.text_area("📝 ملاحظات الشكوى")

    submitted = st.form_submit_button("➕ إضافة شكوى")
    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            complaints_ids = [str(c[0]) for c in complaints_sheet.get_all_values()[1:]]
            archive_ids = [str(a[0]) for a in archive_sheet.get_all_values()[1:]]

            if comp_id in complaints_ids:
                st.error("⚠️ رقم الشكوى موجود بالفعل في الشكاوى النشطة")
            elif comp_id in archive_ids:
                for i, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if row[0] == comp_id:
                        archive_sheet.delete_rows(i)
                        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        complaints_sheet.append_row([comp_id, comp_type, notes, "", date_now, "🔄 مسترجعة"])
                        st.success("✅ تم استرجاع الشكوى من الأرشيف وإعادة تفعيلها")
                        st.rerun()
            else:
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                complaints_sheet.append_row([comp_id, comp_type, notes, "", date_now, ""])
                st.success("✅ تم تسجيل الشكوى")
                st.rerun()
        else:
            st.error("⚠️ لازم تدخل رقم شكوى وتختار نوع")

# ====== 3. عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
notes = complaints_sheet.get_all_values()
if len(notes) > 1:
    for i, row in enumerate(notes[1:], start=2):
        comp_id, comp_type, notes_text, action, date_added, restored = row[:6] + [""]*(6-len(row))
        with st.expander(f"🆔 شكوى رقم {comp_id} {restored}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"📝 ملاحظات الشكوى: {notes_text}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            new_notes = st.text_area("✏️ عدل ملاحظات الشكوى", value=notes_text, key=f"notes_{i}")
            new_action = st.text_area("✏️ عدل الإجراء", value=action, key=f"action_{i}")
            col1, col2, col3, col4 = st.columns(4)

            if col1.button("💾 حفظ", key=f"save_{i}"):
                complaints_sheet.update(f"C{i}", [[new_notes]])
                st.success("✅ تم تعديل الشكوى")
                st.rerun()

            if col2.button("🗑️ حذف", key=f"delete_{i}"):
                complaints_sheet.delete_rows(i)
                st.warning("🗑️ تم حذف الشكوى")
                st.rerun()

            if col3.button("📦 أرشفة", key=f"archive_{i}"):
                archive_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
                complaints_sheet.delete_rows(i)
                st.success("♻️ الشكوى انتقلت للأرشيف")
                st.rerun()

            if col4.button("➡️ نقل للإجراءات المردودة", key=f"to_responded_{i}") and new_action.strip():
                try:
                    responded_sheet.append_row([comp_id, comp_type, new_notes, new_action, date_added, restored])
                    complaints_sheet.delete_rows(i)
                    st.success("✅ اتنقلت لقائمة الإجراءات المردودة")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ حدث خطأ أثناء النقل: {e}")

else:
    st.info("لا توجد شكاوى حالياً.")

# ====== 4. عرض الأرشيف ======
st.header("📦 الأرشيف (الشكاوى المحلولة):")
archived = archive_sheet.get_all_values()
if len(archived) > 1:
    for row in archived[1:]:
        comp_id, comp_type, notes_text, action, date_added, restored = row[:6] + [""]*(6-len(row))
        with st.expander(f"📦 شكوى رقم {comp_id} {restored}"):
            st.write(f"📌 النوع: {comp_type}")
            st.write(f"📝 ملاحظات الشكوى: {notes_text}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")
else:
    st.info("لا يوجد شكاوى في الأرشيف.")

# ====== 5. معلق ارامكس ======
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

# عرض الطلبات
st.subheader("📋 قائمة الطلبات المعلقة")
aramex_data = aramex_sheet.get_all_values()
if len(aramex_data) > 1:
    for i, row in enumerate(aramex_data[1:], start=2):
        order_id, status, date_added, action = row[:4]
        with st.expander(f"طلب {order_id}"):
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
