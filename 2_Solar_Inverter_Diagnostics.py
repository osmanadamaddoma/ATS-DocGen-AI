# المسار: pages/2_Solar_Inverter_Diagnostics.py
import streamlit as st
import sys
import os

# إضافة المسار الرئيسي للوصول إلى مجلد data_ingestion
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data_ingestion.inverter_modbus import SolarInverterDiagnostics

st.set_page_config(page_title="تشخيص أعطال المحول الشمسي", layout="wide")
st.title("⚡ وحدة مراقبة أعطال محولات الطاقة الشمسية")

# إعدادات الاتصال
st.sidebar.header("⚙️ إعدادات الاتصال")
port = st.sidebar.text_input("المنفذ", "/dev/ttyUSB0")
baudrate = st.sidebar.selectbox("سرعة النقل", [9600, 19200, 38400])
slave_id = st.sidebar.number_input("معرف الجهاز (Slave ID)", value=1)
register_address = st.sidebar.number_input("عنوان المسجل", value=256)

if st.button("🔄 فحص الحالة اللحظية", type="primary"):
    inverter = SolarInverterDiagnostics(port=port, baudrate=baudrate, slave_id=slave_id)
    with st.spinner("جاري الاتصال بالمحول..."):
        fault_code = inverter.read_fault_status(register_address=register_address)
        
        if fault_code == 0:
            st.success("✅ النظام يعمل بشكل طبيعي.")
        elif fault_code > 0:
            st.error(f"🚨 تم رصد عطل! كود العطل: {fault_code}")
        else:
            st.warning("⚠️ تعذر الاتصال بالمحول. يرجى التحقق من الكابلات أو إعدادات المنفذ.")
