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
    """دالة للاتصال وقراءة العطل مع معالجة استثناءات بيئة السحابة"""
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
            except Exception as e:
                return -2 # خطأ في تبادل البيانات
            finally:
                client.close()
        else:
            return -3 # فشل فتح المنفذ
            
    except Exception as e:
        # التقاط أخطاء عدم توفر مكتبة pyserial أو غياب منافذ COM في السحابة
        return -4 

# واجهة الشريط الجانبي (Sidebar) لإعدادات الاتصال
st.sidebar.header("⚙️ إعدادات الاتصال (Modbus RTU)")
port = st.sidebar.text_input("المنفذ (Port)", value="COM3" if st.sidebar.checkbox("Windows") else "/dev/ttyUSB0")
baudrate = st.sidebar.selectbox("سرعة النقل (Baudrate)", [9600, 19200, 38400, 115200])
slave_id = st.sidebar.number_input("معرف الجهاز (Slave ID)", min_value=1, max_value=247, value=1)
register_address = st.sidebar.number_input("عنوان مسجل العطل (Hex to Dec)", value=256) # 256 يوازي 0x0100

st.title("⚡ لوحة مراقبة أعطال محولات الطاقة الشمسية")
st.markdown("---")

# أزرار التحكم
col1, col2 = st.columns(2)
with col1:
    check_btn = st.button("🔄 فحص حالة المحول الآن", use_container_width=True)
with col2:
    reset_btn = st.button("⚠️ إرسال أمر إعادة الضبط (Reset)", type="primary", use_container_width=True)

# مساحة عرض النتائج
status_placeholder = st.empty()

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
                
            # عرض عداد مبسط
            st.metric(label="كود مسجل العطل (Register Value)", value=fault_code)
            
        elif fault_code == -1:
            st.error("❌ فشل في قراءة المسجل. تأكد من صحة عنوان المسجل (Register Address).")
        elif fault_code == -2:
            st.error("❌ حدث خطأ أثناء محاولة تبادل البيانات (Communication Error).")
        elif fault_code == -3:
            st.error(f"❌ لم نتمكن من فتح المنفذ {port}. تأكد من توصيل الكابل وعدم استخدامه من برنامج آخر.")
        elif fault_code == -4:
            st.error("☁️ **خطأ بيئة سحابية:** التطبيق يعمل الآن على خوادم Streamlit السحابية ولا يمكنه الوصول إلى منافذ (COM/USB) المحلية الخاصة بك. للقراءة الفعلية، يجب تشغيل الكود محلياً أو استخدام بوابة IoT (Modbus TCP).")

if reset_btn:
    st.warning("هذه الخاصية تتطلب كتابة قيمة على مسجل إعادة الضبط (أضف دالة Write Register هنا وفقاً لكتيب المحول).")
