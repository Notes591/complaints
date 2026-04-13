# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime

# ====== TRY ACCESS (LOCAL ONLY) ======
ACCESS_ENABLED = False
conn = None
cursor = None

try:
    import pyodbc

    DB_FILE = r"C:\Users\ASUS\OneDrive\هوم لمسات.accdb"
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        r"DBQ=" + DB_FILE
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    ACCESS_ENABLED = True
except Exception:
    ACCESS_ENABLED = False


# ====== CITY MAP ======
city_map = {
    "الرياض": "Riyadh",
    "جدة": "Jeddah",
    "الدمام": "Dammam",
    # (اختصرته هنا لكن تقدر ترجع تحط القاموس كامل عندك)
}


# ====== STREAMLIT UI ======
st.set_page_config(page_title="Orders System", layout="wide")
st.title("📦 Orders System (Access + Streamlit)")


# ====== INPUT ======
col1, col2 = st.columns(2)

with col1:
    order_id = st.text_input("رقم الطلب")

with col2:
    action = st.selectbox(
        "الإجراء",
        ["ارسال صيانه", "إرجاع", "الصيانة", "الاستبدال", "إرسال الاستبدال", "إرسال نواقص"]
    )


# ====== LOAD FROM ACCESS ======
def fetch_order(order_id):
    if not ACCESS_ENABLED:
        return None

    try:
        cursor.execute("""
            SELECT [Order Number], [First Name (Billing)], [Phone (Billing)],
                   [MAIL], [Address 1&2 (Billing)], [City (Billing)],
                   [PostalCode], [CountryCode]
            FROM Orders
            WHERE [Order Number] = ?
        """, (int(order_id),))

        return cursor.fetchone()

    except Exception as e:
        st.error(f"DB Error: {e}")
        return None


# ====== ACTION FORMAT ======
def format_second_col(num, action):
    if action == "إرجاع":
        return num + "*"
    elif action == "الصيانة":
        return num + "#"
    elif action == "الاستبدال":
        return num + "*#"
    elif action == "إرسال الاستبدال":
        return num + "*#&"
    elif action == "إرسال نواقص":
        return num + "&"
    elif action == "ارسال صيانه":
        return num + "#&"
    return num


# ====== SESSION DATA ======
if "rows" not in st.session_state:
    st.session_state.rows = []


# ====== ADD BUTTON ======
if st.button("➕ إضافة"):
    if not order_id.isdigit():
        st.error("رقم الطلب غير صحيح")
    else:
        data = fetch_order(order_id)

        second = format_second_col(order_id, action)

        if data:
            city_en = city_map.get(data[5], data[5])

            row = [
                data[0],
                second,
                data[1],
                data[2],
                data[3],
                data[4],
                city_en,
                data[6],
                data[7],
                3,
                0,
                "منتجات"
            ]
        else:
            row = [
                order_id,
                second,
                "لا توجد بيانات",
                "-", "-", "-", "-", "-", "-", 3, 0, "منتجات"
            ]

        st.session_state.rows.append(row)


# ====== TABLE ======
columns = [
    "Order Number",
    "Order Number*",
    "Name",
    "Phone",
    "Email",
    "Address",
    "City",
    "Postal",
    "Country",
    "WeightKG",
    "COD",
    "Description"
]

if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows, columns=columns)
    st.dataframe(df, use_container_width=True)


    # ====== EXPORT EXCEL ======
    def convert_to_excel(dataframe):
        file_path = "Orders_Output.xlsx"
        dataframe.to_excel(file_path, index=False)
        return file_path


    if st.button("⬇️ تصدير Excel"):
        path = convert_to_excel(df)
        st.success("تم التصدير")
        st.download_button(
            "تحميل الملف",
            data=open(path, "rb"),
            file_name="Orders_Output.xlsx"
        )
else:
    st.info("لا توجد بيانات")
