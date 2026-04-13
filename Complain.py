# -*- coding: utf-8 -*-
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone, timedelta, time as dt_time
import time
import gspread.exceptions
import requests
import json
import xml.etree.ElementTree as ET
import re
import io
import base64
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# ====== تحديث تلقائي ======
st_autorefresh(interval=1200000, key="auto_refresh")

# ====== الاتصال بجوجل شيت ======
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

complaints_sheet   = sheets_dict["Complaints"]
responded_sheet    = sheets_dict["Responded"]
archive_sheet      = sheets_dict["Archive"]
types_sheet        = sheets_dict["Types"]
aramex_sheet       = sheets_dict["معلق ارامكس"]
aramex_archive     = sheets_dict["أرشيف أرامكس"]
return_warehouse_sheet = sheets_dict["ReturnWarehouse"]
order_number_sheet = sheets_dict["Order Number"]

# ====== إعدادات الصفحة ======
st.set_page_config(page_title="🏢 نظام عمليات عالم الرشاقة", page_icon="⚙️", layout="wide")
st.title("⚙️ نظام عمليات عالم الرشاقة")

# ====== دوال Retry ======
def safe_append(sheet, row_data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.append_row(row_data)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل append_row بعد عدة محاولات.")
    return False

def safe_update(sheet, cell_range, values, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.update(cell_range, values)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل update بعد عدة محاولات.")
    return False

def safe_delete(sheet, row_index, retries=5, delay=1):
    for attempt in range(retries):
        try:
            sheet.delete_rows(row_index)
            return True
        except Exception:
            time.sleep(delay)
    st.error("❌ فشل delete_rows بعد عدة محاولات.")
    return False

# ====== تحميل البيانات المساعدة ======
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

# ====== إعداد أرامكس ======
ARAMEX_CLIENT = {
    "UserName": "fitnessworld525@gmail.com",
    "Password": "Aa12345678@",
    "Version": "v1",
    "AccountNumber": "71958996",
    "AccountPin": "657448",
    "AccountEntity": "RUH",
    "AccountCountryCode": "SA"
}

SHIPPER_INFO = {
    "name": "شركة عالم الرشاقة للتجارة",
    "phone": "00966560000496",
    "email": "world-fitness@outlook.sa",
    "line1": "الرياض حي السلي شارع ابن ماجه",
    "city": "Riyadh",
    "postcode": "14265",
    "country": "SA"
}

def to_aramex_datetime(dt):
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    ms = int((dt - epoch).total_seconds() * 1000)
    return f"/Date({ms})/"

def to_aramex_datetime_from_time(t):
    now = datetime.now(timezone.utc)
    dt = datetime.combine(now.date(), t, tzinfo=timezone.utc)
    ms = int(dt.timestamp() * 1000)
    return f"/Date({ms})/"

def remove_xml_namespaces(xml_str):
    xml_str = re.sub(r'xmlns(:\w+)?="[^"]+"', '', xml_str)
    xml_str = re.sub(r'(<\/?)(\w+:)', r'\1', xml_str)
    return xml_str

def extract_reference(tracking_result):
    for ref_tag in ['Reference1','Reference2','Reference3','Reference4','Reference5']:
        ref_elem = tracking_result.find(ref_tag)
        if ref_elem is not None and ref_elem.text and ref_elem.text.strip():
            return ref_elem.text.strip()
    return ""

def get_aramex_status(awb_number):
    try:
        payload = {
            "ClientInfo": ARAMEX_CLIENT,
            "Shipments": [awb_number],
            "Transaction": {"Reference1":"","Reference2":"","Reference3":"","Reference4":"","Reference5":""},
            "LabelInfo": None
        }
        url = "https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc/json/TrackShipments"
        response = requests.post(url, json=payload, headers={"Content-Type":"application/json"}, timeout=10)
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
                    last_track = sorted(tracks,
                        key=lambda tr: tr.find('UpdateDateTime').text if tr.find('UpdateDateTime') is not None else '',
                        reverse=True)[0]
                    desc = last_track.find('UpdateDescription').text if last_track.find('UpdateDescription') is not None else "—"
                    date = last_track.find('UpdateDateTime').text if last_track.find('UpdateDateTime') is not None else "—"
                    loc  = last_track.find('UpdateLocation').text  if last_track.find('UpdateLocation')  is not None else "—"
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

# ====== قاموس المدن ======
CITY_MAP = {
    "ابا الورود": "Aba Alworood", "ابها": "Abha", "الاحساء": "Al Hassa",
    "الباحة": "Baha", "بريدة": "Buraidah", "الدمام": "Dammam",
    "الدوادمي": "Dawadmi", "الدرعية": "Dere'iyeh", "الظهران": "Dhahran",
    "عرعر": "Arar", "حفر الباطن": "Hafer Al Batin", "حائل": "Hail",
    "الهفوف": "Hofuf", "جدة": "Jeddah", "الجوف": "Jouf",
    "الجبيل": "Jubail", "خميس مشيط": "Khamis Mushait", "الخرج": "Kharj",
    "الخبر": "Khobar", "ليلى": "Layla", "المدينة المنورة": "Madinah",
    "مكة المكرمة": "Makkah", "المجمعة": "Majma", "نجران": "Najran",
    "القطيف": "Qatif", "رابغ": "Rabigh", "رفحاء": "Rafha",
    "الرياض": "Riyadh", "سكاكا": "Sakaka", "شقراء": "Shaqra",
    "تبوك": "Tabuk", "الطائف": "Taif", "ينبع": "Yanbu",
    "الزلفي": "Zulfi", "بيشة": "Bisha", "جازان": "Gizan",
    "أبها": "Abha", "القصيم": "Qassim", "حريملاء": "Horaimal",
    "الرس": "AlRass", "عنيزة": "Onaiza", "بلجرشي": "BilJurashi",
    "محايل": "Mohayel Aseer", "صبيا": "Sabya", "أبو عريش": "Abu Areish",
    "الدمام ": "Dammam", "مكة": "Makkah", "المدينة": "Madinah",
}

# ====== دالة عرض الشكوى ======
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
                    f"رقم الطلب: {rw_record['رقم الطلب']} | الفاتورة: {rw_record['الفاتورة']} | "
                    f"التاريخ: {rw_record['التاريخ']} | الزبون: {rw_record['الزبون']} | "
                    f"المبلغ: {rw_record['المبلغ']} | رقم الشحنة: {rw_record['رقم الشحنة']} | "
                    f"البيان: {rw_record['البيان']}"
                )

            new_type   = st.selectbox("✏️ عدل نوع الشكوى", [comp_type]+[t for t in types_list if t != comp_type], index=0)
            new_notes  = st.text_area("✏️ عدل الملاحظات", value=notes)
            new_action = st.text_area("✏️ عدل الإجراء", value=action)
            new_outbound = st.text_input("✏️ Outbound AWB", value=outbound_awb)
            new_inbound  = st.text_input("✏️ Inbound AWB",  value=inbound_awb)

            if new_outbound:
                st.info(f"🚚 Outbound AWB: {new_outbound} | الحالة: {cached_aramex_status(new_outbound)}")
            if new_inbound:
                st.info(f"📦 Inbound AWB: {new_inbound} | الحالة: {cached_aramex_status(new_inbound)}")

            col1, col2, col3, col4 = st.columns(4)
            submitted_save    = col1.form_submit_button("💾 حفظ")
            submitted_delete  = col2.form_submit_button("🗑️ حذف")
            submitted_archive = col3.form_submit_button("📦 أرشفة")
            if not in_responded:
                submitted_move = col4.form_submit_button("➡️ نقل للمردودة")
            else:
                submitted_move = col4.form_submit_button("⬅️ رجوع للنشطة")

            if submitted_save:
                safe_update(sheet, f"B{i}", [[new_type]])
                safe_update(sheet, f"C{i}", [[new_notes]])
                safe_update(sheet, f"D{i}", [[new_action]])
                safe_update(sheet, f"G{i}", [[new_outbound]])
                safe_update(sheet, f"H{i}", [[new_inbound]])
                st.success("✅ تم التعديل")

            if submitted_delete:
                if safe_delete(sheet, i):
                    st.warning("🗑️ تم حذف الشكوى")

            if submitted_archive:
                if safe_append(archive_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                    if safe_delete(sheet, i):
                        st.success("♻️ الشكوى انتقلت للأرشيف")

            if submitted_move:
                if not in_responded:
                    if safe_append(responded_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            st.success("✅ انتقلت للمردودة")
                else:
                    if safe_append(complaints_sheet, [comp_id, new_type, new_notes, new_action, date_added, restored, new_outbound, new_inbound]):
                        if safe_delete(sheet, i):
                            st.success("✅ انتقلت للنشطة")

# ====== دالة إنشاء شحنة أرامكس ======
def create_aramex_shipment(row_data, num_pieces, is_return=False):
    """
    row_data: dict بالمفاتيح التالية:
        OrderNumber, ReferenceNumber, CustomerName, CustomerPhone,
        CustomerEmail, AddressLine, City, PostalCode, CountryCode,
        WeightKG, CODAmount, Description
    is_return: True = الشاحن هو الزبون والمستلم هو المستودع
    """
    shipping_dt = datetime.now(timezone.utc)
    due_dt = shipping_dt + timedelta(days=2)

    consignee_name  = str(row_data.get("CustomerName","")).strip() or "غير محدد"
    customer_phone  = str(row_data.get("CustomerPhone","0000000000")).strip()
    ref_number      = str(row_data.get("ReferenceNumber", row_data.get("OrderNumber","")))

    shipper_party = {
        "Reference1": ref_number, "Reference2": "",
        "AccountNumber": ARAMEX_CLIENT["AccountNumber"],
        "PartyAddress": {
            "Line1": SHIPPER_INFO["line1"], "Line2": "", "Line3": "",
            "City": SHIPPER_INFO["city"], "StateOrProvinceCode": SHIPPER_INFO["city"],
            "PostCode": SHIPPER_INFO["postcode"], "CountryCode": SHIPPER_INFO["country"]
        },
        "Contact": {
            "Department": "", "PersonName": SHIPPER_INFO["name"],
            "CompanyName": SHIPPER_INFO["name"],
            "PhoneNumber1": SHIPPER_INFO["phone"], "PhoneNumber2": SHIPPER_INFO["phone"],
            "CellPhone": SHIPPER_INFO["phone"], "EmailAddress": SHIPPER_INFO["email"], "Type": ""
        }
    }

    consignee_party = {
        "Reference1": ref_number, "Reference2": "",
        "AccountNumber": "", "PartyAddress": {
            "Line1": str(row_data.get("AddressLine","")), "Line2": "", "Line3": "",
            "City": str(row_data.get("City","")),
            "PostCode": str(row_data.get("PostalCode","")),
            "CountryCode": str(row_data.get("CountryCode","SA"))
        },
        "Contact": {
            "PersonName": consignee_name, "CompanyName": consignee_name,
            "PhoneNumber1": customer_phone, "PhoneNumber2": customer_phone,
            "CellPhone": customer_phone, "EmailAddress": str(row_data.get("CustomerEmail","")),
            "Type": "consignee"
        }
    }

    if is_return:
        # في الإرجاع: الشاحن = الزبون، المستلم = المستودع
        return_shipper = {
            "Reference1": ref_number, "Reference2": "",
            "AccountNumber": ARAMEX_CLIENT["AccountNumber"],
            "AccountEntity": ARAMEX_CLIENT["AccountEntity"],
            "PartyAddress": {
                "Line1": str(row_data.get("AddressLine","")), "Line2": "", "Line3": "",
                "City": str(row_data.get("City","")),
                "StateOrProvinceCode": "",
                "PostCode": str(row_data.get("PostalCode","")),
                "CountryCode": str(row_data.get("CountryCode","SA"))
            },
            "Contact": {
                "Department": "", "PersonName": consignee_name, "CompanyName": consignee_name,
                "PhoneNumber1": customer_phone, "PhoneNumber2": customer_phone,
                "CellPhone": customer_phone, "EmailAddress": str(row_data.get("CustomerEmail","")), "Type": ""
            }
        }
        return_consignee = {
            "Reference1": ref_number, "Reference2": "",
            "AccountNumber": ARAMEX_CLIENT["AccountNumber"],
            "AccountEntity": ARAMEX_CLIENT["AccountEntity"],
            "PartyAddress": {
                "Line1": SHIPPER_INFO["line1"], "Line2": "", "Line3": "",
                "City": SHIPPER_INFO["city"], "StateOrProvinceCode": SHIPPER_INFO["city"],
                "PostCode": SHIPPER_INFO["postcode"], "CountryCode": SHIPPER_INFO["country"]
            },
            "Contact": {
                "PersonName": SHIPPER_INFO["name"], "CompanyName": SHIPPER_INFO["name"],
                "PhoneNumber1": SHIPPER_INFO["phone"], "PhoneNumber2": SHIPPER_INFO["phone"],
                "CellPhone": SHIPPER_INFO["phone"], "EmailAddress": SHIPPER_INFO["email"], "Type": "consignee"
            }
        }
        final_shipper   = return_shipper
        final_consignee = return_consignee
        payment_type    = "C"
    else:
        final_shipper   = shipper_party
        final_consignee = consignee_party
        payment_type    = "P"

    payload = {
        "ClientInfo": ARAMEX_CLIENT,
        "Transaction": {"Reference1":"","Reference2":"","Reference3":"","Reference4":"","Reference5":""},
        "Shipments": [{
            "Reference1": ref_number, "Reference2": "",
            "Shipper":   final_shipper,
            "Consignee": final_consignee,
            "ShippingDateTime": to_aramex_datetime(shipping_dt),
            "DueDate": to_aramex_datetime(due_dt),
            "Comments": "", "PickupLocation": "",
            "Details": {
                "Dimensions": None,
                "ActualWeight":    {"Value": float(row_data.get("WeightKG", 1)), "Unit": "KG"},
                "ChargeableWeight":{"Value": float(row_data.get("WeightKG", 1)), "Unit": "KG"},
                "DescriptionOfGoods": str(row_data.get("Description","منتجات")),
                "GoodsOriginCountry": "SA",
                "NumberOfPieces": num_pieces,
                "ProductGroup": "DOM", "ProductType": "CDS",
                "PaymentType": payment_type, "PaymentOptions": "",
                "CustomsValueAmount":    {"Value": 1500, "CurrencyCode": "SAR"},
                "CashOnDeliveryAmount":  {"Value": float(row_data.get("CODAmount",0)), "CurrencyCode": "SAR"},
                "InsuranceAmount":       {"Value": 0, "CurrencyCode": "SAR"},
                "CashAdditionalAmount":  {"Value": 0, "CurrencyCode": "SAR"},
                "CashAdditionalAmountDescription": "",
                "CollectAmount":         {"Value": 0, "CurrencyCode": "SAR"},
                "Services": "", "Items": []
            }
        }]
    }

    url = "https://ws.aramex.net/ShippingAPI.V2/Shipping/Service_1_0.svc/json/CreateShipments"
    json_payload = json.dumps(payload, ensure_ascii=False).replace("\\/", "/")
    try:
        response = requests.post(url, data=json_payload, headers={"Content-Type":"application/json"}, timeout=15)
        if response.status_code != 200:
            return None, None, f"HTTP {response.status_code}"
        ns = {'ns': 'http://ws.aramex.net/ShippingAPI/v1/'}
        root_el = ET.fromstring(response.text)
        processed = root_el.find('.//ns:ProcessedShipment', ns)
        if processed is None:
            return None, None, "لا توجد بيانات شحن في الرد"
        has_errors = processed.find('ns:HasErrors', ns)
        if has_errors is not None and has_errors.text.lower() == 'true':
            notif = processed.find('ns:Notifications', ns)
            err_msg = ET.tostring(notif, encoding='unicode') if notif is not None else "خطأ غير معروف"
            return None, None, err_msg
        tracking_id = processed.find('ns:ID', ns)
        label_url_el = processed.find('.//ns:ShipmentLabel/ns:LabelURL', ns)
        tracking_id = tracking_id.text if tracking_id is not None else ""
        label_url   = label_url_el.text if label_url_el is not None else ""
        return tracking_id, label_url, None
    except Exception as e:
        return None, None, str(e)

def download_pdf_bytes(label_url):
    try:
        r = requests.get(label_url, timeout=10)
        if r.status_code == 200:
            return r.content
    except:
        pass
    return None

# ====== دالة طلب المندوب ======
def request_pickup_aramex(shipper_data, num_pieces, weight_kg, order_number, location_details):
    url_pickup = "https://ws.aramex.net/ShippingAPI.V2/Shipping/Service_1_0.svc/json/CreatePickup"
    pickup_date_str     = to_aramex_datetime(datetime.now(timezone.utc))
    pickup_time_str     = to_aramex_datetime_from_time(dt_time(9,0))
    ready_time_str      = to_aramex_datetime_from_time(dt_time(9,0))
    last_pickup_time    = to_aramex_datetime_from_time(dt_time(18,0))
    closing_time_str    = to_aramex_datetime_from_time(dt_time(19,0))

    payload = {
        "ClientInfo": ARAMEX_CLIENT,
        "Pickup": {
            "PickupLocation": shipper_data["city"],
            "PickupAddress": {
                "Line1": shipper_data.get("line1",""), "Line2": "", "Line3": "",
                "City": shipper_data.get("city",""), "StateOrProvince": "",
                "PostCode": shipper_data.get("postcode",""), "CountryCode": "SA"
            },
            "PickupContact": {
                "PersonName": shipper_data.get("name",""),
                "CompanyName": shipper_data.get("name",""),
                "PhoneNumber1": shipper_data.get("phone",""),
                "PhoneNumber2": shipper_data.get("phone",""),
                "CellPhone": shipper_data.get("phone",""),
                "EmailAddress": shipper_data.get("email",""), "Type": ""
            },
            "PickupItems": [{
                "PackageType": "Box", "Quantity": num_pieces,
                "ProductGroup": "DOM", "ProductType": "PPX",
                "NumberOfShipments": 1, "Payment": "P",
                "ShipmentWeight": {"Value": weight_kg, "Unit": "KG"},
                "ShipmentVolume": None, "NumberOfPieces": num_pieces,
                "CashAmount": None, "ExtraCharges": None,
                "ShipmentDimensions": None, "Comments": ""
            }],
            "PickupDate": pickup_date_str, "PickupTime": pickup_time_str,
            "ReadyTime": ready_time_str, "LastPickupTime": last_pickup_time,
            "ClosingTime": closing_time_str,
            "Comments": "طلب مندوب من النظام", "Vehicle": None,
            "Remarks": "طلب مندوب من النظام",
            "PickupLocationDetails": location_details,
            "AccountNumber": ARAMEX_CLIENT["AccountNumber"],
            "AccountPin": ARAMEX_CLIENT["AccountPin"],
            "AccountEntity": ARAMEX_CLIENT["AccountEntity"],
            "AccountCountryCode": ARAMEX_CLIENT["AccountCountryCode"],
            "Reference1": str(order_number), "Status": "Ready"
        }
    }
    json_payload = json.dumps(payload, ensure_ascii=False).replace("\\/", "/")
    try:
        response = requests.post(url_pickup, data=json_payload, headers={"Content-Type":"application/json"}, timeout=15)
        if response.status_code == 200:
            root_el = ET.fromstring(response.text)
            ns = {'ns': 'http://ws.aramex.net/ShippingAPI/v1/'}
            pickup_ref = root_el.find('.//ns:ID', ns)
            if pickup_ref is not None and pickup_ref.text:
                return pickup_ref.text, None
            return None, "لم يُعثر على رقم المندوب في الرد"
        return None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, str(e)

# ============================================================
# ==================== التبويبات الرئيسية ====================
# ============================================================
tab_complaints, tab_shipping, tab_return, tab_pickup, tab_customers = st.tabs([
    "⚠️ الشكاوى",
    "📤 شحن أرامكس",
    "📥 إرجاع أرامكس",
    "🚚 طلب مندوب",
    "🧑‍💼 بيانات العملاء"
])

# ============================================================
# ======================== تبويب الشكاوى ====================
# ============================================================
with tab_complaints:
    st.header("🔍 البحث عن شكوى")
    search_id = st.text_input("أدخل رقم الشكوى للبحث", key="search_complaint")
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
            for i, row in enumerate(data[1:], start=2):
                if len(row) > 0 and str(row[0]) == search_id:
                    st.success(f"✅ الشكوى موجودة في {'المردودة' if in_responded else 'الأرشيف' if in_archive else 'النشطة'}")
                    render_complaint(sheet_obj, i, row, in_responded=in_responded, in_archive=in_archive)
                    found = True
                    break
            if found:
                break
        if not found:
            st.error("⚠️ لم يتم العثور على الشكوى")

    st.header("➕ تسجيل شكوى جديدة")
    with st.form("add_complaint", clear_on_submit=True):
        comp_id   = st.text_input("🆔 رقم الشكوى")
        comp_type = st.selectbox("📌 نوع الشكوى", ["اختر نوع الشكوى..."] + types_list)
        notes     = st.text_area("📝 ملاحظات الشكوى")
        action    = st.text_area("✅ الإجراء المتخذ")
        outbound_awb = st.text_input("✏️ Outbound AWB")
        inbound_awb  = st.text_input("✏️ Inbound AWB")
        submitted = st.form_submit_button("➕ إضافة")

        if submitted:
            if comp_id.strip() and comp_type != "اختر نوع الشكوى...":
                try:
                    complaints_recs = complaints_sheet.get_all_records()
                except Exception:
                    complaints_recs = []
                try:
                    responded_recs = responded_sheet.get_all_records()
                except Exception:
                    responded_recs = []
                try:
                    archive_recs = archive_sheet.get_all_records()
                except Exception:
                    archive_recs = []

                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                all_active_ids  = [str(c.get("ID","")) for c in complaints_recs] + [str(r.get("ID","")) for r in responded_recs]
                all_archive_ids = [str(a.get("ID","")) for a in archive_recs]

                if comp_id in all_active_ids:
                    st.error("⚠️ الشكوى موجودة بالفعل في النشطة أو المردودة")
                elif comp_id in all_archive_ids:
                    for idx, row in enumerate(archive_sheet.get_all_values()[1:], start=2):
                        if str(row[0]) == comp_id:
                            if safe_append(complaints_sheet, [comp_id, row[1] if len(row)>1 else "", row[2] if len(row)>2 else "", row[3] if len(row)>3 else "", date_now, "🔄 مسترجعة", row[6] if len(row)>6 else "", row[7] if len(row)>7 else ""]):
                                if safe_delete(archive_sheet, idx):
                                    st.success("✅ الشكوى كانت في الأرشيف وتمت إعادتها للنشطة")
                            break
                else:
                    if action.strip():
                        if safe_append(responded_sheet, [comp_id, comp_type, notes, action, date_now, "", outbound_awb, inbound_awb]):
                            st.success("✅ تم تسجيل الشكوى في المردودة")
                    else:
                        if safe_append(complaints_sheet, [comp_id, comp_type, notes, "", date_now, "", outbound_awb, inbound_awb]):
                            st.success("✅ تم تسجيل الشكوى في النشطة")
            else:
                st.error("⚠️ لازم تدخل رقم الشكوى وتختار نوع صحيح")

    st.header("📋 الشكاوى النشطة:")
    active_notes = complaints_sheet.get_all_values()
    if len(active_notes) > 1:
        for i, row in enumerate(active_notes[1:], start=2):
            render_complaint(complaints_sheet, i, row)
    else:
        st.info("لا توجد شكاوى نشطة حالياً.")

    st.header("✅ الإجراءات المردودة حسب النوع:")
    responded_notes = responded_sheet.get_all_values()
    if len(responded_notes) > 1:
        types_in_responded = list({row[1] for row in responded_notes[1:]})
        for complaint_type in types_in_responded:
            with st.expander(f"📌 نوع الشكوى: {complaint_type}"):
                type_rows = [(i, row) for i, row in enumerate(responded_notes[1:], start=2) if row[1] == complaint_type]
                followup_1, followup_2, others = [], [], []
                for i, row in type_rows:
                    comp_id     = row[0]
                    outbound_awb = row[6] if len(row) > 6 else ""
                    inbound_awb  = row[7] if len(row) > 7 else ""
                    rw_record = get_returnwarehouse_record(comp_id)
                    delivered = any("Delivered" in cached_aramex_status(awb) for awb in [outbound_awb, inbound_awb] if awb)
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

    st.markdown("---")
    st.header("🚚 معلق ارامكس")
    with st.form("add_aramex", clear_on_submit=True):
        order_id_ar = st.text_input("🔢 رقم الطلب")
        status_ar   = st.text_input("📌 الحالة")
        action_ar   = st.text_area("✅ الإجراء المتخذ")
        submitted_ar = st.form_submit_button("➕ إضافة")
        if submitted_ar:
            if order_id_ar.strip() and status_ar.strip() and action_ar.strip():
                date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if safe_append(aramex_sheet, [order_id_ar, status_ar, date_now, action_ar]):
                    st.success("✅ تم تسجيل الطلب")
            else:
                st.error("⚠️ لازم تدخل رقم الطلب + الحالة + الإجراء")

    st.subheader("📋 قائمة الطلبات المعلقة")
    aramex_pending = aramex_sheet.get_all_values()
    if len(aramex_pending) > 1:
        for i, row in enumerate(aramex_pending[1:], start=2):
            while len(row) < 4:
                row.append("")
            order_id_p, status_p, date_added_p, action_p = row[0], row[1], row[2], row[3]
            with st.expander(f"📦 طلب {order_id_p}"):
                st.write(f"📌 الحالة: {status_p}"); st.write(f"✅ الإجراء: {action_p}")
                st.caption(f"📅 تاريخ الإضافة: {date_added_p}")
                with st.form(key=f"form_aramex_{order_id_p}_{i}"):
                    new_status_p = st.text_input("✏️ عدل الحالة", value=status_p)
                    new_action_p = st.text_area("✏️ عدل الإجراء", value=action_p)
                    c1, c2, c3 = st.columns(3)
                    s_save = c1.form_submit_button("💾 حفظ")
                    s_del  = c2.form_submit_button("🗑️ حذف")
                    s_arch = c3.form_submit_button("📦 أرشفة")
                    if s_save:
                        safe_update(aramex_sheet, f"B{i}", [[new_status_p]])
                        safe_update(aramex_sheet, f"D{i}", [[new_action_p]])
                        st.success("✅ تم التعديل")
                    if s_del:
                        if safe_delete(aramex_sheet, i):
                            st.warning("🗑️ تم الحذف")
                    if s_arch:
                        if safe_append(aramex_archive, [order_id_p, new_status_p, date_added_p, new_action_p]):
                            if safe_delete(aramex_sheet, i):
                                st.success("♻️ تم الأرشفة")
    else:
        st.info("لا توجد شكاوى أرامكس معلقة.")

    st.markdown("---")
    st.header("📦 أرشيف أرامكس:")
    aramex_archived = aramex_archive.get_all_values()
    if len(aramex_archived) > 1:
        for i, row in enumerate(aramex_archived[1:], start=2):
            while len(row) < 4:
                row.append("")
            order_id_a, status_a, date_added_a, action_a = row[0], row[1], row[2], row[3]
            with st.expander(f"📦 أرشيف طلب {order_id_a}"):
                st.write(f"📌 الحالة: {status_a}"); st.write(f"✅ الإجراء: {action_a}")
                st.caption(f"📅 التاريخ: {date_added_a}")
                col1, col2 = st.columns(2)
                if col1.button(f"⬅️ إرجاع {order_id_a} لمعلق ارامكس", key=f"ret_{i}"):
                    if safe_append(aramex_sheet, [order_id_a, status_a, date_added_a, action_a]):
                        if safe_delete(aramex_archive, i):
                            st.success(f"✅ تم إعادة {order_id_a}")
                if col2.button(f"🗑️ حذف {order_id_a}", key=f"del_arch_{i}"):
                    if safe_delete(aramex_archive, i):
                        st.warning(f"🗑️ تم الحذف")
    else:
        st.info("لا توجد شكاوى أرامكس مؤرشفة.")

# ============================================================
# ====================== تبويب الشحن ========================
# ============================================================
with tab_shipping:
    st.header("📤 شحن جديد مع أرامكس")
    st.info("ارفع ملف Excel يحتوي على أعمدة: OrderNumber, ReferenceNumber, CustomerName, CustomerPhone, CustomerEmail, AddressLine, City, PostalCode, CountryCode, WeightKG, CODAmount, Description")

    col_set1, col_set2 = st.columns(2)
    with col_set1:
        default_pieces_ship = st.number_input("عدد القطع الافتراضي لكل الشحنات", min_value=1, value=1, key="default_pieces_ship")
    with col_set2:
        print_pdf = st.checkbox("فتح PDF للطباعة بعد إنشاء البوليصة", value=False)

    st.subheader("طلبات بعدد قطع مختلف (اختياري)")
    custom_col1, custom_col2 = st.columns(2)
    with custom_col1:
        custom_orders_ship = st.text_area("أرقام الطلبات (كل رقم في سطر)", height=100, key="custom_orders_ship")
    with custom_col2:
        custom_pieces_ship = st.text_area("عدد القطع لكل طلب (بالترتيب)", height=100, key="custom_pieces_ship")

    uploaded_ship = st.file_uploader("📂 ارفع ملف الإكسل", type=["xlsx"], key="upload_ship")

    if uploaded_ship and st.button("🚚 ابدأ تنفيذ الشحن", key="btn_ship"):
        df_ship = pd.read_excel(uploaded_ship)
        if "LabelURL" not in df_ship.columns:
            df_ship["LabelURL"] = ""
        if "TrackingNumber" not in df_ship.columns:
            df_ship["TrackingNumber"] = ""

        order_list  = [x.strip() for x in custom_orders_ship.replace("\n",",").split(",") if x.strip()]
        piece_list_raw = [x.strip() for x in custom_pieces_ship.replace("\n",",").split(",") if x.strip()]
        piece_list  = []
        for x in piece_list_raw:
            try:
                piece_list.append(int(x))
            except:
                piece_list.append(None)
        order_piece_map = dict(zip(order_list, piece_list))

        progress_bar = st.progress(0)
        status_text  = st.empty()
        total_rows   = len(df_ship)
        pdf_links    = []

        for idx, row in df_ship.iterrows():
            order_number = str(row.get("OrderNumber",""))
            num_pieces = order_piece_map.get(order_number) or int(default_pieces_ship)
            status_text.text(f"⏳ جاري معالجة الطلب {order_number} ...")

            tracking_id, label_url, err = create_aramex_shipment(row.to_dict(), num_pieces, is_return=False)

            if err:
                st.error(f"❌ الطلب {order_number}: {err}")
            else:
                df_ship.at[idx, "TrackingNumber"] = tracking_id
                df_ship.at[idx, "LabelURL"]       = label_url
                st.success(f"✅ الطلب {order_number} → رقم تتبع: {tracking_id}")

                if label_url:
                    pdf_bytes = download_pdf_bytes(label_url)
                    if pdf_bytes:
                        pdf_links.append((order_number, pdf_bytes, label_url))

            progress_bar.progress((idx + 1) / total_rows)

        status_text.text("✅ اكتمل الشحن!")

        # تحميل Excel المحدث
        output_buffer = io.BytesIO()
        df_ship.to_excel(output_buffer, index=False)
        output_buffer.seek(0)
        st.download_button(
            "⬇️ تحميل ملف الإكسل المحدث (مع أرقام التتبع)",
            data=output_buffer,
            file_name="shipments_with_tracking_updated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # عرض روابط PDF
        if pdf_links:
            st.subheader("📄 بوليصات الشحن")
            for order_number, pdf_bytes, label_url in pdf_links:
                col_a, col_b = st.columns([3,1])
                with col_a:
                    st.download_button(
                        f"⬇️ تحميل بوليصة الطلب {order_number}",
                        data=pdf_bytes,
                        file_name=f"{order_number}.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_ship_{order_number}"
                    )
                with col_b:
                    if print_pdf:
                        b64 = base64.b64encode(pdf_bytes).decode()
                        st.markdown(
                            f'<a href="data:application/pdf;base64,{b64}" target="_blank">🖨️ فتح للطباعة</a>',
                            unsafe_allow_html=True
                        )

# ============================================================
# ===================== تبويب الإرجاع =======================
# ============================================================
with tab_return:
    st.header("📥 إرجاع شحنة مع أرامكس")
    st.info("ارفع ملف Excel بنفس التنسيق - الشاحن سيكون الزبون والمستلم سيكون المستودع تلقائياً")

    col_ret1, col_ret2 = st.columns(2)
    with col_ret1:
        default_pieces_ret = st.number_input("عدد القطع الافتراضي", min_value=1, value=1, key="default_pieces_ret")
    with col_ret2:
        print_pdf_ret = st.checkbox("فتح PDF للطباعة", value=False, key="print_pdf_ret")

    custom_col3, custom_col4 = st.columns(2)
    with custom_col3:
        custom_orders_ret = st.text_area("أرقام الطلبات بعدد مختلف (كل رقم في سطر)", height=100, key="custom_orders_ret")
    with custom_col4:
        custom_pieces_ret = st.text_area("عدد القطع لكل طلب (بالترتيب)", height=100, key="custom_pieces_ret")

    uploaded_ret = st.file_uploader("📂 ارفع ملف الإكسل", type=["xlsx"], key="upload_ret")

    if uploaded_ret and st.button("🔄 ابدأ تنفيذ الإرجاع", key="btn_ret"):
        df_ret = pd.read_excel(uploaded_ret)
        if "LabelURL" not in df_ret.columns:
            df_ret["LabelURL"] = ""
        if "TrackingNumber" not in df_ret.columns:
            df_ret["TrackingNumber"] = ""

        order_list_ret  = [x.strip() for x in custom_orders_ret.replace("\n",",").split(",") if x.strip()]
        piece_list_ret_raw = [x.strip() for x in custom_pieces_ret.replace("\n",",").split(",") if x.strip()]
        piece_list_ret = []
        for x in piece_list_ret_raw:
            try:
                piece_list_ret.append(int(x))
            except:
                piece_list_ret.append(None)
        order_piece_map_ret = dict(zip(order_list_ret, piece_list_ret))

        progress_bar_ret = st.progress(0)
        status_text_ret  = st.empty()
        total_rows_ret   = len(df_ret)
        pdf_links_ret    = []

        for idx, row in df_ret.iterrows():
            order_number = str(row.get("OrderNumber",""))
            num_pieces = order_piece_map_ret.get(order_number) or int(default_pieces_ret)
            status_text_ret.text(f"⏳ جاري معالجة الإرجاع {order_number} ...")

            tracking_id, label_url, err = create_aramex_shipment(row.to_dict(), num_pieces, is_return=True)

            if err:
                st.error(f"❌ الطلب {order_number}: {err}")
            else:
                df_ret.at[idx, "TrackingNumber"] = tracking_id
                df_ret.at[idx, "LabelURL"]       = label_url
                st.success(f"✅ الإرجاع {order_number} → رقم تتبع: {tracking_id}")

                if label_url:
                    pdf_bytes = download_pdf_bytes(label_url)
                    if pdf_bytes:
                        pdf_links_ret.append((order_number, pdf_bytes, label_url))

            progress_bar_ret.progress((idx + 1) / total_rows_ret)

        status_text_ret.text("✅ اكتمل الإرجاع!")

        output_buffer_ret = io.BytesIO()
        df_ret.to_excel(output_buffer_ret, index=False)
        output_buffer_ret.seek(0)
        st.download_button(
            "⬇️ تحميل ملف الإكسل المحدث",
            data=output_buffer_ret,
            file_name="returns_with_tracking.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if pdf_links_ret:
            st.subheader("📄 بوليصات الإرجاع")
            for order_number, pdf_bytes, label_url in pdf_links_ret:
                col_a, col_b = st.columns([3,1])
                with col_a:
                    st.download_button(
                        f"⬇️ تحميل بوليصة الإرجاع {order_number}",
                        data=pdf_bytes,
                        file_name=f"return_{order_number}.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_ret_{order_number}"
                    )
                with col_b:
                    if print_pdf_ret:
                        b64 = base64.b64encode(pdf_bytes).decode()
                        st.markdown(
                            f'<a href="data:application/pdf;base64,{b64}" target="_blank">🖨️ فتح للطباعة</a>',
                            unsafe_allow_html=True
                        )

# ============================================================
# =================== تبويب طلب المندوب ====================
# ============================================================
with tab_pickup:
    st.header("🚚 طلب مندوب أرامكس")

    pickup_mode = st.radio(
        "طريقة إدخال البيانات",
        ["📂 من ملف Excel (تم إنشاء الشحنات مسبقاً)", "✏️ إدخال يدوي لطلب واحد"],
        horizontal=True
    )

    if pickup_mode == "📂 من ملف Excel (تم إنشاء الشحنات مسبقاً)":
        st.info("ارفع ملف الإكسل المحدث (shipments_with_tracking_updated.xlsx) الناتج من تبويب الشحن")
        uploaded_pickup = st.file_uploader("📂 ارفع ملف الإكسل", type=["xlsx"], key="upload_pickup")

        if uploaded_pickup and st.button("🚚 طلب المندوب لكل الشحنات", key="btn_pickup_excel"):
            df_pickup = pd.read_excel(uploaded_pickup)
            if "PickupReference" not in df_pickup.columns:
                df_pickup["PickupReference"] = ""

            progress_bar_pu = st.progress(0)
            status_text_pu  = st.empty()
            total_pu = len(df_pickup)

            for idx, row in df_pickup.iterrows():
                order_number = str(row.get("ReferenceNumber", row.get("OrderNumber","غير معروف")))
                status_text_pu.text(f"⏳ جاري طلب مندوب للطلب {order_number} ...")

                shipper = {
                    "name":     str(row.get("CustomerName","")),
                    "phone":    str(row.get("CustomerPhone","0000000000")),
                    "email":    str(row.get("CustomerEmail","")),
                    "line1":    str(row.get("PickupAddress", row.get("AddressLine",""))),
                    "city":     str(row.get("City","Riyadh")),
                    "postcode": str(row.get("PostalCode","")),
                }
                try:
                    num_p = int(row.get("Pieces", 1))
                except:
                    num_p = 1
                try:
                    weight = float(row.get("WeightKG", 1.0))
                except:
                    weight = 1.0

                pickup_ref, err = request_pickup_aramex(shipper, num_p, weight, order_number, shipper["line1"])
                if err:
                    st.error(f"❌ الطلب {order_number}: {err}")
                    df_pickup.at[idx, "PickupReference"] = f"خطأ: {err}"
                else:
                    st.success(f"✅ الطلب {order_number} → رقم المندوب: {pickup_ref}")
                    df_pickup.at[idx, "PickupReference"] = pickup_ref

                progress_bar_pu.progress((idx + 1) / total_pu)

            status_text_pu.text("✅ اكتمل طلب المندوبين!")
            output_pu = io.BytesIO()
            df_pickup.to_excel(output_pu, index=False)
            output_pu.seek(0)
            st.download_button(
                "⬇️ تحميل الإكسل برقم المندوب",
                data=output_pu,
                file_name="shipments_with_pickup.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    else:
        st.subheader("✏️ إدخال يدوي")
        with st.form("manual_pickup"):
            col_pu1, col_pu2 = st.columns(2)
            with col_pu1:
                pu_name    = st.text_input("اسم العميل")
                pu_phone   = st.text_input("رقم الجوال")
                pu_address = st.text_input("العنوان")
                pu_city    = st.text_input("المدينة", value="Riyadh")
            with col_pu2:
                pu_order   = st.text_input("رقم الطلب / المرجع")
                pu_pieces  = st.number_input("عدد القطع", min_value=1, value=1)
                pu_weight  = st.number_input("الوزن (كجم)", min_value=0.1, value=1.0)

            submitted_manual_pu = st.form_submit_button("🚚 طلب المندوب")
            if submitted_manual_pu:
                if pu_name and pu_phone and pu_address and pu_order:
                    shipper = {"name": pu_name, "phone": pu_phone, "email": "", "line1": pu_address, "city": pu_city, "postcode": ""}
                    pickup_ref, err = request_pickup_aramex(shipper, int(pu_pieces), float(pu_weight), pu_order, pu_address)
                    if err:
                        st.error(f"❌ {err}")
                    else:
                        st.success(f"✅ تم طلب المندوب بنجاح | رقم المرجع: {pickup_ref}")
                else:
                    st.error("⚠️ يرجى تعبئة جميع الحقول المطلوبة")

# ============================================================
# ================== تبويب بيانات العملاء ===================
# ============================================================
with tab_customers:
    st.header("🧑‍💼 إدارة بيانات العملاء وتجهيز الشحنات")
    st.info(
        "هذا القسم يحل محل برنامج Access المحلي. "
        "أدخل أرقام الطلبات يدوياً أو ارفع Excel من Access، "
        "ثم صدّر الجدول جاهزاً للشحن."
    )

    action_options = ["ارسال صيانه", "إرجاع", "الصيانة", "الاستبدال", "إرسال الاستبدال", "إرسال نواقص"]
    action_suffix  = {
        "إرجاع": "*", "الصيانة": "#", "الاستبدال": "*#",
        "إرسال الاستبدال": "*#&", "إرسال نواقص": "&", "ارسال صيانه": "#&"
    }

    CUSTOMERS_COLUMNS = [
        "Order Number", "Order Number*", "First Name (Billing)", "Phone (Billing)", "MAIL",
        "Address 1&2 (Billing)", "City (Billing)", "PostalCode", "CountryCode", "WeightKG", "CODAmount", "Description"
    ]

    if "customers_df" not in st.session_state:
        st.session_state.customers_df = pd.DataFrame(columns=CUSTOMERS_COLUMNS)

    tab_cust_a, tab_cust_b = st.tabs(["✏️ إدخال يدوي", "📂 رفع من Excel"])

    with tab_cust_a:
        st.subheader("إدخال طلب يدوي")
        with st.form("add_customer_manual", clear_on_submit=True):
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                cust_order  = st.text_input("رقم الطلب")
                cust_action = st.selectbox("الإجراء", action_options)
            with col_c2:
                cust_name   = st.text_input("اسم العميل")
                cust_phone  = st.text_input("رقم الجوال")
            with col_c3:
                cust_city_ar = st.text_input("المدينة (بالعربي)")
                cust_address = st.text_input("العنوان")

            col_c4, col_c5, col_c6 = st.columns(3)
            with col_c4:
                cust_email   = st.text_input("البريد الإلكتروني")
            with col_c5:
                cust_weight  = st.number_input("الوزن (كجم)", min_value=0.1, value=3.0)
                cust_cod     = st.number_input("مبلغ الدفع عند الاستلام", min_value=0.0, value=0.0)
            with col_c6:
                cust_desc    = st.text_input("الوصف", value="منتجات")
                cust_postal  = st.text_input("الرمز البريدي", value="")

            submitted_cust = st.form_submit_button("➕ إضافة للجدول")
            if submitted_cust:
                if cust_order.strip() and cust_name.strip():
                    suffix = action_suffix.get(cust_action, "")
                    city_en = CITY_MAP.get(cust_city_ar.strip(), cust_city_ar.strip())
                    new_row = {
                        "Order Number":          cust_order,
                        "Order Number*":         cust_order + suffix,
                        "First Name (Billing)":  cust_name,
                        "Phone (Billing)":       cust_phone,
                        "MAIL":                  cust_email,
                        "Address 1&2 (Billing)": cust_address,
                        "City (Billing)":        city_en,
                        "PostalCode":            cust_postal,
                        "CountryCode":           "SA",
                        "WeightKG":              cust_weight,
                        "CODAmount":             cust_cod,
                        "Description":           cust_desc
                    }
                    st.session_state.customers_df = pd.concat(
                        [st.session_state.customers_df, pd.DataFrame([new_row])],
                        ignore_index=True
                    )
                    st.success(f"✅ تم إضافة الطلب {cust_order}")
                else:
                    st.error("⚠️ رقم الطلب واسم العميل مطلوبان")

    with tab_cust_b:
        st.subheader("📂 رفع بيانات من Excel")
        st.caption("ارفع ملف Excel مُصدَّر من Access أو أي مصدر آخر")
        uploaded_cust = st.file_uploader("ارفع ملف Excel", type=["xlsx","xls"], key="upload_cust")
        selected_action_bulk = st.selectbox("الإجراء لكل الطلبات المرفوعة", action_options, key="bulk_action")

        if uploaded_cust and st.button("📥 تحميل البيانات", key="btn_load_cust"):
            df_cust_upload = pd.read_excel(uploaded_cust)
            suffix = action_suffix.get(selected_action_bulk, "")
            rows_added = 0
            for _, row in df_cust_upload.iterrows():
                order_no = str(row.get("Order Number", row.get("رقم الطلب", "")))
                if not order_no.strip():
                    continue
                city_ar = str(row.get("City (Billing)", row.get("المدينة", "")))
                city_en = CITY_MAP.get(city_ar.strip(), city_ar.strip())
                new_row = {
                    "Order Number":          order_no,
                    "Order Number*":         order_no + suffix,
                    "First Name (Billing)":  str(row.get("First Name (Billing)", row.get("الاسم", ""))),
                    "Phone (Billing)":       str(row.get("Phone (Billing)", row.get("الجوال", ""))),
                    "MAIL":                  str(row.get("MAIL", row.get("البريد", ""))),
                    "Address 1&2 (Billing)": str(row.get("Address 1&2 (Billing)", row.get("العنوان", ""))),
                    "City (Billing)":        city_en,
                    "PostalCode":            str(row.get("PostalCode", row.get("الرمز البريدي", ""))),
                    "CountryCode":           str(row.get("CountryCode","SA")),
                    "WeightKG":              row.get("WeightKG", 3),
                    "CODAmount":             row.get("CODAmount", 0),
                    "Description":           str(row.get("Description","منتجات"))
                }
                st.session_state.customers_df = pd.concat(
                    [st.session_state.customers_df, pd.DataFrame([new_row])],
                    ignore_index=True
                )
                rows_added += 1
            st.success(f"✅ تم تحميل {rows_added} طلب")

    st.markdown("---")
    st.subheader("📋 جدول الطلبات الحالية")

    if not st.session_state.customers_df.empty:
        st.dataframe(st.session_state.customers_df, use_container_width=True)

        col_exp1, col_exp2, col_exp3 = st.columns(3)
        with col_exp1:
            output_cust = io.BytesIO()
            st.session_state.customers_df.to_excel(output_cust, index=False)
            output_cust.seek(0)
            st.download_button(
                "⬇️ تصدير الجدول كـ Excel (جاهز للشحن)",
                data=output_cust,
                file_name="Orders_Output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col_exp2:
            del_order = st.text_input("رقم الطلب لحذفه من الجدول")
        with col_exp3:
            if st.button("🗑️ حذف الطلب من الجدول", key="del_cust_row"):
                before = len(st.session_state.customers_df)
                st.session_state.customers_df = st.session_state.customers_df[
                    st.session_state.customers_df["Order Number"].astype(str) != del_order.strip()
                ].reset_index(drop=True)
                after = len(st.session_state.customers_df)
                if before != after:
                    st.success(f"✅ تم حذف الطلب {del_order}")
                else:
                    st.warning(f"⚠️ لم يُعثر على الطلب {del_order}")

        if st.button("🗑️ مسح كل الجدول", key="clear_cust"):
            st.session_state.customers_df = pd.DataFrame(columns=CUSTOMERS_COLUMNS)
            st.success("✅ تم مسح الجدول")
    else:
        st.info("الجدول فارغ. أضف طلبات من التبويبات أعلاه.")

    st.markdown("---")
    st.caption("💡 بعد التصدير، ارفع الملف في تبويب 'شحن أرامكس' أو 'إرجاع أرامكس' لإنشاء البوليصات مباشرة.")

st.caption("⚡ النظام متكامل: بيانات العملاء ← شحن/إرجاع أرامكس ← طلب مندوب ← إدارة الشكاوى")
