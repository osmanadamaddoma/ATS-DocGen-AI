import streamlit as st
import time

# إعداد الصفحة
st.set_page_config(page_title="Inverter Diagnostics Dashboard", layout="wide")

# قاموس الأعطال
FAULT_CODES = {
    0: "النظام يعمل بشكل طبيعي (No Fault)",
    1: "جهد الشبكة غير طبيعي (Grid Voltage Out of Range)",
    2: "تردد الشبكة غير طبيعي (Grid Frequency Out of Range)",
    3: "ارتفاع جهد الألواح (PV Over Voltage)",
    4: "ارتفاع حرارة المحول (Inverter Over Temperature)",
    5: "انخفاض جهد البطارية (Battery Low Voltage)",
    6: "قصر في الدائرة أو زيادة حمل (Short Circuit / Overload)"
}

def read_inverter_fault(port, baudrate, slave_id, register):
    """دالة الاتصال وقراءة العطل من المسجل"""
    try:
        from pymodbus.client import ModbusSerialClient as ModbusClient
        client = ModbusClient(method='rtu', port=port, baudrate=baudrate, timeout=2)
        
        if client.connect():
            try:
                response = client.read_holding_registers(address=register, count=1, slave=slave_id)
                if not response.isError():
                    return response.registers[0]
                else:
                    return -1 # خطأ في القراءة
            except Exception:
                return -2 # خطأ في تبادل البيانات
            finally:
                client.close()
        else:
            return -3 # فشل فتح المنفذ
            
    except Exception:
        return -4 # خطأ بيئة سحابية / عدم توفر المنفذ الفيزيائي

def write_inverter_reset(port, baudrate, slave_id, reset_register, reset_value):
    """دالة كتابة أمر إعادة الضبط على مسجل المحول"""
    try:
        from pymodbus.client import ModbusSerialClient as ModbusClient
        client = ModbusClient(method='rtu', port=port, baudrate=baudrate, timeout=2)
        
        if client.connect():
            try:
                # كتابة القيمة على المسجل المحدد (Holding Register)
                response = client.write_register(address=reset_register, value=reset_value, slave=slave_id)
                if not response.isError():
                    return 1 # تم الإرسال بنجاح
                else:
                    return -1 # رفض المحول للأمر
            except Exception:
                return -2
            finally:
                client.close()
        else:
            return -3
            
    except Exception:
        return -4

# واجهة الشريط الجانبي (Sidebar) لإعدادات الاتصال
st.sidebar.header("⚙️ إعدادات الاتصال (Modbus RTU)")
port = st.sidebar.text_input("المنفذ (Port)", value="COM3" if st.sidebar.checkbox("Windows") else "/dev/ttyUSB0")
baudrate = st.sidebar.selectbox("سرعة النقل (Baudrate)", [9600, 19200, 38400, 115200])
slave_id = st.sidebar.number_input("معرف الجهاز (Slave ID)", min_value=1, max_value=247, value=1)
register_address = st.sidebar.number_input("عنوان مسجل العطل (Fault Register)", value=256) # 256 = 0x0100

st.sidebar.markdown("---")
st.sidebar.header("🔄 إعدادات إعادة الضبط (Reset)")
reset_register_address = st.sidebar.number_input("عنوان مسجل إعادة الضبط (Reset Register)", value=261) # مثال 0x0105
reset_command_value = st.sidebar.number_input("قيمة أمر الريست (Reset Value)", value=1)

st.title("⚡ لوحة مراقبة وأعطال محولات الطاقة الشمسية")
st.markdown("---")

# أزرار التحكم
col1, col2 = st.columns(2)
with col1:
    check_btn = st.button("🔄 فحص حالة المحول الآن", use_container_width=True)
with col2:
    reset_btn = st.button("⚠️ إرسال أمر إعادة الضبط (Reset)", type="primary", use_container_width=True)

# مساحة عرض النتائج
if check_btn:
    with st.spinner('جاري محاولة الاتصال وقراءة البيانات من المحول...'):
        fault_code = read_inverter_fault(port, baudrate, slave_id, register_address)
        
        if fault_code >= 0:
            description = FAULT_CODES.get(fault_code, f"كود عطل غير معروف: {fault_code}")
            
            if fault_code == 0:
                st.success(f"✅ الحالة: {description}")
            elif fault_code in [4, 6]: # أعطال حرجة
                st.error(f"🚨 تحذير حرج: {description}")
            else:
                st.warning(f"⚠️ تنبيه: {description}")
                
            st.metric(label="كود مسجل العطل (Register Value)", value=fault_code)
            
        elif fault_code == -1:
            st.error("❌ فشل في قراءة المسجل. تأكد من صحة عنوان المسجل (Register Address).")
        elif fault_code == -2:
            st.error("❌ حدث خطأ أثناء محاولة تبادل البيانات (Communication Error).")
        elif fault_code == -3:
            st.error(f"❌ لم نتمكن من فتح المنفذ {port}. تأكد من توصيل الكابل وعدم استخدامه من برنامج آخر.")
        elif fault_code == -4:
            st.error("☁️ **خطأ بيئة سحابية:** التطبيق يعمل على Streamlit Cloud ولا يمكنه الاتصال بمنافذ COM/USB المحلية. للتشغيل الميداني الفعلي استخدم التشغيل المحلي أو بوابة Modbus TCP.")

if reset_btn:
    with st.spinner('جاري إرسال أمر إعادة الضبط إلى المحول...'):
        res = write_inverter_reset(port, baudrate, slave_id, reset_register_address, reset_command_value)
        
        if res == 1:
            st.success(f"✅ تم إرسال أمر إعادة الضبط (القيمة {reset_command_value}) بنجاح إلى المسجل {reset_register_address}.")
        elif res == -1:
            st.error("❌ رفض المحول استقبال أمر إعادة الضبط. تحقق من صلاحية المسجل أو نمط التشغيل.")
        elif res == -2:
            st.error("❌ خطأ في تبادل البيانات أثناء كتابة أمر الريست.")
        elif res == -3:
            st.error(f"❌ تعذر فتح المنفذ {port} لإرسال الأمر.")
        elif res == -4:
            st.error("☁️ **خطأ بيئة سحابية:** لا يمكن إرسال أوامر التحكم مباشرة عبر المنافذ التسلسلية من السحابة.")
