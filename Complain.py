# -*- coding: utf-8 -*-
import streamlit as st
import pyodbc
import pandas as pd
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# ======================
# إعداد الصفحة
# ======================
st.set_page_config(page_title="نظام الشحن Aramex", layout="wide")
st.title("🚚 نظام الشحن (Access + Aramex)")

# ======================
# الاتصال بـ Access
# ======================
DB_FILE = "homeless.accdb"  # غيّر المسار لو عندك محلي
conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + DB_FILE

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
except Exception as e:
    st.error(f"❌ خطأ في الاتصال بـ Access: {e}")
    st.stop()

# ======================
# Aramex Date
# ======================
def to_aramex_datetime(dt):
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    ms = int((dt - epoch).total_seconds() * 1000)
    return f"/Date({ms})/"

# ======================
# UI Inputs
# ======================
st.subheader("📦 إدخال الطلبات")

orders_text = st.text_area("أرقام الطلبات (كل رقم في سطر أو فاصلة)")
pieces_text = st.text_area("عدد القطع (بنفس الترتيب)")

default_pieces = st.number_input("عدد القطع الافتراضي", min_value=1, value=1)

start = st.button("🚀 بدء الشحن")

# ======================
# جلب من Access
# ======================
def get_order(order_id):
    cursor.execute("""
        SELECT [Order Number], [First Name (Billing)], [Phone (Billing)], [MAIL],
               [Address 1&2 (Billing)], [City (Billing)], [PostalCode], [CountryCode],
               [WeightKG], [CODAmount], [Description], [ReferenceNumber]
        FROM Orders
        WHERE [Order Number] = ?
    """, (int(order_id),))
    return cursor.fetchone()

# ======================
# Aramex Credentials
# ======================
client_info = {
    "UserName": "fitnessworld525@gmail.com",
    "Password": "Aa12345678@",
    "Version": "v1",
    "AccountNumber": "71958996",
    "AccountPin": "657448",
    "AccountEntity": "RUH",
    "AccountCountryCode": "SA"
}

url = "https://ws.aramex.net/ShippingAPI.V2/Shipping/Service_1_0.svc/json/CreateShipments"
headers = {"Content-Type": "application/json"}

# ======================
# تشغيل الشحن
# ======================
if start:

    orders = [o.strip() for o in orders_text.replace("\n", ",").split(",") if o.strip()]
    pieces = [p.strip() for p in pieces_text.replace("\n", ",").split(",") if p.strip()]

    results = []
    progress = st.progress(0)

    for i, order in enumerate(orders):

        st.write(f"📦 معالجة الطلب: {order}")

        try:
            row = get_order(order)

            if not row:
                st.error(f"❌ الطلب غير موجود: {order}")
                continue

            num_pieces = int(pieces[i]) if i < len(pieces) else default_pieces

            shipping_dt = datetime.now(timezone.utc)
            due_dt = shipping_dt + timedelta(days=2)

            payload = {
                "ClientInfo": client_info,
                "LabelInfo": {"ReportID": 9729, "ReportType": "URL"},
                "Shipments": [{
                    "Reference1": str(row[11]),
                    "Shipper": {
                        "AccountNumber": client_info["AccountNumber"],
                        "PartyAddress": {
                            "Line1": "Riyadh",
                            "City": "Riyadh",
                            "CountryCode": "SA"
                        },
                        "Contact": {
                            "PersonName": "Company",
                            "PhoneNumber1": "000"
                        }
                    },
                    "Consignee": {
                        "PartyAddress": {
                            "Line1": row[4],
                            "City": row[5],
                            "PostCode": str(row[6]),
                            "CountryCode": row[7]
                        },
                        "Contact": {
                            "PersonName": row[1],
                            "PhoneNumber1": str(row[2])
                        }
                    },
                    "ShippingDateTime": to_aramex_datetime(shipping_dt),
                    "DueDate": to_aramex_datetime(due_dt),
                    "Details": {
                        "ActualWeight": {"Value": float(row[8] or 1), "Unit": "KG"},
                        "ChargeableWeight": {"Value": float(row[8] or 1), "Unit": "KG"},
                        "DescriptionOfGoods": row[10],
                        "NumberOfPieces": num_pieces,
                        "ProductGroup": "DOM",
                        "ProductType": "CDS",
                        "PaymentType": "P",
                        "CashOnDeliveryAmount": {"Value": float(row[9] or 0), "CurrencyCode": "SAR"}
                    }
                }]
            }

            res = requests.post(url, json=payload, headers=headers)

            if res.status_code == 200:
                try:
                    root = ET.fromstring(res.text)

                    tracking = root.find('.//ID')
                    label = root.find('.//LabelURL')

                    tracking_id = tracking.text if tracking is not None else ""
                    label_url = label.text if label is not None else ""

                    results.append({
                        "Order": order,
                        "Tracking": tracking_id,
                        "LabelURL": label_url
                    })

                    st.success(f"✅ تم شحن {order}")

                except:
                    st.error(f"❌ خطأ قراءة رد Aramex {order}")

            else:
                st.error(f"❌ فشل {order} - {res.status_code}")

        except Exception as e:
            st.error(f"❌ خطأ في {order}: {e}")

        progress.progress((i + 1) / len(orders))

    # ======================
    # حفظ Excel
    # ======================
    if results:
        df = pd.DataFrame(results)
        file_name = "shipments_output.xlsx"
        df.to_excel(file_name, index=False)

        st.success("🎉 تم الانتهاء")
        st.download_button(
            "📥 تحميل الملف",
            data=open(file_name, "rb"),
            file_name=file_name
        )
