# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import gspread.exceptions
import requests
import re
import json
from streamlit_autorefresh import st_autorefresh

# ================== إعداد الصفحة (لازم أول شيء) ==================
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")

# ================== تحديث تلقائي ==================
st_autorefresh(interval=1200000, key="auto_refresh")

# ================== الاتصال بجوجل شيت ==================
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "Complaints"
sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس", "ReturnWarehouse", "Order Number"
]

sheets_dict = {}
ss = client.open(SHEET_NAME)

for title in sheet_titles:
    try:
        sheets_dict[title] = ss.worksheet(title)
    except Exception:
        sheets_dict[title] = ss.add_worksheet(title=title, rows="1000", cols="20")

complaints_sheet = sheets_dict["Complaints"]
responded_sheet = sheets_dict["Responded"]
archive_sheet = sheets_dict["Archive"]
types_sheet = sheets_dict["Types"]
aramex_sheet = sheets_dict["معلق ارامكس"]
aramex_archive = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ================== Safe functions ==================
def safe_append(sheet, row):
    for _ in range(3):
        try:
            sheet.append_row(row)
            return True
        except:
            time.sleep(1)
    return False

def safe_update_cell(sheet, row, col, value):
    for _ in range(3):
        try:
            sheet.update_cell(row, col, value)
            return True
        except:
            time.sleep(1)
    return False

def safe_delete(sheet, row):
    for _ in range(3):
        try:
            sheet.delete_rows(row)
            return True
        except:
            time.sleep(1)
    return False

# ================== تحميل البيانات ==================
def load_sheet(sheet, key):
    if key not in st.session_state:
        try:
            st.session_state[key] = sheet.get_all_values()
        except:
            st.session_state[key] = []
    return st.session_state[key]

complaints_data = load_sheet(complaints_sheet, "complaints_data")
responded_data = load_sheet(responded_sheet, "responded_data")
archive_data = load_sheet(archive_sheet, "archive_data")

types_list = []
try:
    types_list = [r[0] for r in load_sheet(types_sheet, "types_data")[1:]]
except:
    pass

return_warehouse_data = load_sheet(return_warehouse_sheet, "return_warehouse_data")[1:]
order_number_data = load_sheet(order_number_sheet, "order_number_data")[1:]

# ================== Helpers ==================
def get_returnwarehouse_record(order_id):
    for row in return_warehouse_data:
        if row and str(row[0]) == str(order_id):
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

def get_order_status(order_id):
    for row in order_number_data:
        if len(row) > 1 and str(row[1]) == str(order_id):
            delegate = row[3] if len(row) > 3 else ""
            if delegate.lower() == "aramex":
                return "📦 أرامكس"
            elif delegate:
                return f"🚚 مندوب ({delegate})"
            return "⏳ تحت المتابعة"
    return "⏳ تحت المتابعة"

# ================== Aramex (FIXED JSON) ==================
client_info = st.secrets.get("aramex_credentials", {})

def get_aramex_status(awb):
    try:
        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"

        payload = {
            "ClientInfo": client_info,
            "Shipments": [awb],
            "Transaction": {}
        }

        r = requests.post(url, json=payload, timeout=10)

        if r.status_code != 200:
            return f"❌ خطأ API {r.status_code}"

        data = r.json()

        try:
            track = data["TrackingResults"][0]["Value"][0]["TrackingResult"]
            last = sorted(track, key=lambda x: x.get("UpdateDateTime", ""), reverse=True)[0]

            desc = last.get("UpdateDescription", "")
            date = last.get("UpdateDateTime", "")
            loc = last.get("UpdateLocation", "")

            return f"{desc} بتاريخ {date} في {loc}"

        except:
            return "❌ لا توجد بيانات"

    except Exception as e:
        return f"خطأ: {e}"

# cache
if "aramex_cache" not in st.session_state:
    st.session_state["aramex_cache"] = {}

def cached_aramex_status(awb):
    if not awb:
        return ""
    if awb in st.session_state["aramex_cache"]:
        return st.session_state["aramex_cache"][awb]

    status = get_aramex_status(awb)
    st.session_state["aramex_cache"][awb] = status
    return status

# ================== عرض الشكوى ==================
def render_complaint(sheet, i, row, in_responded=False, in_archive=False):
    while len(row) < 8:
        row.append("")

    comp_id, comp_type, notes, action, date_added = row[:5]
    outbound_awb = row[6]
    inbound_awb = row[7]

    status = get_order_status(comp_id)

    with st.expander(f"🆔 {comp_id} | {comp_type} | {status}"):

        st.write("📌", comp_type)
        st.write("📝", notes)
        st.write("✅", action)

        new_type = st.selectbox("تعديل النوع", [comp_type] + types_list, index=0)
        new_notes = st.text_area("ملاحظات", value=notes)
        new_action = st.text_area("إجراء", value=action)

        new_out = st.text_input("Outbound", value=outbound_awb)
        new_in = st.text_input("Inbound", value=inbound_awb)

        if st.button("💾 حفظ", key=f"save_{comp_id}_{i}"):
            safe_update_cell(sheet, i, 2, new_type)
            safe_update_cell(sheet, i, 3, new_notes)
            safe_update_cell(sheet, i, 4, new_action)
            safe_update_cell(sheet, i, 7, new_out)
            safe_update_cell(sheet, i, 8, new_in)
            st.success("تم الحفظ")

        if st.button("🗑️ حذف", key=f"del_{comp_id}_{i}"):
            safe_delete(sheet, i)
            st.warning("تم الحذف")

# ================== UI ==================
st.title("⚠️ نظام إدارة الشكاوى")

st.header("🔍 بحث")
search = st.text_input("رقم الشكوى")

if search:
    found = False
    for sheet_obj in [complaints_sheet, responded_sheet, archive_sheet]:
        data = sheet_obj.get_all_values()
        for i, r in enumerate(data[1:], start=2):
            if r and r[0] == search:
                render_complaint(sheet_obj, i, r)
                found = True
                break
    if not found:
        st.error("غير موجود")

st.header("➕ إضافة شكوى")

with st.form("add"):
    cid = st.text_input("ID")
    ctype = st.selectbox("نوع", [""] + types_list)
    notes = st.text_area("ملاحظات")
    action = st.text_area("إجراء")
    out = st.text_input("Outbound")
    inn = st.text_input("Inbound")

    if st.form_submit_button("إضافة"):
        date = datetime.now().strftime("%Y-%m-%d")

        target = responded_sheet if action else complaints_sheet

        safe_append(target, [cid, ctype, notes, action, date, "", out, inn])
        st.success("تمت الإضافة")

st.header("📋 الشكاوى")
for i, row in enumerate(complaints_data[1:], start=2):
    render_complaint(complaints_sheet, i, row)
