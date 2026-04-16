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

# ====== تحديث تلقائي كل دقيقة عشان الإشعارات تتحدث ======
st_autorefresh(interval=60000, key="auto_refresh")

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
    "Notifications"  # ورقة جديدة للإشعارات
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

complaints_sheet     = sheets_dict["Complaints"]
responded_sheet      = sheets_dict["Responded"]
archive_sheet        = sheets_dict["Archive"]
types_sheet          = sheets_dict["Types"]
aramex_sheet         = sheets_dict["معلق ارامكس"]
aramex_archive       = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet   = sheets_dict["Order Number"]
notifications_sheet  = sheets_dict["Notifications"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")

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

# ======================================================
# ====== نظام الإشعارات ======
# ======================================================
# الأعمدة في ورقة Notifications:
# A: notification_id | B: order_id | C: comp_type | D: action_done | E: timestamp | F: is_read

NOTIF_ICON = {
    "إضافة شكوى جديدة": "➕",
    "تعديل شكوى": "✏️",
    "حفظ شكوى": "💾",
    "أرشفة شكوى": "📦",
    "حذف شكوى": "🗑️",
    "نقل للمردودة": "➡️",
    "رجوع للنشطة": "⬅️",
    "طلب جديد في ReturnWarehouse": "🆕",
    "إضافة معلق أرامكس": "🚚",
    "تعديل معلق أرامكس": "✏️",
    "أرشفة معلق أرامكس": "📦",
}

def add_notification(order_id, comp_type, action_done):
    """يحفظ إشعار جديد في ورقة Notifications"""
    notif_id = f"N{int(time.time()*1000)}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_append(notifications_sheet, [notif_id, str(order_id), str(comp_type), str(action_done), timestamp, "unread"])

def get_notifications():
    """يجيب كل الإشعارات من الورقة"""
    try:
        all_rows = notifications_sheet.get_all_values()
        # لو الورقة فاضية أو عندها header بس
        if len(all_rows) == 0:
            return []
        # نتجاهل أي header لو موجود (نشوف لو الصف الأول = header)
        data_rows = []
        for i, row in enumerate(all_rows):
            if len(row) < 5:
                continue
            # نتخطى الـ header لو موجود
            if row[0] == "notification_id":
                continue
            data_rows.append({
                "row_index": i + 1,  # 1-based
                "notif_id": row[0],
                "order_id": row[1],
                "comp_type": row[2],
                "action_done": row[3],
                "timestamp": row[4],
                "is_read": row[5] if len(row) > 5 else "unread"
            })
        # الأحدث أولاً
        data_rows.reverse()
        return data_rows
    except Exception:
        return []

def mark_all_read():
    """يعلّم كل الإشعارات كـ مقروءة"""
    try:
        all_rows = notifications_sheet.get_all_values()
        updates = []
        for i, row in enumerate(all_rows):
            if len(row) >= 6 and row[5] == "unread":
                updates.append({
                    "range": f"F{i+1}",
                    "values": [["read"]]
                })
        if updates:
            for u in updates:
                safe_update(notifications_sheet, u["range"], u["values"])
    except Exception:
        pass

def clear_all_notifications():
    """يحذف كل الإشعارات"""
    try:
        all_rows = notifications_sheet.get_all_values()
        # نحذف من الأسفل للأعلى عشان ما يختل ترقيم الصفوف
        for i in range(len(all_rows), 0, -1):
            safe_delete(notifications_sheet, i)
    except Exception:
        pass

# ====== عرض الإشعارات في الشريط الجانبي ======
def render_notifications_sidebar():
    notifications = get_notifications()
    unread_count = sum(1 for n in notifications if n["is_read"] == "unread")

    with st.sidebar:
        st.markdown("---")
        # عنوان مع عداد
        if unread_count > 0:
            st.markdown(f"### 🔔 الإشعارات &nbsp; <span style='background:#e74c3c;color:white;border-radius:50%;padding:2px 8px;font-size:14px;'>{unread_count}</span>", unsafe_allow_html=True)
        else:
            st.markdown("### 🔔 الإشعارات")

        col_a, col_b = st.columns(2)
        if col_a.button("✅ تعليم الكل مقروء", use_container_width=True):
            mark_all_read()
            st.rerun()
        if col_b.button("🗑️ مسح الكل", use_container_width=True):
            clear_all_notifications()
            st.rerun()

        st.markdown("---")

        if not notifications:
            st.info("لا توجد إشعارات")
            return

        for notif in notifications[:50]:  # نعرض آخر 50 إشعار
            icon = NOTIF_ICON.get(notif["action_done"], "🔔")
            is_new = notif["is_read"] == "unread"
            bg_color = "#fff3cd" if is_new else "#f8f9fa"
            border = "2px solid #ffc107" if is_new else "1px solid #dee2e6"
            new_badge = " 🆕" if is_new else ""

            st.markdown(f"""
            <div style='background:{bg_color};border:{border};border-radius:8px;padding:8px 10px;margin-bottom:6px;'>
                <div style='font-size:14px;font-weight:{"bold" if is_new else "normal"};color:#222;'>
                    {icon} {notif["action_done"]}{new_badge}
                </div>
                <div style='font-size:13px;color:#333;margin-top:2px;'>
                    📋 رقم الطلب: <b>{notif["order_id"]}</b>
                </div>
                <div style='font-size:12px;color:#555;'>
                    📌 نوع الشكوى: {notif["comp_type"]}
                </div>
                <div style='font-size:11px;color:#888;margin-top:3px;'>
                    🕐 {notif["timestamp"]}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ======================================================
# ====== مراقبة ReturnWarehouse للإشعارات التلقائية ======
# ======================================================
def normalize_id(val):
    try:
        return str(int(float(val)))
    except:
        return str(val).strip().replace("\xa0", "").replace(" ", "")


def get_last_rw_id():
    try:
        sheet = client.open(SHEET_NAME).worksheet("SystemState")
        data = sheet.get_all_values()
        for row in data:
            if row[0] == "last_rw_id":
                return row[1]
    except:
        pass
    return ""


def set_last_rw_id(val):
    try:
        sheet = client.open(SHEET_NAME).worksheet("SystemState")
        rows = sheet.get_all_values()
        for i, row in enumerate(rows):
            if row[0] == "last_rw_id":
                sheet.update(f"B{i+1}", [[val]])
                return
    except:
        pass


def check_returnwarehouse_new_orders():
    try:
        rw_data = return_warehouse_sheet.get_all_values()

        if len(rw_data) <= 1:
            return

        last_saved_id = normalize_id(get_last_rw_id())

        active_ids = set()
        for sheet_obj in [complaints_sheet, responded_sheet, archive_sheet]:
            try:
                rows = sheet_obj.get_all_values()[1:]
                for row in rows:
                    if row and row[0]:
                        active_ids.add(normalize_id(row[0]))
            except:
                pass

        new_last_id = None

        for row in reversed(rw_data[1:]):
            if not row:
                continue

            order_id = normalize_id(row[0])

            if not order_id:
                continue

            if new_last_id is None:
                new_last_id = order_id

            if order_id == last_saved_id:
                break

            if order_id in active_ids:
                add_notification(
                    order_id=order_id,
                    comp_type="ReturnWarehouse",
                    action_done="طلب جديد في ReturnWarehouse"
                )

        if new_last_id:
            set_last_rw_id(new_last_id)

    except Exception as e:
        st.error(f"❌ خطأ: {e}")

# ====== تشغيل مراقبة ReturnWarehouse ======
check_returnwarehouse_new_orders()

# ====== عرض الإشعارات في الشريط الجانبي ======
render_notifications_sidebar()

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
                "رقم الطلب":  row[0],
                "الفاتورة":   row[1] if len(row) > 1 else "",
                "التاريخ":    row[2] if len(row) > 2 else "",
                "الزبون":     row[3] if len(row) > 3 else "",
                "المبلغ":     row[4] if len(row) > 4 else "",
                "رقم الشحنة": row[5] if len(row) > 5 else "",
                "البيان":     row[6] if len(row) > 6 else ""
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
    xml_str = re.sub(r'xmlns(:\w+)?="[^"]+"', '', xml_str)
    xml_str = re.sub(r'(<\/?)(\w+:)', r'\1', xml_str)
    return xml_str

def extract_reference(tracking_result):
    for ref_tag in ['Reference1','Reference2','Reference3','Reference4','Reference5']:
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
            "Transaction": {"Reference1":"","Reference2":"","Reference3":"","Reference4":"","Reference5":""},
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
                    desc  = last_track.find('UpdateDescription').text if last_track.find('UpdateDescription') is not None else "—"
                    date  = last_track.find('UpdateDateTime').text if last_track.find('UpdateDateTime') is not None else "—"
                    loc   = last_track.find('UpdateLocation').text if last_track.find('UpdateLocation') is not None else "—"
                    reference = extract_reference(last_track)
                    info = f"{desc} بتاريخ {date} في {loc}"
                    if reference:
                        info += f" | الرقم المرجعي: {reference}"
                    return info
        return "❌ لا توجد حالة متاحة"
    except Exception as e:
        return f"خطأ في جلب الحالة: {e}"

@st.cache_data(ttl=300)
def cached_aramex_status(awb):
    if not awb or str(awb).strip() == "":
        return ""
    return get_aramex_status(awb)

# ====== دالة عرض الشكوى مع إشعارات ======
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    restored    = row[5] if len(row) > 5 else ""
    outbound_awb = row[6] if len(row) > 6 else ""
    inbound_awb  = row[7] if len(row) > 7 else ""

    order_status = get_order_status(comp_id)

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        with st.form(key=f"form_{comp_id}_{sheet.title}_{i}"):
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

            new_type   = st.selectbox("✏️ عدل نوع الشكوى", [comp_type] + [t for t in types_list if t != comp_type], index=0)
            new_notes  = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb)
            new_inbound  = st.text_input("✏️ Inbound AWB", value=inbound_awb)

            if new_outbound:
                st.info(f"🚚 Outbound AWB: {new_outbound} | الحالة: {cached_aramex_status(new_outbound)}")
            if new_inbound:
                st.info(f"📦 Inbound AWB: {new_inbound} | الحالة: {cached_aramex_status(new_inbound)}")

            col1, col2, col3, col4 = st.columns(4)
            submitted_save    = col1.form_submit_button("💾 حفظ")
            submitted_delete  = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")
            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ نقل للإجراءات المردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع للنشطة")

            if submitted_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                add_notification(comp_id, new_type, "حفظ شكوى")
                st.success("✅ تم التعديل")

            if submitted_delete:
                if safe_delete(sheet, i):
                    add_notification(comp_id, comp_type, "حذف شكوى")
                    st.warning("🗑️ تم حذف الشكوى")

            if submitted_archive:
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        add_notification(comp_id, new_type, "أرشفة شكوى")
                        st.success("♻️ الشكوى انتقلت للأرشيف")

            if submitted_move:
                if not in_responded:
                    if safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, new_type, "نقل للمردودة")
                            st.success("✅ انتقلت للإجراءات المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, new_type, "رجوع للنشطة")
                            st.success("✅ انتقلت للنشطة")

# ====== العنوان الرئيسي ======
st.title("⚠️ نظام إدارة الشكاوى")

# ====== البحث عن شكوى ======
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
        for i, row in (enumerate(data[1:], start=2) if data else []):
            if len(row) > 0 and str(row[0]) == search_id:
                st.success(f"✅ الشكوى موجودة في {'المردودة' if in_responded else 'الأرشيف' if in_archive else 'النشطة'}")
                render_complaint(sheet_obj, i, row, in_responded=in_responded, in_archive=in_archive)
                found = True
                break
        if found:
            break
    if not found:
        st.error("⚠️ لم يتم العثور على الشكوى")

# ====== تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")
with st.form("add_complaint", clear_on_submit=True):
    comp_id   = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list, index=0)
    notes     = st.text_area("📝 ملاحظات الشكوى")
    action    = st.text_area("✅ الإجراء المتخذ")
    outbound_awb = st.text_input("✏️ Outbound AWB")
    inbound_awb  = st.text_input("✏️ Inbound AWB")
    submitted    = st.form_submit_button("➕ إضافة")

    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            try:
                complaints = complaints_sheet.get_all_records()
            except Exception:
                complaints = []
            try:
                responded = responded_sheet.get_all_records()
            except Exception:
                responded = []
            try:
                archive = archive_sheet.get_all_records()
            except Exception:
                archive = []

            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_active_ids  = [str(c.get("ID","")) for c in complaints] + [str(r.get("ID","")) for r in responded]
            all_archive_ids = [str(a.get("ID","")) for a in archive]

            if comp_id in all_active_ids:
                st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
            elif comp_id in all_archive_ids:
                for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                    if str(row[0]) == comp_id:
                        restored_notes   = row[2] if len(row) > 2 else ""
                        restored_action  = row[3] if len(row) > 3 else ""
                        restored_type    = row[1] if len(row) > 1 else ""
                        restored_outbound = row[6] if len(row) > 6 else ""
                        restored_inbound  = row[7] if len(row) > 7 else ""
                        if safe_append(complaints_sheet, [comp_id, restored_type, restored_notes, restored_action, date_now, "🔄 مسترجعة", restored_outbound, restored_inbound]):
                            if safe_delete(archive_sheet, idx):
                                add_notification(comp_id, restored_type, "رجوع للنشطة")
                                st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                        break
            else:
                if action.strip():
                    if safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb]):
                        add_notification(comp_id, comp_type, "إضافة شكوى جديدة")
                        st.success("✅ تم تسجيل الشكوى في المردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb]):
                        add_notification(comp_id, comp_type, "إضافة شكوى جديدة")
                        st.success("✅ تم تسجيل الشكوى في النشطة")
        else:
            st.error("⚠️ لازم تدخل رقم الشكوى وتختار نوع صحيح")

# ====== عرض الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
active_notes = complaints_sheet.get_all_values()
if len(active_notes) > 1:
    for i, row in enumerate(active_notes[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")

# ====== عرض الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة حسب النوع:")
responded_notes = responded_sheet.get_all_values()
if len(responded_notes) > 1:
    types_in_responded = list({row[1] for row in responded_notes[1:]})
    for complaint_type in types_in_responded:
        with st.expander(f"📌 نوع الشكوى: {complaint_type}"):
            type_rows = [(i, row) for i, row in enumerate(responded_notes[1:], start=2) if row[1] == complaint_type]

            followup_1 = []
            followup_2 = []
            others     = []

            for i, row in type_rows:
                cid          = row[0]
                outbound_awb = row[6] if len(row) > 6 else ""
                inbound_awb  = row[7] if len(row) > 7 else ""
                rw_record    = get_returnwarehouse_record(cid)

                delivered = False
                for awb in [outbound_awb, inbound_awb]:
                    if awb and "Delivered" in cached_aramex_status(awb):
                        delivered = True
                        break

                if delivered and rw_record:
                    followup_2.append((i, row))
                elif delivered and not rw_record:
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

# ====== قسم معلق أرامكس ======
st.markdown("---")
st.header("🚚 معلق ارامكس")
with st.form("add_aramex", clear_on_submit=True):
    order_id = st.text_input("🔢 رقم الطلب")
    status   = st.text_input("📌 الحالة")
    action   = st.text_area("✅ الإجراء المتخذ")
    submitted = st.form_submit_button("➕ إضافة")
    if submitted:
        if order_id.strip() and status.strip() and action.strip():
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if safe_append(aramex_sheet, [order_id, status, date_now, action]):
                add_notification(order_id, "معلق أرامكس", "إضافة معلق أرامكس")
                st.success("✅ تم تسجيل الطلب")
            else:
                st.error("❌ فشل في تسجيل الطلب")
        else:
            st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

# ====== عرض معلق أرامكس ======
st.subheader("📋 قائمة الطلبات المعلقة")
aramex_pending = aramex_sheet.get_all_values()
if len(aramex_pending) > 1:
    for i, row in enumerate(aramex_pending[1:], start=2):
        while len(row) < 4:
            row.append("")
        order_id   = row[0]
        status     = row[1]
        date_added = row[2]
        action     = row[3]
        with st.expander(f"📦 طلب {order_id}"):
            st.write(f"📌 الحالة الحالية: {status}")
            st.write(f"✅ الإجراء الحالي: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            with st.form(key=f"form_aramex_{order_id}_{i}"):
                new_status = st.text_input("✏️ عدل الحالة", value=status)
                new_action = st.text_area("✏️ عدل الإجراء", value=action)
                col1, col2, col3 = st.columns(3)
                submitted_save    = col1.form_submit_button("💾 حفظ")
                submitted_delete  = col2.form_submit_button("🗑️ حذف")
                submitted_archive = col3.form_submit_button("📦 أرشفة")
                if submitted_save:
                    if safe_update(aramex_sheet, f"B{i}", [[new_status]]) and safe_update(aramex_sheet, f"D{i}", [[new_action]]):
                        add_notification(order_id, "معلق أرامكس", "تعديل معلق أرامكس")
                        st.success("✅ تم تعديل الطلب")
                if submitted_delete:
                    if safe_delete(aramex_sheet, i):
                        add_notification(order_id, "معلق أرامكس", "حذف شكوى")
                        st.warning("🗑️ تم حذف الطلب")
                if submitted_archive:
                    if safe_append(aramex_archive, [order_id, new_status, date_added, new_action]):
                        if safe_delete(aramex_sheet, i):
                            add_notification(order_id, "معلق أرامكس", "أرشفة معلق أرامكس")
                            st.success("♻️ تم أرشفة الطلب")
else:
    st.info("لا توجد شكاوى أرامكس معلقة.")

# ====== أرشيف أرامكس ======
st.markdown("---")
st.header("📦 أرشيف أرامكس:")
aramex_archived = aramex_archive.get_all_values()
if len(aramex_archived) > 1:
    for i, row in enumerate(aramex_archived[1:], start=2):
        while len(row) < 4:
            row.append("")
        order_id   = row[0]
        status     = row[1]
        date_added = row[2]
        action     = row[3]
        with st.expander(f"📦 أرشيف طلب {order_id}"):
            st.write(f"📌 الحالة عند الأرشفة: {status}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ الإضافة: {date_added}")
            col1, col2 = st.columns(2)
            if col1.button(f"⬅️ إرجاع {order_id} إلى معلق ارامكس", key=f"ret_{order_id}_{i}"):
                if safe_append(aramex_sheet, [order_id, status, date_added, action]):
                    if safe_delete(aramex_archive, i):
                        add_notification(order_id, "معلق أرامكس", "رجوع للنشطة")
                        st.success(f"✅ تم إعادة {order_id} لمعلق ارامكس")
            if col2.button(f"🗑️ حذف {order_id} من الأرشيف", key=f"del_{order_id}_{i}"):
                if safe_delete(aramex_archive, i):
                    add_notification(order_id, "معلق أرامكس", "حذف شكوى")
                    st.warning(f"🗑️ تم حذف {order_id} من أرشيف أرامكس")
else:
    st.info("لا توجد شكاوى أرامكس مؤرشفة.")

st.caption("التغييرات تحفظ في Google Sheets عند كل عملية. الإشعارات تظهر في الشريط الجانبي وتتحدث كل دقيقة.")
