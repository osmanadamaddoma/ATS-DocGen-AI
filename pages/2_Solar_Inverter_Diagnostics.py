import streamlit as st
import time
import random
import math

# إعداد الصفحة (يجب أن يكون أول سطر)
st.set_page_config(page_title="AI Solar & Inverter Diagnostics", layout="wide", page_icon="⚡")

# --- دوال الاتصال وقواعد البيانات ---
FAULT_CODES = {
    0: "النظام يعمل بشكل طبيعي (No Fault)",
    1: "جهد الشبكة غير طبيعي (Grid Voltage Out of Range)",
    2: "تردد الشبكة غير طبيعي (Grid Frequency Out of Range)",
    3: "ارتفاع جهد الألواح (PV Over Voltage)",
    4: "ارتفاع حرارة المحول (Inverter Over Temperature)",
    5: "انخفاض جهد البطارية (Battery Low Voltage)",
    6: "قصر في الدائرة أو زيادة حمل (Short Circuit / Overload)"
}

def fetch_from_supabase():
    """محاكاة جلب البيانات السحابية أو قراءة الذكاء الاصطناعي للمحطة"""
    return random.choice([0, 0, 0, 1, 3, 4, 5])

def ai_fault_diagnosis(fault_code):
    """نظام خبير مبسط للذكاء الاصطناعي يقدم توصيات هندسية لكل عطل"""
    diagnoses = {
        0: "✅ **تحليل AI:** استقرار حراري وكهربائي ممتاز. كفاءة التوليد متوافقة مع منحنى الإشعاع الشمسي لبرنامج PVsyst.",
        1: "⚠️ **تحليل AI:** رصد تذبذب في شبكة المدينة. يوصى بمراجعة إعدادات المزامنة (Grid-Tie) وتوسيع نطاق الحماية (Voltage Protection limits).",
        2: "⚠️ **تحليل AI:** عدم استقرار في التردد. إذا كانت المحطة تعمل بالتوازي مع مولد ديزل، تأكد من إعدادات (Droop Control) وحاكم السرعة (Governor).",
        3: "🚨 **تحليل AI:** سلسلة الألواح (String) تتجاوز أقصى جهد MPPT. تأكد من مطابقة حسابات (Voc) مع درجات الحرارة الدنيا في منطقتك لتجنب تلف المحول.",
        4: "🚨 **تحليل AI:** إجهاد حراري يقلل من كفاءة المحول (Derating). راجع تهوية غرفة المحولات ونظف زعانف التبريد فوراً.",
        5: "⚠️ **تحليل AI:** تفريغ عميق للبطاريات (DOD تجاوز الحد الآمن). افصل الأحمال غير الحرجة وراجع حجم المصفوفة الشمسية لضمان شحن كافٍ.",
        6: "🚨 **تحليل AI:** تيار زائد مفاجئ. افحص كابلات التيار المتردد (AC) لاحتمالية حدوث قصر، أو راجع ذروة إقلاع المحركات (Inrush Current) في الأحمال."
    }
    return diagnoses.get(fault_code, "عطل غير مصنف. راجع دليل الصيانة.")

# --- الشريط الجانبي ---
st.sidebar.header("⚙️ إعدادات النظام")
mode = st.sidebar.selectbox("طريقة جلب البيانات", ["🌐 وضع السحابة / الذكاء الاصطناعي", "🔌 وضع الكابل المحلي (Modbus)"])

st.sidebar.markdown("---")
st.sidebar.info("💡 **مشروع الصيانة التنبؤية المدعوم بالذكاء الاصطناعي**\n\nتصميم وإدارة المهندس المختص.")

# --- الواجهة الرئيسية ---
st.title("⚡ لوحة الإدارة الذكية لمحطات الطاقة الشمسية")
st.markdown("---")

# تقسيم الواجهة إلى 3 أقسام (Tabs) لتسهيل التصفح من الموبايل
tab1, tab2, tab3 = st.tabs(["📡 المراقبة وتشخيص AI", "🧮 حاسبة PVsyst للتصميم", "📚 ملاحق ومعايير هندسية"])

# ==========================================
# التبويب الأول: المراقبة والذكاء الاصطناعي
# ==========================================
with tab1:
    st.subheader("مراقبة حالة المحول (Inverter Telemetry)")
    col1, col2 = st.columns(2)
    with col1:
        check_btn = st.button("🔄 تحليل حالة المحطة بالذكاء الاصطناعي", use_container_width=True)
    with col2:
        reset_btn = st.button("⚠️ إرسال أمر إعادة الضبط (Remote Reset)", type="primary", use_container_width=True)

    if check_btn:
        with st.spinner("يقوم الذكاء الاصطناعي بتحليل البيانات الحية..."):
            time.sleep(1) # محاكاة معالجة البيانات
            fault_code = fetch_from_supabase()
            
            description = FAULT_CODES.get(fault_code, "كود غير معروف")
            ai_recommendation = ai_fault_diagnosis(fault_code)
            
            # العرض
            st.metric(label="كود مسجل العطل (Modbus Register)", value=fault_code)
            
            if fault_code == 0:
                st.success(f"**الحالة:** {description}")
                st.info(ai_recommendation)
            elif fault_code in [4, 6, 3]:
                st.error(f"**تنبيه حرج:** {description}")
                st.error(ai_recommendation)
            else:
                st.warning(f"**تحذير:** {description}")
                st.warning(ai_recommendation)

# ==========================================
# التبويب الثاني: حاسبة التصميم (على معايير PVsyst)
# ==========================================
with tab2:
    st.subheader("حاسبة الأحمال وتصميم المحطة الكهروضوئية")
    
    c1, c2 = st.columns(2)
    with c1:
        daily_load = st.number_input("الاستهلاك اليومي (كيلو واط ساعة - kWh)", min_value=1.0, value=15.0)
        psh = st.number_input("ساعات الذروة الشمسية (PSH)", min_value=2.0, value=5.5)
        sys_voltage = st.selectbox("جهد النظام (System Voltage DC)", [12, 24, 48, 96, 384], index=2)
    with c2:
        panel_watt = st.number_input("قدرة اللوح الواحد (واط)", min_value=100, value=550)
        autonomy = st.number_input("أيام الاستقلالية للبطاريات (Days)", min_value=0.5, value=1.0)
        dod = st.slider("عمق التفريغ المسموح للبطاريات (DOD %)", min_value=20, max_value=90, value=50)

    if st.button("🧮 حساب المواصفات الهندسية"):
        # الحسابات الرياضية
        efficiency_loss = 1.3 # تعويض الفواقد (حرارة، غبار، كابلات) بمقدار 30%
        required_array_kw = (daily_load / psh) * efficiency_loss
        total_panels = math.ceil((required_array_kw * 1000) / panel_watt)
        
        # حساب البطاريات: (الاستهلاك * أيام الاستقلالية * 1000) / (جهد النظام * عمق التفريغ)
        req_battery_ah = (daily_load * 1000 * autonomy) / (sys_voltage * (dod / 100.0))
        
        st.markdown("### 📊 النتائج الموصى بها للتصميم:")
        res_c1, res_c2, res_c3 = st.columns(3)
        res_c1.metric("حجم المصفوفة الشمسية", f"{required_array_kw:.2f} kW")
        res_c2.metric("عدد الألواح المطلوبة", f"{total_panels} لوح")
        res_c3.metric("سعة بنك البطاريات", f"{req_battery_ah:.0f} Ah")
        
        st.info(f"💡 **توصية المحول:** يوصى باستخدام Inverter بقدرة لا تقل عن **{math.ceil(required_array_kw * 1.25)} kW** لاستيعاب تيارات البدء العالية.")

# ==========================================
# التبويب الثالث: الملاحق وجداول التصميم
# ==========================================
with tab3:
    st.subheader("📚 الملاحق والمعايير الهندسية")
    
    st.markdown("""
    **1. استخدام بيانات Google لتقدير الإشعاع:**
    * يُنصح باستخدام أدوات مثل **Google Project Sunroof** أو **Google Earth** لتحديد زوايا السمت (Azimuth) وتأثير الظلال على الموقع قبل إدخال البيانات إلى PVsyst.
    * المعادلة القياسية لحساب الطاقة المنتجة: 
    $$ E = A \times r \times H \times PR $$
    *(حيث A: المساحة، r: الكفاءة، H: الإشعاع، PR: معامل الأداء)*
    
    **2. معايير ضبط كابلات التيار المستمر (DC Sizing):**
    * يجب ألا يتجاوز الهبوط في الجهد (Voltage Drop) نسبة **2%** بين الألواح والمحول لضمان عمل نظام MPPT بأعلى كفاءة.
    
    **3. معاملات تصحيح الحرارة (Temperature Derating):**
    * وفقاً لبرنامج PVsyst، تنخفض كفاءة الألواح بحوالي $0.4\%$ لكل درجة مئوية ترتفع فوق $25^\circ C$. يجب أخذ ذلك في الاعتبار عند تصميم مشاريع في البيئات الحارة.
    
    **4. التوافق مع المولدات (Genset Integration):**
    * عند ربط المحول الشمسي مع المولدات الصناعية، تأكد من تركيب لوحة تحكم ذكية (مثل Deep Sea أو ComAp) لمنع رجوع القدرة العكسية (Reverse Power) إلى المولد.
    """)
