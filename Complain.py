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

# ====== Auto Refresh ======
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== Google Sheets ======
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "Complaints"

sheet_titles = [
    "Complaints", "Responded", "Archive", "Types",
    "معلق ارامكس", "أرشيف أرامكس",
    "ReturnWarehouse", "Order Number",
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

# ====== Page ======
st.set_page_config(page_title="📢 نظام الشكاوى", layout="wide")
st.title("⚠️ نظام إدارة الشكاوى")

# ====== Notifications System ======
def add_notification(msg):
    try:
        notifications_sheet.append_row([
            msg,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "NEW"
        ])
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
    st.markdown(f"## 🔔 ({len(unread)})")

with col2:
    with st.expander("عرض الإشعارات"):
        if notifications:
            for n in reversed(notifications):
                if len(n) < 3:
                    continue
                if n[2] == "NEW":
                    st.warning(f"🆕 {n[0]} - {n[1]}")
                else:
                    st.write(f"{n[0]} - {n[1]}")
        else:
            st.info("لا توجد إشعارات")

if st.button("✔️ تعليم الكل كمقروء"):
    data = notifications_sheet.get_all_values()
    for i in range(2, len(data)+1):
        notifications_sheet.update(f"C{i}", [["READ"]])
    st.success("تم تحديث الكل")

# ====== Retry Functions ======
def safe_append(sheet, row):
    try:
        sheet.append_row(row)
        return True
    except:
        return False

def safe_update(sheet, rng, val):
    try:
        sheet.update(rng, val)
        return True
    except:
        return False

def safe_delete(sheet, i):
    try:
        sheet.delete_rows(i)
        return True
    except:
        return False

# ====== Types ======
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
        return r.text[:100]
    except:
        return "خطأ"

# ====== Add Complaint ======
st.header("➕ تسجيل شكوى جديدة")

with st.form("add"):
    comp_id = st.text_input("ID")
    comp_type = st.selectbox("Type", ["اختار"] + types_list)
    notes = st.text_area("Notes")
    action = st.text_area("Action")
    submitted = st.form_submit_button("Add")

    if submitted:
        if comp_id and comp_type != "اختار":
            if action:
                safe_append(responded_sheet, [comp_id, comp_type, notes, action])
                add_notification(f"✅ شكوى مردودة {comp_id}")
            else:
                safe_append(complaints_sheet, [comp_id, comp_type, notes, ""])
                add_notification(f"📢 شكوى جديدة {comp_id}")

# ====== View Active ======
st.header("📋 الشكاوى النشطة")

data = complaints_sheet.get_all_values()

if len(data) > 1:
    for i, row in enumerate(data[1:], start=2):
        with st.expander(f"{row[0]}"):
            st.write(row)

            if st.button(f"حذف {row[0]}"):
                safe_delete(complaints_sheet, i)
                add_notification(f"🗑️ حذف {row[0]}")
                st.rerun()

            if st.button(f"نقل {row[0]}"):
                safe_append(responded_sheet, row)
                safe_delete(complaints_sheet, i)
                add_notification(f"➡️ نقل {row[0]}")
                st.rerun()

# ====== Responded ======
st.header("✅ المردودة")

data = responded_sheet.get_all_values()

if len(data) > 1:
    for i, row in enumerate(data[1:], start=2):
        with st.expander(f"{row[0]}"):
            st.write(row)

            if st.button(f"أرشفة {row[0]}"):
                safe_append(archive_sheet, row)
                safe_delete(responded_sheet, i)
                add_notification(f"📦 أرشفة {row[0]}")
                st.rerun()

# ====== Aramex ======
st.header("🚚 أرامكس")

with st.form("aramex"):
    awb = st.text_input("AWB")
    if st.form_submit_button("Check"):
        status = get_aramex_status(awb)
        st.info(status)

        if "Delivered" in status:
            add_notification(f"📦 تم تسليم {awb}")
