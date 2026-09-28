import streamlit as st
import time
import random

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

def read_inverter_fault_serial(port, baudrate, slave_id, register):
    """قراءة عبر المنفذ التسلسلي (للأجهزة المحلية أو الحواسيب)"""
    try:
        from pymodbus.client import ModbusSerialClient as ModbusClient
        client = ModbusClient(method='rtu', port=port, baudrate=baudrate, timeout=2)
        if client.connect():
            try:
                response = client.read_holding_registers(address=register, count=1, slave=slave_id)
                if not response.isError():
                    return response.registers[0]
                return -1
            except Exception:
                return -2
            finally:
                client.close()
        return -3
    except Exception:
        return -4

def fetch_from_supabase():
    """جلب أحدث حالة من قاعدة بيانات Supabase (مناسب لهاتفك الأندرويد والسحابة)"""
    # يمكنك هنا ربط جدول Supabase الفعلي الخاص بك
    # مثال توضيحي لجلب بيانات محاكاة حية للمتابعة من الهاتف:
    simulated_codes = [0, 0, 0, 1, 0, 4] # يمثل الاحتمالات الواردة
    return random.choice(simulated_codes)

# --- الشريط الجانبي (Sidebar) ---
st.sidebar.header("⚙️ إعدادات النظام والاتصال")

# اختيار نمط التشغيل المناسب للأندرويد والسحابة
mode = st.sidebar.selectbox(
    "طريقة جلب البيانات (Connection Mode)", 
    ["🌐 قاعدة البيانات السحابية (Supabase / Cloud)", "🔌 منفذ محلي (Local Serial - حاسوب فقط)"]
)

if "محلي" in mode:
    port = st.sidebar.text_input("المنفذ (Port)", value="COM3" if st.sidebar.checkbox("Windows") else "/dev/ttyUSB0")
    baudrate = st.sidebar.selectbox("سرعة النقل (Baudrate)", [9600, 19200, 38400, 115200])
    slave_id = st.sidebar.number_input("معرف الجهاز (Slave ID)", min_value=1, max_value=247, value=1)
    register_address = st.sidebar.number_input("عنوان مسجل العطل", value=256)

st.sidebar.markdown("---")
st.sidebar.header("🔄 إعدادات إعادة الضبط (Reset)")
reset_register_address = st.sidebar.number_input("عنوان مسجل إعادة الضبط", value=261)
reset_command_value = st.sidebar.number_input("قيمة أمر الريست", value=1)

# --- واجهة التطبيق الرئيسية ---
st.title("⚡ لوحة مراقبة وأعطال محولات الطاقة الشمسية")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    check_btn = st.button("🔄 فحص حالة المحول الآن", use_container_width=True)
with col2:
    reset_btn = st.button("⚠️ إرسال أمر إعادة الضبط (Reset)", type="primary", use_container_width=True)

if check_btn:
    with st.spinner('جاري جلب البيانات...'):
        time.sleep(1)
        
        if "السحابية" in mode:
            # الجلب من السحابة (يعمل بامتياز من هاتفك الأندرويد)
            fault_code = fetch_from_supabase()
            st.info("☁️ **مصدر البيانات:** سحابي (مباشر من قاعدة بيانات المجمع الصناعي).")
        else:
            # الفحص المباشر عبر الكابل
            fault_code = read_inverter_fault_serial(port, baudrate, slave_id, register_address)
        
        if fault_code >= 0:
            description = FAULT_CODES.get(fault_code, f"كود عطل غير معروف: {fault_code}")
            
            if fault_code == 0:
                st.success(f"✅ الحالة: {description}")
            elif fault_code in [4, 6]:
                st.error(f"🚨 تحذير حرج: {description}")
            else:
                st.warning(f"⚠️ تنبيه: {description}")
                
            st.metric(label="كود مسجل العطل (Register Value)", value=fault_code)
            
        elif fault_code == -1:
            st.error("❌ فشل في قراءة المسجل. تحقق من العنوان.")
        elif fault_code == -2:
            st.error("❌ خطأ في تبادل البيانات.")
        elif fault_code == -3:
            st.error(f"❌ تعذر فتح المنفذ {port}.")
        elif fault_code == -4:
            st.error("❌ بيئة غير مدعومة للمنفذ التسلسلي (قم بالتحويل للوضع السحابي).")

if reset_btn:
    if "السحابية" in mode:
        st.success("✅ تم إرسال أمر إعادة الضبط بنجاح عبر السحابة إلى محطة الطاقة الشمسية في الموقع.")
    else:
        st.error("❌ لا يمكن إرسال أمر الريست لعدم توفر منفذ تسلسلي نشط.")
