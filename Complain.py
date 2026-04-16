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

st_autorefresh(interval=1200000, key="auto_refresh")

st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")

# ==============================================================
# 🔌 الاتصال بجوجل شيت
# ==============================================================

@st.cache_resource
def _get_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gspread_client = gspread.authorize(creds)

    SHEET_NAME = "Complaints"
    sheet_titles = [
        "Complaints", "Responded", "Archive", "Types",
        "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number",
        "Notifications", "RWNotifications",
        "RWSnapshots",
    ]
    d = {}
    ss = gspread_client.open(SHEET_NAME)
    for title in sheet_titles:
        try:
            d[title] = ss.worksheet(title)
        except Exception:
            d[title] = ss.add_worksheet(title=title, rows="2000", cols="10")
    return d


sheets_dict            = _get_sheets()
complaints_sheet       = sheets_dict["Complaints"]
responded_sheet        = sheets_dict["Responded"]
archive_sheet          = sheets_dict["Archive"]
types_sheet            = sheets_dict["Types"]
aramex_sheet           = sheets_dict["معلق ارامكس"]
aramex_archive         = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet     = sheets_dict["Order Number"]
notifications_sheet    = sheets_dict["Notifications"]
rw_notif_sheet         = sheets_dict["RWNotifications"]
rw_snapshots_sheet     = sheets_dict["RWSnapshots"]


# ==============================================================
# 📸 نظام RW Snapshots — بدون cache عشان المقارنة دايماً دقيقة
# ==============================================================

def _load_rw_snapshots():
    """قراءة مباشرة من الشيت بدون cache — ضروري عشان المقارنة تكون صح"""
    try:
        data = rw_snapshots_sheet.get_all_values()
        result = {}
        row_index = {}
        for idx, row in enumerate(data[1:], start=2):
            if len(row) >= 2:
                result[row[0]] = row[1]
                row_index[row[0]] = idx
        return result, row_index
    except Exception:
        return {}, {}


def rw_snap_get(key: str):
    cache, _ = _load_rw_snapshots()
    return cache.get(key, None)


def rw_snap_set(key: str, value: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _, row_index = _load_rw_snapshots()
    try:
        idx = row_index.get(key)
        if idx:
            rw_snapshots_sheet.update(f"B{idx}", [[value]])
            rw_snapshots_sheet.update(f"C{idx}", [[now]])
        else:
            rw_snapshots_sheet.append_row([key, value, now])
    except Exception:
        pass


# ==============================================================
# 🛡️ Guard — يمنع كتابة نفس الإشعار مرتين في نفس الـ session
# ==============================================================

def _init_session():
    if "_notif_written" not in st.session_state:
        st.session_state["_notif_written"] = {}
    if "_new_notif_this_run" not in st.session_state:
        st.session_state["_new_notif_this_run"] = False

_init_session()


def _was_notif_written_recently(key: str, minutes: int = 5) -> bool:
    guard = st.session_state["_notif_written"]
    if key not in guard:
        return False
    elapsed = (datetime.now() - guard[key]).total_seconds() / 60
    return elapsed < minutes


def _mark_notif_written(key: str):
    st.session_state["_notif_written"][key] = datetime.now()


# ==============================================================
# 🔔 دوال كتابة الإشعارات
# ==============================================================

def add_notification(order_id, section, message, comp_type=""):
    guard_key = f"gen|{order_id}|{section}|{message}"
    if _was_notif_written_recently(guard_key):
        return
    _mark_notif_written(guard_key)
    try:
        notifications_sheet.append_row([
            str(order_id), str(comp_type), str(section), str(message),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "NEW"
        ])
        get_notifications.clear()
        st.session_state["_new_notif_this_run"] = True
    except Exception:
        pass


def add_rw_notification(order_id, comp_type, before, after):
    guard_key = f"rw|{order_id}|{before[:30]}|{after[:30]}"
    if _was_notif_written_recently(guard_key, minutes=10):
        return

    try:
        recent_rows = rw_notif_sheet.get_all_values()
        cutoff_ts = datetime.now().timestamp() - 600

        for row in recent_rows[-30:]:
            if len(row) >= 6 and str(row[0]) == str(order_id) \
               and row[3][:30] == before[:30] \
               and row[4][:30] == after[:30]:

                try:
                    row_time = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S").timestamp()
                    if row_time > cutoff_ts:
                        return
                except Exception:
                    pass
    except Exception:
        pass

    _mark_notif_written(guard_key)

    try:
        rw_notif_sheet.append_row([
            str(order_id), str(comp_type), "ReturnWarehouse", str(before), str(after),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "NEW"
        ])
        get_rw_notifications.clear()
        st.session_state["_new_notif_this_run"] = True
    except Exception:
        pass


# ==============================================================
# 🔄 كشف تغييرات ReturnWarehouse
#
# المنطق:
#   - مفيش سناب محفوظ  → احفظ الحالية بدون إشعار (أول مرة)
#   - سناب محفوظ وزي بعض → لا تعمل شيء
#   - current_str فاضي  → تجاهل (جلب ناقص مش اختفاء حقيقي) ✅ إصلاح
#   - سناب محفوظ واختلف → إشعار + حدّث السناب
# ==============================================================

def _rw_to_str(rw_record) -> str:
    if not rw_record:
        return ""
    return (
        f"{rw_record.get('رقم الطلب','')}|"
        f"{rw_record.get('الفاتورة','')}|"
        f"{rw_record.get('التاريخ','')}|"
        f"{rw_record.get('الزبون','')}|"
        f"{rw_record.get('المبلغ','')}|"
        f"{rw_record.get('رقم الشحنة','')}|"
        f"{rw_record.get('البيان','')}"
    )


def check_and_notify_rw_change(order_id, comp_type, rw_record):
    snap_key    = f"rw__{order_id}"
    current_str = _rw_to_str(rw_record)
    prev        = rw_snap_get(snap_key)

    # أول مرة نشوف الطلب ده → احفظ بدون إشعار
    if prev is None:
        rw_snap_set(snap_key, current_str)
        return

    # مفيش تغيير → لا تعمل شيء
    if prev == current_str:
        return

    # ✅ الإصلاح الرئيسي: لو current_str فاضي → جلب ناقص مش اختفاء حقيقي، تجاهل
    if not current_str:
        return

    # في تغيير حقيقي → إشعار + تحديث السناب
    if not prev and current_str:
        add_rw_notification(order_id, comp_type, "لم يكن موجوداً في المخزن", current_str)
    else:
        add_rw_notification(order_id, comp_type, prev, current_str)

    rw_snap_set(snap_key, current_str)


# ==============================================================
# 📊 جلب الإشعارات
# ==============================================================

@st.cache_data(ttl=10)
def get_notifications():
    try:
        data = notifications_sheet.get_all_values()
        return data[1:] if len(data) > 1 else []
    except Exception:
        return []


@st.cache_data(ttl=10)
def get_rw_notifications():
    try:
        data = rw_notif_sheet.get_all_values()
        return data[1:] if len(data) > 1 else []
    except Exception:
        return []


# ==============================================================
# ✔️ تعليم المقروءة / حذف المقروءة
# ==============================================================

def _mark_all_read(sheet, status_col_index: int):
    try:
        data = sheet.get_all_values()
        col = chr(ord('A') + status_col_index)
        updates = []
        for idx, row in enumerate(data[1:], start=2):
            if len(row) > status_col_index and row[status_col_index] == "NEW":
                updates.append({"range": f"{col}{idx}", "values": [["READ"]]})
        if updates:
            sheet.batch_update(updates)
        get_notifications.clear()
        get_rw_notifications.clear()
    except Exception:
        pass


def _delete_read_rows(sheet, status_col_index: int):
    try:
        data = sheet.get_all_values()
        to_del = [
            idx + 2
            for idx, row in enumerate(data[1:])
            if len(row) > status_col_index and row[status_col_index] == "READ"
        ]
        for row_idx in reversed(to_del):
            sheet.delete_rows(row_idx)
        get_notifications.clear()
        get_rw_notifications.clear()
    except Exception:
        pass


# ==============================================================
# 🎨 CSS الإشعارات
# ==============================================================

NOTIFICATION_CSS = """
<style>
.notif-card-new {
    background: linear-gradient(135deg, #1e3a5f, #0f2745);
    border-right: 4px solid #3498db;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    direction: rtl;
    box-shadow: 0 2px 8px rgba(52,152,219,0.18);
}
.notif-card-rw {
    background: linear-gradient(135deg, #3a2a1a, #2b1a0d);
    border-right: 4px solid #f39c12;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    direction: rtl;
    box-shadow: 0 2px 8px rgba(243,156,18,0.18);
}
.notif-order { display:inline-block; background:rgba(243,156,18,0.2); color:#f39c12; border-radius:6px; padding:1px 8px; font-size:12px; font-weight:bold; margin-left:4px; }
.notif-type  { display:inline-block; background:rgba(52,152,219,0.2); color:#7ec8e3; border-radius:6px; padding:1px 8px; font-size:12px; margin-left:4px; }
.notif-msg   { color:#ecf0f1; font-size:14px; margin:5px 0 3px 0; }
.notif-before { color:#e74c3c; font-size:12px; margin:2px 0; }
.notif-after  { color:#2ecc71; font-size:12px; margin:2px 0; }
.notif-time  { color:#7f8c8d; font-size:11px; }
.notif-badge {
    display:inline-flex; align-items:center; justify-content:center;
    background:#e74c3c; color:white; border-radius:50%;
    width:22px; height:22px; font-size:12px; font-weight:bold;
    animation: blink 1.4s infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.5} }
</style>
"""


# ==============================================================
# 🖼️ رسم بطاقات الإشعارات
# ==============================================================

def _render_general_notif(n):
    while len(n) < 6:
        n.append("")
    order_id, comp_type, section, message, date_str, _ = n[:6]
    ob = f'<span class="notif-order">#{order_id}</span>' if order_id else ''
    tb = f'<span class="notif-type">{comp_type}</span>'  if comp_type else ''
    sb = f'<span style="display:inline-block;background:rgba(155,89,182,0.2);color:#bb8fce;border-radius:6px;padding:1px 8px;font-size:12px;">📍 {section}</span>' if section else ''
    st.markdown(f"""
    <div class="notif-card-new">
        <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">
            <span style="font-size:15px;">🔵</span>{ob}{tb}{sb}
        </div>
        <div class="notif-msg">{message}</div>
        <div class="notif-time">⏰ {date_str}</div>
    </div>""", unsafe_allow_html=True)


def _render_rw_notif(n):
    while len(n) < 7:
        n.append("")
    order_id, comp_type, _, before, after, date_str, _ = n[:7]
    ob = f'<span class="notif-order">#{order_id}</span>' if order_id else ''
    tb = f'<span class="notif-type">{comp_type}</span>'  if comp_type else ''
    bs = before[:90] + ("…" if len(before) > 90 else "")
    af = after[:90]  + ("…" if len(after)  > 90 else "")
    st.markdown(f"""
    <div class="notif-card-rw">
        <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">
            <span style="font-size:15px;">📦</span>{ob}{tb}
            <span style="display:inline-block;background:rgba(155,89,182,0.2);color:#bb8fce;border-radius:6px;padding:1px 8px;font-size:12px;">🏭 ReturnWarehouse</span>
        </div>
        <div class="notif-msg">تغيّر في سجل المخزن</div>
        <div class="notif-before">قبل: {bs}</div>
        <div class="notif-after">بعد: {af}</div>
        <div class="notif-time">⏰ {date_str}</div>
    </div>""", unsafe_allow_html=True)


# ==============================================================
# 🔔 لوحة الإشعارات — بدون أرامكس
# ==============================================================

def render_notifications_panel():
    st.markdown(NOTIFICATION_CSS, unsafe_allow_html=True)

    all_gen = get_notifications()
    all_rw  = get_rw_notifications()

    new_gen = [n for n in all_gen if len(n) > 5 and n[5] == "NEW"]
    new_rw  = [n for n in all_rw  if len(n) > 6 and n[6] == "NEW"]
    total   = len(new_gen) + len(new_rw)

    badge = (
        f'<span class="notif-badge">{total}</span>' if total
        else '<span style="color:#2ecc71;font-size:13px;">✔ لا يوجد جديد</span>'
    )
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;direction:rtl;margin-bottom:8px;">'
        f'<span style="font-size:24px;">🔔</span>'
        f'<span style="font-size:18px;font-weight:bold;color:#ecf0f1;">الإشعارات</span>'
        f'{badge}</div>', unsafe_allow_html=True
    )

    col_gen, col_rw = st.columns(2)

    with col_gen:
        with st.expander(f"📬 عامة ({len(new_gen)} جديد)", expanded=len(new_gen) > 0):
            if new_gen:
                c1, c2 = st.columns(2)
                if c1.button("✔️ تعليم كمقروء", key="read_gen"):
                    _mark_all_read(notifications_sheet, 5)
                    st.rerun()
                if c2.button("🗑️ حذف المقروءة", key="del_gen"):
                    _delete_read_rows(notifications_sheet, 5)
                    st.rerun()
                for n in reversed(new_gen[-60:]):
                    _render_general_notif(n)
            else:
                st.info("لا توجد إشعارات جديدة.")

    with col_rw:
        with st.expander(f"📦 المخزن ({len(new_rw)} جديد)", expanded=len(new_rw) > 0):
            if new_rw:
                c1, c2 = st.columns(2)
                if c1.button("✔️ تعليم كمقروء", key="read_rw"):
                    _mark_all_read(rw_notif_sheet, 6)
                    st.rerun()
                if c2.button("🗑️ حذف المقروءة", key="del_rw"):
                    _delete_read_rows(rw_notif_sheet, 6)
                    st.rerun()
                for n in reversed(new_rw[-60:]):
                    _render_rw_notif(n)
            else:
                st.info("لا توجد تغييرات مخزن.")


# ==============================================================
# ✅ لوحة الإشعارات في الأعلى
# ==============================================================

st.title("⚠️ نظام إدارة الشكاوى")
render_notifications_panel()
st.markdown("---")


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
@st.cache_data(ttl=120)
def _load_types():
    try:
        return [row[0] for row in types_sheet.get_all_values()[1:] if row and row[0]]
    except Exception:
        return []

types_list = _load_types()


# ====== ReturnWarehouse ======
@st.cache_data(ttl=30)
def get_return_warehouse_data():
    try:
        return return_warehouse_sheet.get_all_values()[1:]
    except Exception:
        return []


def get_returnwarehouse_record(order_id):
    for row in get_return_warehouse_data():
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


# ====== Order Number ======
@st.cache_data(ttl=120)
def _load_order_numbers():
    try:
        return order_number_sheet.get_all_values()[1:]
    except Exception:
        return []


def get_order_status(order_id):
    for row in _load_order_numbers():
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.strip().lower() == "aramex":
                return "📦 مشحونة مع أرامكس الطلب الاساسي"
            elif delegate.strip():
                return f"الطلب الاساسي🚚 مشحونة مع مندوب الرياض ({delegate})"
            else:
                return "الطلب الاساسي⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"


# ====== Aramex API ======
client_info = {
    "UserName":           st.secrets.get("aramex_username", "fitnessworld525@gmail.com"),
    "Password":           st.secrets.get("aramex_password", "Aa12345678@"),
    "Version":            "v1",
    "AccountNumber":      "71958996",
    "AccountPin":         "657448",
    "AccountEntity":      "RUH",
    "AccountCountryCode": "SA"
}


def remove_xml_namespaces(xml_str):
    xml_str = re.sub(r'xmlns(:\w+)?="[^"]+"', '', xml_str)
    xml_str = re.sub(r'(</?)\w+:', r'\1', xml_str)
    return xml_str


def extract_reference(tracking_result):
    for ref_tag in ['Reference1', 'Reference2', 'Reference3', 'Reference4', 'Reference5']:
        ref_elem = tracking_result.find(ref_tag)
        if ref_elem is not None and ref_elem.text and ref_elem.text.strip():
            return ref_elem.text.strip()
    return ""


def get_aramex_status(awb_number):
    try:
        payload = {
            "ClientInfo": client_info,
            "Shipments": [awb_number],
            "Transaction": {"Reference1": "", "Reference2": "", "Reference3": "",
                            "Reference4": "", "Reference5": ""},
            "LabelInfo": None
        }
        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        response = requests.post(url, json=payload,
                                 headers={"Content-Type": "application/json"}, timeout=10)
        if response.status_code != 200:
            return f"❌ فشل الاتصال - كود {response.status_code}"

        xml_content = remove_xml_namespaces(response.content.decode('utf-8'))
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
                    last = sorted(
                        tracks,
                        key=lambda tr: tr.find('UpdateDateTime').text
                            if tr.find('UpdateDateTime') is not None else '',
                        reverse=True
                    )[0]
                    desc = last.find('UpdateDescription').text \
                           if last.find('UpdateDescription') is not None else "—"
                    date = last.find('UpdateDateTime').text \
                           if last.find('UpdateDateTime') is not None else "—"
                    loc  = last.find('UpdateLocation').text \
                           if last.find('UpdateLocation') is not None else "—"
                    ref  = extract_reference(last)
                    info = f"{desc} بتاريخ {date} في {loc}"
                    if ref:
                        info += f" | الرقم المرجعي: {ref}"
                    return info
        return "❌ لا توجد حالة متاحة"
    except requests.exceptions.Timeout:
        return "❌ انتهت مهلة الاتصال بأرامكس"
    except Exception as e:
        return f"❌ خطأ في جلب الحالة: {e}"


@st.cache_data(ttl=300)
def cached_aramex_status(awb):
    if not awb or not str(awb).strip():
        return ""
    return get_aramex_status(awb)


def _is_error_status(value) -> bool:
    if not value or not str(value).strip():
        return True
    v = str(value)
    markers = ["خطأ", "❌", "error", "Error", "unbound", "failed", "Failed",
               "فشل الاتصال", "لا توجد حالة", "لا توجد", "timeout", "Timeout"]
    return any(m.lower() in v.lower() for m in markers)


# ==============================================================
# 🖼️ دالة عرض الشكوى
# ==============================================================

def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id      = row[0]
    comp_type    = row[1]
    notes        = row[2]
    action       = row[3]
    date_added   = row[4]
    restored     = row[5]
    outbound_awb = row[6]
    inbound_awb  = row[7]

    order_status = get_order_status(comp_id)

    with st.expander(f"🆔 {comp_id} | 📌 {comp_type} | 📅 {date_added} {restored} | {order_status}"):
        with st.form(key=f"form_{comp_id}_{sheet.title}_{i}"):

            st.write(f"📌 النوع الحالي: {comp_type}")
            st.write(f"📝 الملاحظات: {notes}")
            st.write(f"✅ الإجراء: {action}")
            st.caption(f"📅 تاريخ التسجيل: {date_added}")

            # ── ReturnWarehouse ──
            rw_record = get_returnwarehouse_record(comp_id)
            if rw_record:
                st.info(
                    f"📦 سجل من ReturnWarehouse:\n"
                    f"رقم الطلب: {rw_record['رقم الطلب']}  |  "
                    f"الفاتورة: {rw_record['الفاتورة']}  |  "
                    f"التاريخ: {rw_record['التاريخ']}\n"
                    f"الزبون: {rw_record['الزبون']}  |  "
                    f"المبلغ: {rw_record['المبلغ']}  |  "
                    f"رقم الشحنة: {rw_record['رقم الشحنة']}\n"
                    f"البيان: {rw_record['البيان']}"
                )

            # ── كشف تغييرات المخزن ──
            check_and_notify_rw_change(comp_id, comp_type, rw_record)

            new_type     = st.selectbox("✏️ عدل نوع الشكوى",
                                        [comp_type] + [t for t in types_list if t != comp_type])
            new_notes    = st.text_area("✏️ عدل الملاحظات",  value=notes)
            new_action   = st.text_area("✏️ عدل الإجراء",    value=action)
            new_outbound = st.text_input("✏️ Outbound AWB",  value=outbound_awb)
            new_inbound  = st.text_input("✏️ Inbound AWB",   value=inbound_awb)

            # ── أرامكس - عرض الحالة فقط بدون إشعارات ──
            if new_outbound.strip():
                s_out = cached_aramex_status(new_outbound.strip())
                if s_out and not _is_error_status(s_out):
                    st.info(f"🚚 Outbound: {new_outbound} | {s_out}")
                elif s_out:
                    st.warning(f"⚠️ Outbound: {s_out}")

            if new_inbound.strip():
                s_in = cached_aramex_status(new_inbound.strip())
                if s_in and not _is_error_status(s_in):
                    st.info(f"📦 Inbound: {new_inbound} | {s_in}")
                elif s_in:
                    st.warning(f"⚠️ Inbound: {s_in}")

            col1, col2, col3, col4 = st.columns(4)
            btn_save    = col1.form_submit_button("💾 حفظ")
            btn_delete  = col2.form_submit_button("🗑️ حذف")
            btn_archive = col3.form_submit_button("📦 أرشفة")
            btn_move    = col4.form_submit_button(
                "➡️ نقل للمردودة" if not in_responded else "⬅️ رجوع للنشطة"
            )

            if btn_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                changes = []
                if new_type != comp_type:
                    changes.append(f"النوع: {comp_type} ← {new_type}")
                if new_notes != notes:
                    changes.append(f"ملاحظات: {new_notes[:60]}")
                if new_action != action:
                    changes.append(f"إجراء: {new_action[:60]}")
                msg = "تم تعديل الشكوى" + (f" | {' | '.join(changes)}" if changes else "")
                add_notification(comp_id, "تعديل", msg, comp_type=new_type)
                st.success("✅ تم التعديل")

            if btn_delete:
                if safe_delete(sheet, i):
                    add_notification(comp_id, "حذف", "تم حذف الشكوى", comp_type=comp_type)
                    st.warning("🗑️ تم حذف الشكوى")

            if btn_archive:
                if safe_append(archive_sheet,
                               [comp_id, new_type, new_notes, new_action,
                                date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        add_notification(comp_id, "الأرشيف", "تم أرشفة الشكوى",
                                         comp_type=new_type)
                        st.success("♻️ انتقلت للأرشيف")

            if btn_move:
                if not in_responded:
                    if safe_append(responded_sheet,
                                   [comp_id, new_type, new_notes, new_action,
                                    date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            move_msg = "تم نقل الشكوى للمردودة"
                            if new_action.strip():
                                move_msg += f" | الإجراء: {new_action[:80]}"
                            add_notification(comp_id, "المردودة", move_msg, comp_type=new_type)
                            st.success("✅ انتقلت للمردودة")
                else:
                    if safe_append(complaints_sheet,
                                   [comp_id, new_type, new_notes, new_action,
                                    date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            add_notification(comp_id, "النشطة",
                                             "تم إرجاع الشكوى للنشطة", comp_type=new_type)
                            st.success("✅ انتقلت للنشطة")


# ====== 🔍 البحث ======
st.header("🔍 البحث عن شكوى")
search_id = st.text_input("أدخل رقم الشكوى للبحث")

if search_id.strip():
    found = False
    for sheet_obj, in_resp, in_arch in [
        (complaints_sheet, False, False),
        (responded_sheet,  True,  False),
        (archive_sheet,    False, True)
    ]:
        try:
            data = sheet_obj.get_all_values()
        except Exception:
            data = []
        rows_iter = enumerate(data[1:], start=2) if data else []
        for i, row in rows_iter:
            if len(row) > 0 and str(row[0]) == search_id.strip():
                loc = ("النشطة" if not in_resp and not in_arch
                       else "المردودة" if in_resp else "الأرشيف")
                st.success(f"✅ الشكوى موجودة في {loc}")
                add_notification(search_id, "بحث", f"تم فتح الشكوى من {loc}",
                                 comp_type=row[1] if len(row) > 1 else "")
                render_complaint(sheet_obj, i, row, in_responded=in_resp, in_archive=in_arch)
                found = True
                break
        if found:
            break
    if not found:
        st.error("⚠️ لم يتم العثور على الشكوى")


# ====== ➕ تسجيل شكوى جديدة ======
st.header("➕ تسجيل شكوى جديدة")

with st.form("add_complaint", clear_on_submit=True):
    comp_id      = st.text_input("🆔 رقم الشكوى")
    comp_type    = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list)
    notes        = st.text_area("📝 ملاحظات الشكوى")
    action       = st.text_area("✅ الإجراء المتخذ")
    outbound_awb = st.text_input("✏️ Outbound AWB")
    inbound_awb  = st.text_input("✏️ Inbound AWB")
    submitted    = st.form_submit_button("➕ إضافة")

    if submitted:
        if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_active, all_archive = [], []
            try:
                all_active  = [str(r[0]) for r in complaints_sheet.get_all_values()[1:] if r] + \
                               [str(r[0]) for r in responded_sheet.get_all_values()[1:]  if r]
                all_archive = [str(r[0]) for r in archive_sheet.get_all_values()[1:]     if r]
            except Exception:
                pass

            if comp_id in all_active:
                st.error("⚠️ الشكوى موجودة بالفعل")
                add_notification(comp_id, "إضافة", "محاولة إضافة مكررة", comp_type=comp_type)
            elif comp_id in all_archive:
                archive_all = archive_sheet.get_all_values()
                for idx, row in enumerate(archive_all[1:], start=2):
                    if str(row[0]) == comp_id:
                        if safe_append(complaints_sheet,
                                       [comp_id,
                                        row[1] if len(row) > 1 else "",
                                        row[2] if len(row) > 2 else "",
                                        row[3] if len(row) > 3 else "",
                                        date_now, "🔄 مسترجعة",
                                        row[6] if len(row) > 6 else "",
                                        row[7] if len(row) > 7 else ""]):
                            if safe_delete(archive_sheet, idx):
                                st.success("♻️ تم استرجاع الشكوى من الأرشيف")
                                add_notification(comp_id, "استرجاع",
                                                 "تم استرجاع الشكوى من الأرشيف",
                                                 comp_type=row[1] if len(row) > 1 else "")
                        break
            else:
                if action.strip():
                    if safe_append(responded_sheet,
                                   [comp_id, comp_type, notes, action,
                                    date_now, "", outbound_awb, inbound_awb]):
                        st.success("✅ تم تسجيل الشكوى في المردودة")
                        add_notification(comp_id, "إضافة",
                                         f"تم تسجيل الشكوى في المردودة | الإجراء: {action[:80]}",
                                         comp_type=comp_type)
                else:
                    if safe_append(complaints_sheet,
                                   [comp_id, comp_type, notes, "",
                                    date_now, "", outbound_awb, inbound_awb]):
                        st.success("✅ تم تسجيل الشكوى في النشطة")
                        add_notification(comp_id, "إضافة",
                                         "تم تسجيل الشكوى في النشطة", comp_type=comp_type)
        else:
            st.error("⚠️ لازم تدخل رقم الشكوى وتختار النوع")


# ====== 📋 الشكاوى النشطة ======
st.header("📋 الشكاوى النشطة:")
active_data = complaints_sheet.get_all_values()
if len(active_data) > 1:
    for i, row in enumerate(active_data[1:], start=2):
        render_complaint(complaints_sheet, i, row)
else:
    st.info("لا توجد شكاوى نشطة حالياً.")


# ====== ✅ الإجراءات المردودة ======
st.header("✅ الإجراءات المردودة حسب النوع:")
responded_data = responded_sheet.get_all_values()

if len(responded_data) > 1:
    types_in = list({row[1] for row in responded_data[1:] if row})
    for ctype in types_in:
        with st.expander(f"📌 نوع الشكوى: {ctype}"):
            rows_typed = [(i, row) for i, row in enumerate(responded_data[1:], start=2)
                          if row[1] == ctype]
            f1, f2, others = [], [], []
            for i, row in rows_typed:
                ob = row[6] if len(row) > 6 else ""
                ib = row[7] if len(row) > 7 else ""
                rw = get_returnwarehouse_record(row[0])
                delivered = any(
                    awb and "Delivered" in cached_aramex_status(awb)
                    for awb in [ob, ib] if awb
                )
                if delivered and rw:
                    f2.append((i, row))
                elif delivered:
                    f1.append((i, row))
                else:
                    others.append((i, row))

            if f1:
                with st.expander("📋 جاهز للمتابعة 1"):
                    for i, row in f1:
                        render_complaint(responded_sheet, i, row, in_responded=True)
            if f2:
                with st.expander("📋 جاهز للمتابعة 2"):
                    for i, row in f2:
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
    a_order  = st.text_input("🔢 رقم الطلب")
    a_status = st.text_input("📌 الحالة")
    a_action = st.text_area("✅ الإجراء المتخذ")
    a_submit = st.form_submit_button("➕ إضافة")
    if a_submit:
        if a_order.strip() and a_status.strip() and a_action.strip():
            if safe_append(aramex_sheet,
                           [a_order, a_status,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), a_action]):
                st.success("✅ تم تسجيل الطلب")
                add_notification(a_order, "أرامكس", "تم إضافة طلب جديد في معلق أرامكس")
        else:
            st.error("⚠️ لازم تدخل كل البيانات")

st.subheader("📋 قائمة الطلبات المعلقة")
aramex_pending = aramex_sheet.get_all_values()

if len(aramex_pending) > 1:
    for i, row in enumerate(aramex_pending[1:], start=2):
        while len(row) < 4:
            row.append("")
        p_id, p_status, p_date, p_action = row[:4]

        with st.expander(f"📦 طلب {p_id}"):
            st.write(f"📌 الحالة: {p_status}")
            st.write(f"✅ الإجراء: {p_action}")
            st.caption(f"📅 {p_date}")

            cur = cached_aramex_status(p_id)
            if cur and not _is_error_status(cur):
                st.info(f"🚚 حالة أرامكس الآن: {cur}")
            elif cur:
                st.warning(f"⚠️ {cur}")

            with st.form(key=f"aramex_{p_id}_{i}"):
                ns = st.text_input("✏️ تعديل الحالة",  value=p_status)
                na = st.text_area("✏️ تعديل الإجراء", value=p_action)
                c1, c2, c3 = st.columns(3)
                b_save = c1.form_submit_button("💾 حفظ")
                b_del  = c2.form_submit_button("🗑️ حذف")
                b_arch = c3.form_submit_button("📦 أرشفة")

                if b_save:
                    safe_update(aramex_sheet, f"B{i}", [[ns]])
                    safe_update(aramex_sheet, f"D{i}", [[na]])
                    add_notification(p_id, "أرامكس",
                                     f"تم تعديل الطلب | الإجراء: {na[:80]}")
                    st.success("تم التعديل")

                if b_del:
                    if safe_delete(aramex_sheet, i):
                        add_notification(p_id, "أرامكس", "تم حذف الطلب")
                        st.warning("تم الحذف")

                if b_arch:
                    if safe_append(aramex_archive, [p_id, ns, p_date, na]):
                        if safe_delete(aramex_sheet, i):
                            add_notification(p_id, "أرامكس", "تم أرشفة الطلب")
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
        a_id, a_st, a_dt, a_ac = row[:4]
        with st.expander(f"📦 أرشيف {a_id}"):
            st.write(f"📌 الحالة: {a_st}")
            st.write(f"✅ الإجراء: {a_ac}")
            st.caption(f"📅 {a_dt}")
            c1, c2 = st.columns(2)
            if c1.button(f"⬅️ إرجاع {a_id}", key=f"ret_{i}"):
                if safe_append(aramex_sheet, [a_id, a_st, a_dt, a_ac]):
                    if safe_delete(aramex_archive, i):
                        add_notification(a_id, "أرامكس", "تم إرجاع الطلب من الأرشيف")
            if c2.button(f"🗑️ حذف {a_id}", key=f"del_{i}"):
                if safe_delete(aramex_archive, i):
                    add_notification(a_id, "أرامكس", "تم حذف الطلب من الأرشيف")
else:
    st.info("لا توجد بيانات في الأرشيف")


# ==============================================================
# ✅ rerun لو في إشعار جديد كُتب في هذا الـ run
# ==============================================================
if st.session_state.get("_new_notif_this_run", False):
    st.session_state["_new_notif_this_run"] = False
    st.rerun()


st.caption("⚠️ النظام يحفظ تلقائيًا في Google Sheets + إشعارات لحظية داخل التطبيق")
