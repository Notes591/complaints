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

# ====== تحديث تلقائي ======
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
    "Notifications"
]

sheets_dict = {}
for title in sheet_titles:
    try:
        sheets_dict[title] = client.open(SHEET_NAME).worksheet(title)
    except Exception:
        ss = client.open(SHEET_NAME)
        sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]
notifications_sheet = sheets_dict["Notifications"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== 🔔 نظام الإشعارات ======
def add_notification(order_id, section, message):
    try:
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notifications_sheet.append_row([order_id, section, message, date_now, "NEW"])
    except:
        pass

@st.cache_data(ttl=10)
def get_notifications():
    try:
        data = notifications_sheet.get_all_values()
        return data[1:] if len(data) > 1 else []
    except:
        return []

notifications = get_notifications()
unread = [n for n in notifications if len(n) > 4 and n[4] == "NEW"]

col1, col2 = st.columns([1,5])
with col1:
    st.markdown(f"### 🔔 ({len(unread)})")

with col2:
    with st.expander("عرض الإشعارات"):
        for n in reversed(notifications):
            if len(n) < 5:
                continue
            order_id, section, msg, date, status = n

            if status == "NEW":
                st.warning(f"📦 {order_id} | 📍 {section}\n📝 {msg}\n⏰ {date}")
            else:
                st.write(f"📦 {order_id} | {msg}")

if st.button("✔️ تعليم الكل كمقروء"):
    data = notifications_sheet.get_all_values()
    for i in range(2, len(data)+1):
        notifications_sheet.update(f"E{i}", [["READ"]])
    st.success("تم تحديث الإشعارات")
    # ====== دوال Retry (نفس كودك) ======
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

# ====== تحميل الأنواع ومصادر البيانات ======
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

try:
    order_number_data = order_number_sheet.get_all_values()[1:]
except Exception:
    order_number_data = []

def get_order_status(order_id):
    for row in order_number_data:
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f"الطلب الاساسي🚚 مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "الطلب الاساسي⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"

# ====== إعداد Aramex ======
client_info = {
    "UserName": "fitnessworld525@gmail.com",
    "Password": "Aa12345678@",
    "Version": "v1",
    "AccountNumber": "71958996",
    "AccountPin": "657448",
    "AccountEntity": "RUH",
    "AccountCountryCode": "SA"
}

def remove_xml_namespaces(xml_str):
    xml_str = re.sub(r'xmlns(:\w+)?=\"[^\"]+\"', '', xml_str)
    xml_str = re.sub(r'(<\\/?)(\\w+:)', r'\\1', xml_str)
    return xml_str

def extract_reference(tracking_result):
    for ref_tag in ['Reference1', 'Reference2', 'Reference3', 'Reference4', 'Reference5']:
        ref_elem = tracking_result.find(ref_tag)
        if ref_elem is not None and ref_elem.text and ref_elem.text.strip() != "":
            return ref_elem.text.strip()
    return ""

def get_aramex_status(awb_number, search_type="Waybill"):
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "ClientInfo": client_info,
            "Shipments": [awb_number],
            "Transaction": {"Reference1": "", "Reference2": "", "Reference3": "", "Reference4": "", "Reference5": ""},
            "LabelInfo": None
        }
        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code != 200:
            return f"❌ فشل الاتصال - كود {response.status_code}"

        xml_content = response.content.decode('utf-8')
        xml_content = remove_xml_namespaces(xml_content)
        root = ET.fromstring(xml_content)

        tracking_results = root.find('TrackingResults')
        if tracking_results is None or len(tracking_results) == 0:
            return "❌ لا توجد حالة متاحة"

        keyvalue = tracking_results.find('KeyValueOfstringArrayOfTrackingResultmFAkxlpY')
        if keyvalue is not None:
            tracking_array = keyvalue.find('Value')
            if tracking_array is not None:
                tracks = tracking_array.findall('TrackingResult')
                if tracks:
                    last_track = sorted(
                        tracks,
                        key=lambda tr: tr.find('UpdateDateTime').text if tr.find('UpdateDateTime') is not None else '',
                        reverse=True
                    )[0]

                    desc = last_track.find('UpdateDescription').text if last_track.find('UpdateDescription') is not None else "—"
                    date = last_track.find('UpdateDateTime').text if last_track.find('UpdateDateTime') is not None else "—"
                    loc = last_track.find('UpdateLocation').text if last_track.find('UpdateLocation') is not None else "—"
                    reference = extract_reference(last_track)

                    info = f"{desc} بتاريخ {date} في {loc}"
                    if reference:
                        info += f" | الرقم المرجعي: {reference}"

                    return info

        return "❌ لا توجد حالة متاحة"

    except Exception as e:
        return f"خطأ في جلب الحالة: {e}"

# ====== Cache ======
@st.cache_data(ttl=300)
def cached_aramex_status(awb):
    if not awb or str(awb).strip() == "":
        return ""
    return get_aramex_status(awb)
# ====== دالة عرض الشكوى ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        with st.form(key=f"form_{comp_id}_{sheet.title}"):

            st.write(f"📌 النوع الحالي: {comp_type}")
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            rw_record = get_returnwarehouse_record(comp_id)
            if rw_record:
                st.info(
                    f"📦 سجل من ReturnWarehouse:\n"
                    f"رقم الطلب: {rw_record['رقم الطلب']}\n"
                    f"الفاتورة: {rw_record['الفاتورة']}\n"
                    f"التاريخ: {rw_record['التاريخ']}\n"
                    f"الزبون: {rw_record['الزبون']}\n"
                    f"المبلغ: {rw_record['المبلغ']}\n"
                    f"رقم الشحنة: {rw_record['رقم الشحنة']}\n"
                    f"البيان: {rw_record['البيان']}"
                )

            new_type = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type])
            new_notes = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb)
            new_inbound = st.text_input("✏️ Inbound AWB", value=inbound_awb)

            # ====== عرض حالة Aramex + إشعار عند التسليم ======
            if new_outbound:
                status_out = cached_aramex_status(new_outbound)
                st.info(f"🚚 Outbound AWB: {new_outbound} | الحالة: {status_out}")
                if "Delivered" in status_out:
                    add_notification(comp_id, "الشحن", f"تم تسليم الشحنة {new_outbound}")

            if new_inbound:
                status_in = cached_aramex_status(new_inbound)
                st.info(f"📦 Inbound AWB: {new_inbound} | الحالة: {status_in}")
                if "Delivered" in status_in:
                    add_notification(comp_id, "الشحن", f"تم تسليم الشحنة {new_inbound}")

            col1, col2, col3, col4 = st.columns(4)
            submitted_save = col1.form_submit_button("💾 حفظ")
            submitted_delete = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")

            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ نقل للإجراءات المردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع للنشطة")

            # ====== حفظ ======
            if submitted_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])

                add_notification(comp_id, "تعديل", "تم تعديل الشكوى")
                st.success("✅ تم التعديل")

            # ====== حذف ======
            if submitted_delete:
                if safe_delete(sheet, i):
                    add_notification(comp_id, "حذف", "تم حذف الشكوى")
                    st.warning("🗑️ تم حذف الشكوى")

            # ====== أرشفة ======
            if submitted_archive:
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        add_notification(comp_id, "الأرشيف", "تم أرشفة الشكوى")
                        st.success("♻️ الشكوى انتقلت للأرشيف")

            # ====== نقل ======
            if submitted_move:
                if not in_responded:
                    if safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, "المردودة", "تم نقل الشكوى إلى الإجراءات المردودة")
                            st.success("✅ انتقلت للإجراءات المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, "النشطة", "تم إرجاع الشكوى للنشطة")
                            st.success("✅ انتقلت للنشطة")
                            
# ====== 🔍 البحث عن شكوى ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")

if search_id.strip():
    found = False

    for sheet_obj, in_responded, in_archive in [
        (complaints_sheet, False, False),
        (responded_sheet, True, False),
        (archive_sheet, False, True)
    ]:

        try:
            data = sheet_obj.get_all_values()
        except Exception:
            data = []

        for i, row in enumerate(data[1:], start=2) if data else []:
            if len(row) > 0 and str(row[0]) == search_id:

                location = "النشطة" if not in_responded and not in_archive else "المردودة" if in_responded else "الأرشيف"

                st.success(f"✅ الشكوى موجودة في {location}")

                add_notification(search_id, "بحث", f"تم فتح الشكوى من {location}")

                render_complaint(sheet_obj, i, row, in_responded=in_responded, in_archive=in_archive)

                found = True
                break

        if found:
            break

    if not found:
        st.error("⚠️ لم يتم العثور على الشكوى")


# ====== ➕ تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")

with st.form("add_complaint", clear_on_submit=True):

    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list)
    notes = st.text_area("📝 ملاحظات الشكوى")
    action = st.text_area("✅ الإجراء المتخذ")
    outbound_awb = st.text_input("✏️ Outbound AWB")
    inbound_awb = st.text_input("✏️ Inbound AWB")

    submitted = st.form_submit_button("➕ إضافة")

    if submitted:

        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":

            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            all_active_ids = []
            all_archive_ids = []

            try:
                complaints = complaints_sheet.get_all_records()
                responded = responded_sheet.get_all_records()
                archive = archive_sheet.get_all_records()

                all_active_ids = [str(c.get("ID", "")) for c in complaints] + [str(r.get("ID", "")) for r in responded]
                all_archive_ids = [str(a.get("ID", "")) for a in archive]

            except:
                pass

            # ====== موجود بالفعل ======
            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل")
                add_notification(comp_id, "إضافة", "محاولة إضافة مكررة")

            # ====== استرجاع من الأرشيف ======
            elif comp_id in all_archive_ids:

                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:

                        restored_type = row[1] if len(row) > 1 else ""
                        restored_notes = row[2] if len(row) > 2 else ""
                        restored_action = row[3] if len(row) > 3 else ""
                        restored_outbound = row[6] if len(row) > 6 else ""
                        restored_inbound = row[7] if len(row) > 7 else ""

                        if safe_append(
                            complaints_sheet,
                            [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound]
                        ):
                            if safe_delete(archive_sheet, idx):
                                st.success("♻️ تم استرجاع الشكوى")

                                add_notification(comp_id, "استرجاع", "تم استرجاع الشكوى من الأرشيف")
                        break

            # ====== جديد ======
            else:

                if action.strip():
                    if safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb]):
                        st.success("✅ تم تسجيل الشكوى في المردودة")
                        add_notification(comp_id, "إضافة", "تم تسجيل الشكوى في المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb]):
                        st.success("✅ تم تسجيل الشكوى في النشطة")
                        add_notification(comp_id, "إضافة", "تم تسجيل الشكوى في النشطة")
        else:
            st.error("⚠️ لازم تدخل رقم الشكوى وتختار النوع")
            
# ====== 📋 الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")

active_notes = complaints_sheet.get_all_values()

if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")


# ====== ✅ الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة حسب النوع:")

responded_notes = responded_sheet.get_all_values()

if len(responded_notes) > 1:

    types_in_responded = list({row[1] for row in responded_notes[1:]})

    for complaint_type in types_in_responded:

        with st.expander(f"📌 نوع الشكوى: {complaint_type}"):

            type_rows = [
                (i, row)
                for i, row in enumerate(responded_notes[1:], start=2)
                if row[1] == complaint_type
            ]

            followup_1 = []
            followup_2 = []
            others = []

            for i, row in type_rows:

                comp_id = row[0]
                outbound_awb = row[6] if len(row) > 6 else ""
                inbound_awb = row[7] if len(row) > 7 else ""

                rw_record = get_returnwarehouse_record(comp_id)

                delivered = False
                for awb in [outbound_awb, inbound_awb]:
                    if awb and "Delivered" in cached_aramex_status(awb):
                        delivered = True
                        break

                if delivered and rw_record:
                    followup_2.append((i, row))
                elif delivered:
                    followup_1.append((i, row))
                else:
                    others.append((i, row))

            if followup_1:
                with st.expander("📋 جاهز للمتابعة 1"):
                    for i, row in followup_1:
                        render_complaint(responded_sheet, i, row, in_responded=True)

            if followup_2:
                with st.expander("📋 جاهز للمتابعة 2"):
                    for i, row in followup_2:
                        render_complaint(responded_sheet, i, row, in_responded=True)

            if others:
                with st.expander("📋 غير جاهز للمتابعة"):
                    for i, row in others:
                        render_complaint(responded_sheet, i, row, in_responded=True)

else:
    st.info("لا توجد شكاوى مردودة حالياً.")


# ====== 🚚 معلق أرامكس ======
st.markdown("---")
st.header("🚚 معلق ارامكس")

with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status = st.text_input("📌 الحالة")
    action = st.text_area("✅ الإجراء المتخذ")

    submitted = st.form_submit_button("➕ إضافة")

    if submitted:
        if order_id.strip() and status.strip() and action.strip():

            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if safe_append(aramex_sheet, [order_id, status, date_now, action]):
                st.success("✅ تم تسجيل الطلب")
                add_notification(order_id, "أرامكس", "تم إضافة طلب جديد")

        else:
            st.error("⚠️ لازم تدخل كل البيانات")


# ====== 📋 عرض معلق أرامكس ======
st.subheader("📋 قائمة الطلبات المعلقة")

aramex_pending = aramex_sheet.get_all_values()

if len(aramex_pending) > 1:

    for i, row in enumerate(aramex_pending[1:], start=2):

        while len(row) < 4:
            row.append("")

        order_id = row[0]
        status = row[1]
        date_added = row[2]
        action = row[3]

        with st.expander(f"📦 طلب {order_id}"):

            st.write(f"📌 الحالة: {status}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 {date_added}")

            with st.form(key=f"aramex_{order_id}"):

                new_status = st.text_input("✏️ تعديل الحالة", value=status)
                new_action = st.text_area("✏️ تعديل الإجراء", value=action)

                col1, col2, col3 = st.columns(3)

                save = col1.form_submit_button("💾 حفظ")
                delete = col2.form_submit_button("🗑️ حذف")
                archive = col3.form_submit_button("📦 أرشفة")

                if save:
                    safe_update(aramex_sheet, f"B{i}", [[new_status]])
                    safe_update(aramex_sheet, f"D{i}", [[new_action]])
                    add_notification(order_id, "أرامكس", "تم تعديل الطلب")
                    st.success("تم التعديل")

                if delete:
                    if safe_delete(aramex_sheet, i):
                        add_notification(order_id, "أرامكس", "تم حذف الطلب")
                        st.warning("تم الحذف")

                if archive:
                    if safe_append(aramex_archive, [order_id, new_status, date_added, new_action]):
                        if safe_delete(aramex_sheet, i):
                            add_notification(order_id, "أرامكس", "تم أرشفة الطلب")
                            st.success("تم الأرشفة")

else:
    st.info("لا توجد طلبات أرامكس")


# ====== 📦 أرشيف أرامكس ======
st.markdown("---")
st.header("📦 أرشيف أرامكس:")

aramex_archived = aramex_archive.get_all_values()

if len(aramex_archived) > 1:

    for i, row in enumerate(aramex_archived[1:], start=2):

        while len(row) < 4:
            row.append("")

        order_id = row[0]
        status = row[1]
        date_added = row[2]
        action = row[3]

        with st.expander(f"📦 أرشيف {order_id}"):

            st.write(f"📌 الحالة: {status}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 {date_added}")

            col1, col2 = st.columns(2)

            if col1.button(f"⬅️ إرجاع {order_id}"):
                safe_append(aramex_sheet, [order_id, status, date_added, action])
                safe_delete(aramex_archive, i)
                add_notification(order_id, "أرامكس", "تم إرجاع الطلب")

            if col2.button(f"🗑️ حذف {order_id}"):
                safe_delete(aramex_archive, i)
                add_notification(order_id, "أرامكس", "تم حذف من الأرشيف")

else:
    st.info("لا توجد بيانات في الأرشيف")


# ====== 🔚 ختام ======
st.caption("⚠️ النظام يحفظ تلقائيًا في Google Sheets + إشعارات لحظية داخل التطبيق")
