# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import io
import base64
from PIL import Image
from streamlit_drawable_canvas import st_canvas
import time

# ====== إعدادات الاتصال بجوجل شيت ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ====== أوراق الشيت ======
SHEET_NAME = "Complaints"
try:
    sheet = client.open(SHEET_NAME)
except Exception as e:
    st.error(f"❌ خطأ في فتح الشيت: {e}")
    st.stop()

# أوراق المستخدمين كما في كودك (ننشئ إذا لم توجد لتفادي الأخطاء)
try:
    complaints_sheet = sheet.worksheet("Complaints")
except Exception:
    complaints_sheet = sheet.add_worksheet(title="Complaints", rows="1000", cols="20")

try:
    responded_sheet = sheet.worksheet("Responded")
except Exception:
    responded_sheet = sheet.add_worksheet(title="Responded", rows="1000", cols="20")

try:
    archive_sheet = sheet.worksheet("Archive")
except Exception:
    archive_sheet = sheet.add_worksheet(title="Archive", rows="1000", cols="20")

# ورقة توقيعات المدير (توجد كما قلت)
try:
    manager_sign_sheet = sheet.worksheet("ManagerSignatures")
except Exception:
    manager_sign_sheet = sheet.add_worksheet(title="ManagerSignatures", rows="1000", cols="20")

# ====== دوال مساعدة ======
def safe_append(sheet_obj, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet_obj.append_row(row_data)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_delete(sheet_obj, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet_obj.delete_rows(row_index)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

def safe_update(sheet_obj, cell_range, values, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet_obj.update(cell_range, values)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

# ====== دالة رسم التوقيع الإلكتروني ======
def draw_signature(key="canvas_signature"):
    st.subheader("✍️ التوقيع الإلكتروني للمدير")
    st.write("قم برسم توقيعك داخل المربع أدناه:")

    canvas = st_canvas(
        fill_color="rgba(0, 0, 0, 0)",
        stroke_width=3,
        stroke_color="#000000",
        background_color="#FFFFFF",
        width=500,
        height=200,
        drawing_mode="freedraw",
        key=key,
    )

    if canvas.image_data is not None:
        img = Image.fromarray(canvas.image_data.astype("uint8"))
        st.image(img, caption="التوقيع الذي تم رسمه")

        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        signature_base64 = base64.b64encode(buffered.getvalue()).decode()

        st.success("✔ تم إنشاء التوقيع بنجاح")
        return signature_base64
    return None

# ====== النظام الرئيسي للمدير ======
def run_admin_system():
    st.title("👑 لوحة تحكم المدير")

    # --- تسجيل الدخول ---
    st.subheader("🔐 تسجيل الدخول كمدير")
    password = st.text_input("ادخل كلمة المرور", type="password")
    if "admin_password" not in st.session_state:
        st.session_state.admin_password = "1234"

    if password == "":
        st.info("من فضلك ادخل كلمة المرور للدخول.")
        return

    if password != st.session_state.admin_password:
        st.error("❌ كلمة المرور غير صحيحة")
        return

    st.success("✔ تم تسجيل الدخول بنجاح")
    st.write("---")

    # --- اختيار وظيفة المدير ---
    option = st.selectbox("اختر وظيفة:", [
        "عرض الشكاوى",
        "اعتماد شكوى",
        "رفض شكوى",
        "إدارة كلمات المرور",
        "التوقيع الإلكتروني",
        "طلبات التوقيع"
    ])

    # ====== عرض الشكاوى ======
    if option == "عرض الشكاوى":
        st.header("📋 الشكاوى النشطة")
        data = complaints_sheet.get_all_values()
        if len(data) > 1:
            for i, row in enumerate(data[1:], start=2):
                while len(row) < 4:
                    row.append("")
                comp_id, comp_type, notes, action = row[:4]
                st.info(f"🆔 {comp_id} | 📌 {comp_type}")
                st.write(f"📝 الملاحظات: {notes}")
                st.write(f"✅ الإجراء: {action}")
        else:
            st.info("لا توجد شكاوى حالياً.")

    # ====== اعتماد الشكوى (الطريقة القديمة إذا أردت استخدامه) ======
    elif option == "اعتماد شكوى":
        st.header("✔ اعتماد شكوى")
        comp_id = st.text_input("أدخل رقم الشكوى لاعتمادها")
        signature_img = draw_signature(key="canvas_approve")
        if st.button("اعتماد الشكوى"):
            if not comp_id:
                st.error("⚠️ ادخل رقم الشكوى")
            elif signature_img is None:
                st.error("⚠️ يجب رسم التوقيع أولاً")
            else:
                # نبحث عن الشكوى في الشيتات ونحدّث Action ونضيف سجل في ManagerSignatures
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                manager_name = "المدير"
                appended = False

                # أضف/حدّث سجل ManagerSignatures
                # نتحقق إن كان هناك سجل سابق
                try:
                    signs = manager_sign_sheet.get_all_values()[1:]
                except Exception:
                    signs = []

                existing_idx = None
                for idx, r in enumerate(signs, start=2):
                    if len(r) > 0 and str(r[0]) == str(comp_id):
                        existing_idx = idx
                        break

                if existing_idx:
                    safe_update(manager_sign_sheet, f"B{existing_idx}", [[manager_name]])
                    safe_update(manager_sign_sheet, f"C{existing_idx}", [[now]])
                    safe_update(manager_sign_sheet, f"E{existing_idx}", [["معتمد"]])
                    safe_update(manager_sign_sheet, f"F{existing_idx}", [[signature_img]])
                else:
                    safe_append(manager_sign_sheet, [comp_id, manager_name, now, "", "معتمد", signature_img])

                # نحدّث العمود D (الإجراء) في أي شيت يوجد به الـ ID
                for sh in [complaints_sheet, responded_sheet, archive_sheet]:
                    try:
                        rows = sh.get_all_values()
                    except Exception:
                        rows = []
                    for i, row in enumerate(rows[1:], start=2) if rows else []:
                        if len(row) > 0 and str(row[0]) == str(comp_id):
                            action_text = row[3] if len(row) > 3 else ""
                            note = f" | ✔ تم اعتمادها بواسطة {manager_name} بتاريخ {now}"
                            if note.strip() not in (action_text or ""):
                                try:
                                    safe_update(sh, f"D{i}", [[(action_text or "") + note]])
                                except Exception:
                                    pass
                            appended = True
                            break
                    if appended:
                        break

                st.success(f"✅ تم اعتماد الشكوى {comp_id}")

    # ====== رفض الشكوى (الطريقة القديمة) ======
    elif option == "رفض شكوى":
        st.header("❌ رفض شكوى")
        comp_id = st.text_input("أدخل رقم الشكوى لرفضها")
        signature_img = draw_signature(key="canvas_reject")
        if st.button("رفض الشكوى"):
            if not comp_id:
                st.error("⚠️ ادخل رقم الشكوى")
            elif signature_img is None:
                st.error("⚠️ يجب رسم التوقيع أولاً")
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                manager_name = "المدير"

                # تحديث/إضافة سجل في ManagerSignatures
                try:
                    signs = manager_sign_sheet.get_all_values()[1:]
                except Exception:
                    signs = []

                existing_idx = None
                for idx, r in enumerate(signs, start=2):
                    if len(r) > 0 and str(r[0]) == str(comp_id):
                        existing_idx = idx
                        break

                if existing_idx:
                    safe_update(manager_sign_sheet, f"B{existing_idx}", [[manager_name]])
                    safe_update(manager_sign_sheet, f"C{existing_idx}", [[now]])
                    safe_update(manager_sign_sheet, f"E{existing_idx}", [["مرفوض"]])
                    safe_update(manager_sign_sheet, f"F{existing_idx}", [[signature_img]])
                else:
                    safe_append(manager_sign_sheet, [comp_id, manager_name, now, "", "مرفوض", signature_img])

                # تحديث الإجراء في الشيتات إن لزم
                for sh in [complaints_sheet, responded_sheet, archive_sheet]:
                    try:
                        rows = sh.get_all_values()
                    except Exception:
                        rows = []
                    for i, row in enumerate(rows[1:], start=2) if rows else []:
                        if len(row) > 0 and str(row[0]) == str(comp_id):
                            action_text = row[3] if len(row) > 3 else ""
                            note = f" | ❌ تم رفضها بواسطة {manager_name} بتاريخ {now}"
                            if note.strip() not in (action_text or ""):
                                try:
                                    safe_update(sh, f"D{i}", [[(action_text or "") + note]])
                                except Exception:
                                    pass
                            break

                st.success(f"✅ تم رفض الشكوى {comp_id}")

    # ====== إدارة كلمات المرور ======
    elif option == "إدارة كلمات المرور":
        st.header("🔑 إدارة كلمة المرور")
        current_pw = st.text_input("كلمة المرور الحالية", type="password")
        new_pw = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pw = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
        if st.button("تغيير كلمة المرور"):
            if current_pw != st.session_state.admin_password:
                st.error("⚠ كلمة المرور الحالية غير صحيحة")
            elif new_pw != confirm_pw:
                st.error("⚠ كلمة المرور الجديدة لا تتطابق")
            else:
                st.session_state.admin_password = new_pw
                st.success("✔ تم تغيير كلمة المرور بنجاح")

    # ====== التوقيع الإلكتروني فقط ======
    elif option == "التوقيع الإلكتروني":
        st.header("✍️ توقيع المدير")
        signature_img = draw_signature(key="canvas_only")
        if signature_img:
            st.write("🔽 هذا هو التوقيع بصيغة Base64:")
            st.code(signature_img)
            st.info("يمكنك نسخ هذا الكود أو حفظه في Google Sheet كما تريد.")

    # ====== صفحة طلبات التوقيع (الحديثة) ======
    elif option == "طلبات التوقيع":
        st.header("🖋 طلبات التوقيع الإلكتروني")

        try:
            data = manager_sign_sheet.get_all_values()[1:]
        except Exception:
            data = []

        pending = [r for r in data if len(r) > 4 and r[4] == "مطلوب توقيع"]

        if not pending:
            st.info("لا توجد طلبات توقيع حالياً.")
        else:
            for r in pending:
                comp_id = r[0]
                date_added = r[2] if len(r) > 2 else ""
                notes = r[3] if len(r) > 3 else ""

                st.subheader(f"📌 شكوى رقم: {comp_id}")
                st.write(f"📅 تاريخ الطلب: {date_added}")
                st.write(f"📝 ملاحظات: {notes if notes else '—'}")

                sig = draw_signature(key=f"canvas_req_{comp_id}")

                col1, col2 = st.columns(2)

                if col1.button(f"✔ اعتماد {comp_id}"):
                    if sig:
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        manager_name = "المدير"

                        # إيجاد صف الطلب في ManagerSignatures
                        signs = manager_sign_sheet.get_all_values()[1:]
                        existing_idx = None
                        for idx, row_s in enumerate(signs, start=2):
                            if len(row_s) > 0 and str(row_s[0]) == str(comp_id):
                                existing_idx = idx
                                break

                        if existing_idx:
                            safe_update(manager_sign_sheet, f"B{existing_idx}", [[manager_name]])
                            safe_update(manager_sign_sheet, f"C{existing_idx}", [[now]])
                            safe_update(manager_sign_sheet, f"E{existing_idx}", [["معتمد"]])
                            safe_update(manager_sign_sheet, f"F{existing_idx}", [[sig]])
                        else:
                            safe_append(manager_sign_sheet, [comp_id, manager_name, now, "", "معتمد", sig])

                        # تحديث خانة الإجراء في أي شيت يحتوي الـ ID
                        updated = False
                        for sh in [complaints_sheet, responded_sheet, archive_sheet]:
                            try:
                                rows_sh = sh.get_all_values()
                            except Exception:
                                rows_sh = []
                            for i, row_sh in enumerate(rows_sh[1:], start=2) if rows_sh else []:
                                if len(row_sh) > 0 and str(row_sh[0]) == str(comp_id):
                                    action_text = row_sh[3] if len(row_sh) > 3 else ""
                                    note = f" | ✔ تم اعتمادها بواسطة {manager_name} بتاريخ {now}"
                                    if note.strip() not in (action_text or ""):
                                        try:
                                            safe_update(sh, f"D{i}", [[(action_text or "") + note]])
                                        except Exception:
                                            pass
                                    updated = True
                                    break
                            if updated:
                                break

                        st.success(f"✔ تم الاعتماد {comp_id}")

                if col2.button(f"❌ رفض {comp_id}"):
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    manager_name = "المدير"

                    # إيجاد صف الطلب في ManagerSignatures
                    signs = manager_sign_sheet.get_all_values()[1:]
                    existing_idx = None
                    for idx, row_s in enumerate(signs, start=2):
                        if len(row_s) > 0 and str(row_s[0]) == str(comp_id):
                            existing_idx = idx
                            break

                    if existing_idx:
                        safe_update(manager_sign_sheet, f"B{existing_idx}", [[manager_name]])
                        safe_update(manager_sign_sheet, f"C{existing_idx}", [[now]])
                        safe_update(manager_sign_sheet, f"E{existing_idx}", [["مرفوض"]])
                    else:
                        safe_append(manager_sign_sheet, [comp_id, manager_name, now, "", "مرفوض", ""])

                    # تحديث خانة الإجراء في أي شيت يحتوي الـ ID
                    updated = False
                    for sh in [complaints_sheet, responded_sheet, archive_sheet]:
                        try:
                            rows_sh = sh.get_all_values()
                        except Exception:
                            rows_sh = []
                        for i, row_sh in enumerate(rows_sh[1:], start=2) if rows_sh else []:
                            if len(row_sh) > 0 and str(row_sh[0]) == str(comp_id):
                                action_text = row_sh[3] if len(row_sh) > 3 else ""
                                note = f" | ❌ تم رفضها بواسطة {manager_name} بتاريخ {now}"
                                if note.strip() not in (action_text or ""):
                                    try:
                                        safe_update(sh, f"D{i}", [[(action_text or "") + note]])
                                    except Exception:
                                        pass
                                updated = True
                                break
                        if updated:
                            break

                    st.warning(f"❌ تم رفض الطلب {comp_id}")

if __name__ == "__main__":
    run_admin_system()
