# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import os
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import threading
import pyodbc
import pandas as pd
import platform
import subprocess

# =======================
# الاتصال بقاعدة بيانات Access
# =======================
DB_FILE = r"C:\Users\ASUS\OneDrive\هوم لمسات.accdb"
conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + DB_FILE
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# =======================
# تحويل التاريخ لأرامكس
# =======================
def to_aramex_datetime(dt):
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    ms = int((dt - epoch).total_seconds() * 1000)
    return f"/Date({ms})/"

# =======================
# واجهة التطبيق
# =======================
class ShipmentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📦 نظام الشحن (Access + Aramex)")
        self.geometry("750x600")
        self.resizable(False, False)
        self.create_widgets()

    # =======================
    # UI
    # =======================
    def create_widgets(self):
        padx, pady = 10, 8

        frame_default = ttk.LabelFrame(self, text="الإعدادات")
        frame_default.pack(fill="x", padx=padx, pady=pady)

        ttk.Label(frame_default, text="عدد القطع الافتراضي:").grid(row=0, column=0)
        self.default_pieces = tk.Entry(frame_default, width=10)
        self.default_pieces.insert(0, "1")
        self.default_pieces.grid(row=0, column=1)

        frame_custom = ttk.LabelFrame(self, text="طلبات خاصة")
        frame_custom.pack(fill="both", padx=padx, pady=pady, expand=True)

        ttk.Label(frame_custom, text="أرقام الطلبات:").pack(anchor="w")
        self.custom_orders = tk.Text(frame_custom, height=4)
        self.custom_orders.pack(fill="x")

        ttk.Label(frame_custom, text="عدد القطع لكل طلب:").pack(anchor="w", pady=(10, 0))
        self.custom_pieces = tk.Text(frame_custom, height=4)
        self.custom_pieces.pack(fill="x")

        self.print_twice = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="طباعة البوليصة مرتين", variable=self.print_twice).pack(anchor="w")

        frame_btn = ttk.Frame(self)
        frame_btn.pack(fill="x", padx=10, pady=5)

        ttk.Button(frame_btn, text="🚚 بدء الشحن", command=self.start_processing).pack(side="right")
        ttk.Button(frame_btn, text="📂 فتح ملف الناتج", command=self.open_excel).pack(side="left")

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=5)

        self.status = ttk.Label(self, text="جاهز")
        self.status.pack(anchor="w", padx=10)

    # =======================
    # تحديث الحالة
    # =======================
    def update_status(self, msg):
        self.after(0, lambda: self.status.config(text=msg))

    # =======================
    # فتح الملف
    # =======================
    def open_excel(self):
        file = "shipments_with_tracking_updated.xlsx"
        if os.path.exists(file):
            os.startfile(file)
        else:
            messagebox.showerror("خطأ", "لا يوجد ملف")

    # =======================
    # بدء التنفيذ
    # =======================
    def start_processing(self):
        threading.Thread(target=self.process_shipments, daemon=True).start()

    # =======================
    # جلب بيانات من Access
    # =======================
    def get_order_from_db(self, order_id):
        try:
            cursor.execute("""
                SELECT [Order Number], [First Name (Billing)], [Phone (Billing)], [MAIL],
                       [Address 1&2 (Billing)], [City (Billing)], [PostalCode], [CountryCode],
                       [WeightKG], [CODAmount], [Description], [ReferenceNumber]
                FROM Orders
                WHERE [Order Number] = ?
            """, (int(order_id),))

            return cursor.fetchone()
        except:
            return None

    # =======================
    # تنفيذ الشحن
    # =======================
    def process_shipments(self):
        try:
            orders_input = self.custom_orders.get("1.0", tk.END).strip().replace("\n", ",")
            pieces_input = self.custom_pieces.get("1.0", tk.END).strip().replace("\n", ",")

            order_list = [x.strip() for x in orders_input.split(",") if x.strip()]
            piece_list = []

            for x in pieces_input.split(","):
                try:
                    piece_list.append(int(x.strip()))
                except:
                    piece_list.append(None)

            order_piece_map = dict(zip(order_list, piece_list))

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

            results = []
            self.progress["value"] = 0
            self.progress["maximum"] = len(order_list)

            for i, order in enumerate(order_list):
                self.update_status(f"جاري معالجة {order}")

                row = self.get_order_from_db(order)

                if not row:
                    self.update_status(f"❌ الطلب {order} غير موجود في Access")
                    continue

                num_pieces = order_piece_map.get(order) or int(self.default_pieces.get())

                shipping_dt = datetime.now(timezone.utc)
                due_dt = shipping_dt + timedelta(days=2)

                payload = {
                    "ClientInfo": client_info,
                    "LabelInfo": {"ReportID": 9729, "ReportType": "URL"},
                    "Shipments": [{
                        "Reference1": row[11] if len(row) > 11 else str(order),
                        "Shipper": {
                            "AccountNumber": client_info["AccountNumber"],
                            "PartyAddress": {
                                "Line1": "الرياض حي السلي",
                                "City": "Riyadh",
                                "CountryCode": "SA"
                            },
                            "Contact": {
                                "PersonName": "Company",
                                "PhoneNumber1": "000000"
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

                        results.append([order, tracking_id, label_url])
                        self.update_status(f"✅ تم شحن {order}")

                    except:
                        self.update_status(f"❌ خطأ تحليل رد {order}")

                self.progress["value"] = i + 1

            df = pd.DataFrame(results, columns=["Order", "Tracking", "Label"])
            df.to_excel("shipments_with_tracking_updated.xlsx", index=False)

            self.update_status("🎉 تم الانتهاء")
            messagebox.showinfo("تم", "تم تنفيذ جميع الشحنات")

        except Exception as e:
            self.update_status(f"❌ خطأ عام: {e}")

# =======================
# تشغيل البرنامج
# =======================
if __name__ == "__main__":
    app = ShipmentApp()
    app.mainloop()
