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

# ====== الشيتات ======
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
    except:
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

# ====== الصفحة ======
st.set_page_config(page_title="📢 نظام الشكاوى", page_icon="⚠️", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== 🔔 الإشعارات ======
def add_notification(message):
    try:
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notifications_sheet.append_row([message, date_now, "NEW"])
    except:
        pass

@st.cache_data(ttl=10)
def get_notifications():
    try:
        data = notifications_sheet.get_all_values()
        return data[1:] if len(data) > 1 else []
    except:
        return []

st.markdown("### 🔔 الإشعارات")
notifications = get_notifications()
unread = [n for n in notifications if len(n) > 2 and n[2] == "NEW"]

col1, col2 = st.columns([1,5])

with col1:
    st.markdown(f"### 🔔 ({len(unread)})")

with col2:
    with st.expander("عرض الإشعارات"):
        if notifications:
            for n in reversed(notifications):
                msg = n[0]
                date = n[1]
                status = n[2] if len(n) > 2 else ""
                if status == "NEW":
                    st.warning(f"🆕 {msg} - {date}")
                else:
                    st.write(f"{msg} - {date}")
        else:
            st.info("لا توجد إشعارات")

if st.button("✔️ تعليم الكل كمقروء"):
    try:
        data = notifications_sheet.get_all_values()
        for i in range(2, len(data)+1):
            notifications_sheet.update(f"C{i}", [["READ"]])
        st.success("تم تحديث الإشعارات")
    except:
        st.error("خطأ")

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except:
            time.sleep(delay)
    return False

def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except:
            time.sleep(delay)
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except:
            time.sleep(delay)
    return False

# ====== أنواع الشكاوى ======
try:
    types_list = [row[0] for row in types_sheet.get_all_values()[1:]]
except:
    types_list = []

# ====== Aramex ======
def get_aramex_status(awb):
    try:
        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        payload = {"Shipments": [awb]}
        r = requests.post(url, json=payload, timeout=5)
        return r.text[:200]
    except:
        return "خطأ"

# ====== إضافة شكوى ======
st.header("➕ تسجيل شكوى جديدة")
with st.form("add_complaint", clear_on_submit=True):
    comp_id = st.text_input("🆔 رقم الشكوى")
    comp_type = st.selectbox("📌 نوع الشكوى", ["اختر"] + types_list)
    notes = st.text_area("📝 ملاحظات")
    action = st.text_area("✅ إجراء")
    submitted = st.form_submit_button("➕ إضافة")

    if submitted:
        if comp_id and comp_type != "اختر":
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if action:
                if safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now]):
                    add_notification(f"✅ شكوى مردودة {comp_id}")
                    st.success("تمت الإضافة للمردودة")
            else:
                if safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now]):
                    add_notification(f"📢 شكوى جديدة {comp_id}")
                    st.success("تمت الإضافة للنشطة")
        else:
            st.error("⚠️ بيانات ناقصة")

# ====== عرض النشطة ======
st.header("📋 الشكاوى النشطة")
active = complaints_sheet.get_all_values()

if len(active) > 1:
    for i, row in enumerate(active[1:], start=2):
        with st.expander(f"{row[0]}"):
            st.write(row)

            if st.button(f"💾 تعديل {row[0]}"):
                add_notification(f"✏️ تعديل {row[0]}")

            if st.button(f"🗑️ حذف {row[0]}"):
                if safe_delete(complaints_sheet, i):
                    add_notification(f"🗑️ حذف {row[0]}")
                    st.rerun()

            if st.button(f"➡️ نقل {row[0]}"):
                if safe_append(responded_sheet, row):
                    safe_delete(complaints_sheet, i)
                    add_notification(f"➡️ نقل {row[0]}")
                    st.rerun()
else:
    st.info("لا يوجد")

# ====== المردودة ======
st.header("✅ الإجراءات المردودة")
resp = responded_sheet.get_all_values()

if len(resp) > 1:
    for i, row in enumerate(resp[1:], start=2):
        with st.expander(f"{row[0]}"):
            st.write(row)

            if st.button(f"📦 أرشفة {row[0]}"):
                if safe_append(archive_sheet, row):
                    safe_delete(responded_sheet, i)
                    add_notification(f"📦 أرشفة {row[0]}")
                    st.rerun()
else:
    st.info("لا يوجد")

# ====== Aramex ======
st.header("🚚 تتبع أرامكس")
with st.form("aramex_form"):
    awb = st.text_input("AWB")
    submitted = st.form_submit_button("تتبع")

    if submitted and awb:
        status = get_aramex_status(awb)
        st.info(status)

        if "Delivered" in status:
            add_notification(f"📦 تم تسليم الشحنة {awb}")
