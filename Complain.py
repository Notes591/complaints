# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import xml.etree.ElementTree as ET
import re
from streamlit_autorefresh import st_autorefresh

# ====== تحديث تلقائي (قابلة للتعديل) ======
# القيمة بالمللي ثانية - الافتراضي 20 دقيقة (1200000). لو تريد 60 ثانية ضع 60000.
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق جوجل شيت ======
SHEET_NAME = "Complaints"
sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number",
    "ForApproval", "Approvals"
]

sheets_dict = {}
for title in sheet_titles:
    try:
        sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
    except Exception as e:
        try:
            ss = client.open(SHEET_NAME)
            sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")
        except Exception as e2:
            st.error(f"خطأ في الوصول/إنشاء ورقة: {title} - {e2}")
            raise

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except gspread.exceptions.APIError:
            time.sleep(delay)
        except Exception:
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
        except Exception:
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
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== تحميل الأنواع ======
try:
    types_list = [row[0] for row in types_sheet.get_all_values()[1:]]
except Exception:
    types_list = []

try:
    return_warehouse_data = return_warehouse_sheet.get_all_values()[1:]
except Exception:
    return_warehouse_data = []

def get_returnwarehouse_record(order_id):
    for row in return_warehouse_data:
        if len(row) > 0 and str(row[0]) == str(order_id):
            return {
                "رقم الطلب": row[0],
                "الفاتورة": row[1] if len(row) > 1 else "",
                "التاريخ": row[2] if len(row) > 2 else "",
                "الزبون": row[3] if len(row) > 3 else "",
                "المبلغ": row[4] if len(row) > 4 else "",
                "رقم الشحنة": row[5] if len(row) > 5 else "",
                "البيان": row[6] if len(row) > 6 else ""
            }
    return None
# ====== بيانات الطلبات ======
try:
    order_number_data = order_number_sheet.get_all_values()[1:]
except Exception:
    order_number_data = []

def get_order_number_record(order_num):
    for row in order_number_data:
        if len(row) > 0 and str(row[0]) == str(order_num):
            return {
                "رقم الطلب": row[0],
                "الاسم": row[1] if len(row) > 1 else "",
                "العنوان": row[2] if len(row) > 2 else "",
                "المدينة": row[3] if len(row) > 3 else "",
                "الموبايل": row[4] if len(row) > 4 else "",
                "الحالة": row[5] if len(row) > 5 else ""
            }
    return None

# ====== دالة عرض الشكاوى ======
def render_complaint(sheet, i, row):
    comp_id = row[0]
    comp_type = row[1] if len(row) > 1 else ""
    notes = row[2] if len(row) > 2 else ""
    action = row[3] if len(row) > 3 else ""
    added = row[4] if len(row) > 4 else ""
    outbound_awb = row[5] if len(row) > 5 else ""
    inbound_awb = row[6] if len(row) > 6 else ""

    with st.expander(f"📄 شكوى رقم {comp_id} — {comp_type}", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_type = st.selectbox("نوع الشكوى", types_list + ["معلق للاعتماد"], index=types_list.index(comp_type) if comp_type in types_list else len(types_list))
            new_notes = st.text_area("ملاحظات", notes)
            new_action = st.text_area("الإجراء", action)
        with col2:
            new_outbound = st.text_input("رقم بوليصة الشحن (Outbound)", outbound_awb)
            new_inbound = st.text_input("رقم بوليصة الإرجاع (Inbound)", inbound_awb)

        col_save, col_delete, col_archive = st.columns(3)
        with col_save:
            if st.button(f"💾 حفظ التعديلات {comp_id}", key=f"save_{comp_id}"):
                if safe_update(sheet, f"A{i}:G{i}", [[comp_id, new_type, new_notes, new_action, added, new_outbound, new_inbound]]):
                    st.success("✅ تم حفظ التعديلات بنجاح")

        with col_delete:
            if st.button(f"🗑️ حذف {comp_id}", key=f"delete_{comp_id}"):
                if safe_delete(sheet, i):
                    st.warning("🗑️ تم حذف الشكوى")

        with col_archive:
            if st.button(f"📦 أرشفة {comp_id}", key=f"archive_{comp_id}"):
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, added, new_outbound, new_inbound]):
                    safe_delete(sheet, i)
                    st.success("✅ تم الأرشفة")

        # =================== زر الإرسال للاعتماد ===================
        if new_type == "معلق للاعتماد":
            col4 = st.columns([1, 3])[0]
            send_for_approval = col4.button("📨 إرسال للاعتماد", key=f"approve_{comp_id}")
            if send_for_approval:
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if safe_append(sheets_dict["ForApproval"], [comp_id, new_type, new_notes, new_action, date_now, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        st.success("✅ تم إرسال الشكوى للاعتماد لدى المدير")
                    else:
                        st.warning("⚠️ أُرسلت الشكوى ولكن لم تُحذف من الجدول الحالي")
                else:
                    st.error("❌ حدث خطأ أثناء الإرسال للاعتماد")
# ====== عرض الشكاوى الحالية ======
st.subheader("📋 الشكاوى الحالية")
try:
    complaints_data = complaints_sheet.get_all_values()[1:]
    if not complaints_data:
        st.info("لا توجد شكاوى حالية.")
    else:
        for i, row in enumerate(complaints_data, start=2):
            render_complaint(complaints_sheet, i, row)
except Exception as e:
    st.error(f"حدث خطأ أثناء تحميل الشكاوى: {e}")

# ====== عرض الشكاوى المردودة ======
st.subheader("📤 الشكاوى المردودة")
try:
    responded_data = responded_sheet.get_all_values()[1:]
    if not responded_data:
        st.info("لا توجد شكاوى مردودة.")
    else:
        for i, row in enumerate(responded_data, start=2):
            comp_id = row[0]
            comp_type = row[1] if len(row) > 1 else ""
            notes = row[2] if len(row) > 2 else ""
            action = row[3] if len(row) > 3 else ""
            added = row[4] if len(row) > 4 else ""
            st.markdown(f"**📄 {comp_id} — {comp_type}**")
            st.text_area("ملاحظات", notes, disabled=True)
            st.text_area("الإجراء", action, disabled=True)
except Exception as e:
    st.error(f"حدث خطأ أثناء تحميل المردودة: {e}")

# ====== عرض الأرشيف ======
st.subheader("🗃️ الأرشيف")
try:
    archive_data = archive_sheet.get_all_values()[1:]
    if not archive_data:
        st.info("الأرشيف فارغ حالياً.")
    else:
        for i, row in enumerate(archive_data, start=2):
            comp_id = row[0]
            comp_type = row[1] if len(row) > 1 else ""
            notes = row[2] if len(row) > 2 else ""
            action = row[3] if len(row) > 3 else ""
            added = row[4] if len(row) > 4 else ""
            st.markdown(f"📦 **{comp_id} — {comp_type}** ({added})")
            st.text_area("ملاحظات", notes, disabled=True)
            st.text_area("الإجراء", action, disabled=True)
except Exception as e:
    st.error(f"خطأ أثناء عرض الأرشيف: {e}")

# ====== عرض شكاوى أرامكس ======
st.subheader("🚚 شكاوى أرامكس المعلقة")
try:
    aramex_data = aramex_sheet.get_all_values()[1:]
    if not aramex_data:
        st.info("لا توجد شكاوى أرامكس حالياً.")
    else:
        for i, row in enumerate(aramex_data, start=2):
            comp_id = row[0]
            comp_type = row[1] if len(row) > 1 else ""
            notes = row[2] if len(row) > 2 else ""
            action = row[3] if len(row) > 3 else ""
            added = row[4] if len(row) > 4 else ""
            st.markdown(f"📮 **{comp_id} — {comp_type}** ({added})")
            st.text_area("ملاحظات", notes, disabled=True)
            st.text_area("الإجراء", action, disabled=True)
except Exception as e:
    st.error(f"خطأ أثناء تحميل شكاوى أرامكس: {e}")

# ====== أرشيف أرامكس ======
st.subheader("📦 أرشيف أرامكس")
try:
    aramex_archive_data = aramex_archive.get_all_values()[1:]
    if not aramex_archive_data:
        st.info("أرشيف أرامكس فارغ.")
    else:
        for i, row in enumerate(aramex_archive_data, start=2):
            comp_id = row[0]
            comp_type = row[1] if len(row) > 1 else ""
            notes = row[2] if len(row) > 2 else ""
            action = row[3] if len(row) > 3 else ""
            added = row[4] if len(row) > 4 else ""
            st.markdown(f"📜 **{comp_id} — {comp_type}** ({added})")
            st.text_area("ملاحظات", notes, disabled=True)
            st.text_area("الإجراء", action, disabled=True)
except Exception as e:
    st.error(f"خطأ أثناء عرض أرشيف أرامكس: {e}")
# ================= Manager Approval / Electronic Signature Extension =================
# هذا القسم لا يغيّر هيكل البرنامج الأساسي، فقط يضيف شاشة اعتماد المدير الجديدة.

try:
    import base64, io
    from PIL import Image
except Exception:
    pass

def _get_config_sheet():
    try:
        if 'sheets_dict' in globals() and isinstance(sheets_dict, dict):
            return sheets_dict.get("Config")
        return None
    except Exception:
        return None

def get_manager_password():
    """يحصل على كلمة مرور المدير من ورقة Config أو من st.secrets"""
    try:
        cfg = _get_config_sheet()
        if cfg:
            try:
                vals = cfg.get_all_values()
            except Exception:
                vals = []
            for row in vals:
                if len(row) >= 2 and row[0].strip().lower() == "manager_password":
                    return row[1]
        try:
            return st.secrets.get("manager_password")
        except Exception:
            return None
    except Exception:
        return None

def set_manager_password(new_pw):
    """يحفظ كلمة المرور الجديدة في ورقة Config"""
    cfg = _get_config_sheet()
    if cfg is None:
        st.error("لم يتم العثور على ورقة Config. أنشئها لحفظ كلمة المرور.")
        return
    try:
        vals = cfg.get_all_values()
    except Exception:
        vals = []
    row_idx = None
    for idx, row in enumerate(vals, start=1):
        if len(row) >= 1 and row[0].strip().lower() == "manager_password":
            row_idx = idx
            break
    if row_idx:
        cfg.update_cell(row_idx, 2, new_pw)
    else:
        cfg.append_row(["manager_password", new_pw])
    st.success("✅ تم تغيير كلمة مرور المدير بنجاح.")

def manager_approval_ui():
    st.markdown("---")
    st.header("🔒 اعتماد المدير (توقيع إلكتروني)")

    current_pw = get_manager_password()
    entered_pw = st.text_input("🔑 أدخل كلمة مرور المدير", type="password", key="m_pw")

    if entered_pw:
        if current_pw is None or entered_pw == current_pw:
            st.success("✅ تم تسجيل الدخول كمدير.")
            
            # ====== تغيير كلمة المرور ======
            with st.expander("🔁 تغيير كلمة مرور المدير"):
                old = st.text_input("كلمة المرور الحالية للتحقق", type="password", key="old_pw")
                new1 = st.text_input("كلمة المرور الجديدة", type="password", key="new_pw1")
                new2 = st.text_input("تأكيد كلمة المرور الجديدة", type="password", key="new_pw2")
                if st.button("💾 تغيير كلمة المرور"):
                    if current_pw and old != current_pw:
                        st.error("كلمة المرور الحالية غير صحيحة.")
                    elif new1 != new2 or not new1:
                        st.warning("كلمة المرور الجديدة غير متطابقة أو فارغة.")
                    else:
                        set_manager_password(new1)

            # ====== عرض الطلبات المعلقة للاعتماد ======
            st.subheader("📋 الطلبات المرسلة للاعتماد")
            try:
                approval_sheet = sheets_dict["ForApproval"]
                approvals = approval_sheet.get_all_values()
            except Exception:
                approvals = []

            if len(approvals) <= 1:
                st.info("لا توجد طلبات اعتماد حالياً.")
                return

            for i, row in enumerate(approvals[1:], start=2):
                while len(row) < 7:
                    row.append("")
                comp_id, comp_type, notes, action, added, outbound, inbound = row[:7]

                with st.expander(f"🆔 {comp_id} — {comp_type} ({added})"):
                    st.write(f"**الملاحظات:** {notes}")
                    st.write(f"**الإجراء:** {action}")
                    st.write(f"**خروج:** {outbound} — **دخول:** {inbound}")

                    st.write("✍️ **توقيع المدير:**")
                    signature_b64 = None

                    try:
                        from streamlit_drawable_canvas import st_canvas
                        import numpy as np

                        canvas = st_canvas(
                            stroke_width=2,
                            stroke_color="#000",
                            background_color="#fff",
                            height=150,
                            width=450,
                            drawing_mode="freedraw",
                            key=f"sig_{comp_id}_{i}"
                        )
                        if canvas.image_data is not None:
                            img = Image.fromarray(canvas.image_data.astype("uint8"))
                            buf = io.BytesIO()
                            img.save(buf, format="PNG")
                            signature_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                            st.success("تم تسجيل التوقيع باليد.")
                    except Exception:
                        st.info("لوحة الرسم غير متاحة. يمكنك رفع صورة أو كتابة اسمك.")
                        uploaded = st.file_uploader(f"رفع صورة توقيع {comp_id}", type=["png","jpg","jpeg"], key=f"upl_{comp_id}")
                        if uploaded:
                            signature_b64 = base64.b64encode(uploaded.read()).decode("utf-8")
                            st.success("✅ تم رفع صورة التوقيع.")
                        else:
                            name = st.text_input("اكتب اسم المدير (بديل للتوقيع)", key=f"name_{comp_id}")
                            if name:
                                signature_b64 = base64.b64encode(f"NAME_SIGNED:{name}".encode()).decode("utf-8")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ اعتماد", key=f"ok_{comp_id}"):
                            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            if safe_append(sheets_dict["Approvals"], [comp_id, comp_type, notes, action, date_now, "Manager", signature_b64 or ""]):
                                safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "معتمد من المدير", outbound, inbound])
                                safe_delete(approval_sheet, i)
                                st.success("✅ تم اعتماد الشكوى وتحويلها للمردودة.")
                            else:
                                st.error("فشل في حفظ الاعتماد.")

                    with col2:
                        if st.button("❌ رفض", key=f"rej_{comp_id}"):
                            if safe_append(archive_sheet, [comp_id, comp_type, notes, action, added, "مرفوض من المدير", outbound, inbound]):
                                safe_delete(approval_sheet, i)
                                st.warning("تم رفض الشكوى وأرشفتها.")
        else:
            st.error("❌ كلمة المرور غير صحيحة.")
    else:
        st.info("أدخل كلمة مرور المدير للدخول إلى شاشة الاعتماد.")

# ====== استدعاء الشاشة ======
manager_approval_ui()
# ================= End of Manager Approval Extension =================
