import streamlit as st
import datetime
import pandas as pd

# ==========================================
# 1. إعدادات الصفحة العامة والقائمة الجانبية
# ==========================================
st.set_page_config(
    page_title="منصة الدومة الهندسية المتكاملة",
    page_icon="⚙️",
    layout="wide"
)

st.sidebar.title("⚙️ منصة الخدمات الهندسية")
st.sidebar.markdown("---")

app_mode = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚡ الصيانة التنبؤية للمولدات",
        "🤖 المساعد الذكي والكتالوجات",
        "📋 إدارة الأصول وفحص المعدات"
    ]
)

# ==========================================
# القسم الأول: الصيانة التنبؤية للمولدات
# ==========================================
if app_mode == "⚡ الصيانة التنبؤية للمولدات":
    st.title("⚡ نظام الصيانة التنبؤية والتشغيل الذكي للمولدات")
    st.markdown("مراقبة وتحليل أداء مولدات الديزل (Perkins / Cummins) ووحدات التحكم (Deep Sea DSE).")
    st.markdown("---")

    st.sidebar.subheader("📋 إدخال بيانات المولد")
    gen_model = st.sidebar.selectbox("طراز المحرك", ["Perkins 2206C-E13TAG3", "Perkins 130 KVA", "Cummins GTA38", "Caterpillar C15"])
    controller_type = st.sidebar.selectbox("وحدة التحكم", ["Deep Sea DSE 8610 MKII", "Deep Sea DSE 7320 MKII", "ComAp InteliGen"])
    
    gen_kw = st.sidebar.number_input("سعة المولد الإسمية (kW)", min_value=10, max_value=2500, value=250)
    load_kw = st.sidebar.number_input("الحمل الحالي (kW)", min_value=0, max_value=2500, value=180)
    run_hours = st.sidebar.number_input("ساعات التشغيل الكلية (Hours)", min_value=0, value=3450)

    st.sidebar.subheader("القياسات والبيئة")
    coolant_temp = st.sidebar.slider("حرارة سائل التبريد (°C)", 40, 120, 85)
    oil_press = st.sidebar.slider("ضغط زيت المحرك (Bar)", 0.0, 10.0, 4.5, step=0.1)
    ambient_temp = st.sidebar.slider("درجة الحرارة المحيطة (°C)", 10, 55, 38)
    voltage = st.sidebar.number_input("الجهد الكهربائي (V)", value=400)
    freq = st.sidebar.number_input("التردد (Hz)", value=50.0, step=0.1)

    uploaded_gen_image = st.sidebar.file_uploader("رفع صورة المولد / لوحة التحكم", type=["jpg", "jpeg", "png"], key="gen_img")

    load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

    col_img, col_metrics = st.columns([1, 2]) if uploaded_gen_image else (None, st.container())

    if uploaded_gen_image:
        with col_img:
            st.image(uploaded_gen_image, caption=f"المولد: {gen_model}", width="stretch")

    st.subheader("📊 المؤشرات التشغيلية الحالية")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("إجمالي التشغيل", f"{run_hours} hrs")
    c2.metric("سعة المولد", f"{gen_kw} kW")
    c3.metric("الحمولة", f"{load_kw} kW", f"{load_percentage:.1f}%")
    c4.metric("الحرارة المحيطة", f"{ambient_temp} °C")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("حرارة المحرك", f"{coolant_temp} °C", delta="مرتفع" if coolant_temp >= 95 else "طبيعي", delta_color="inverse" if coolant_temp >= 95 else "normal")
    c6.metric("ضغط الزيت", f"{oil_press} Bar", delta="منخفض" if oil_press < 2.5 else "طبيعي", delta_color="inverse" if oil_press < 2.5 else "normal")
    c7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
    c8.metric("طراز الكنترولر", controller_type)

    st.markdown("---")
    st.subheader("🔍 تقييم الأعطال التنبؤي")
    alerts = []
    if coolant_temp >= 98:
        alerts.append("⚠️ **إنذار حرارة:** حرارة سائل التبريد مرتفعة! افحص الرديتر وسير المروحة.")
    if oil_press < 2.0:
        alerts.append("🚨 **خطر:** ضغط الزيت منخفض بشكل حرج! أوقف المحرك فوراً.")
    if load_percentage > 90:
        alerts.append("⚠️ **تحذير حمل:** المولد يعمل بأكثر من 90% من سعته.")

    if not alerts:
        st.success("✅ جميع المؤشرات في النطاق الآمن والمستقر.")
    else:
        for al in alerts:
            st.warning(al)

    st.subheader("📅 جدول الصيانة الدورية")
    maint_df = pd.DataFrame([
        {"المهمة": "تغيير الفلاتر والزيت", "الفترة": "كل 250 ساعة", "الحالة": "مجدولة قريباً"},
        {"المهمة": "فحص مزامنة الـ DSE 8610", "الفترة": "شهرياً", "الحالة": "مستقر"},
        {"المهمة": "اختبار الحساسات (ECM)", "الفترة": "كل 1000 ساعة", "الحالة": "تم الفحص"}
    ])
    st.dataframe(maint_df, width="stretch")


# ==========================================
# القسم الثاني: المساعد الذكي والكتالوجات
# ==========================================
elif app_mode == "🤖 المساعد الذكي والكتالوجات":
    st.title("🤖 المساعد الذكي للتشخيص والبحث في الكتالوجات")
    st.markdown("استفسر عن أي عطل فني، أو ارفع الكتالوجات والمخططات للتحليل الفوري.")
    st.markdown("---")

    uploaded_doc = st.file_uploader("رفع كتالوج أو مخطط فني (PDF, TXT, Image)", type=["pdf", "txt", "png", "jpg", "jpeg"])
    
    if uploaded_doc:
        st.success(f"تم رفع الملف بنجاح: {uploaded_doc.name}")
        if uploaded_doc.type.startswith("image"):
            st.image(uploaded_doc, caption="المخطط المرفوع", width="stretch")

    user_query = st.text_input("اكتب استفسارك الهندسي هنا (مثلاً: أسباب خطأ Failure to Start في محرك Perkins أو ضبط صمام التمدد لغرف تبريد Porkka WIC 10):")
    
    if st.button("بحث وتحليل ذكي"):
        if user_query:
            st.info(f"جاري تحليل الاستفسار والمصادر الفنية لـ: '{user_query}' ...")
            # نموذج إجابة هندسي استرشادي
            st.markdown("### 💡 نتائج التحليل الفني:")
            st.write("بناءً على المعايير الهندسية ومواصفات المحركات وأنظمة التبريد:")
            st.markdown("- **الخطوة الأولى:** التحقق من إشارات البدء وحساسات السرعة (Magnetic Pickup / Crankshaft Sensor).")
            st.markdown("- **الخطوة الثانية:** مراجعة إعدادات وحدة التحكم (DSE 7320 / 8610) وتأكيد عدم وجود قفل برمجي (Lockout Alarm).")
            st.markdown("- **الخطوة الثالثة:** فحص ضغط الوقود وفلاتر المياه/الوقود في دورة الحقن الإلكتروني (ECM).")
        else:
            st.warning("الرجاء إدخال نص الاستفسار أولاً.")


# ==========================================
# الثالث: إدارة الأصول وفحص المعدات
# ==========================================
else:
    st.title("📋 إدارة الأصول وتقييم المعدات الصناعية")
    st.markdown("إدارة وتتبع حالة المعدات، غرف التبريد (Porkka WIC 10 & WIC 40)، والمولدات، وتقييم الأضرار.")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📁 سجل الأصول والمعدات", "📊 مصفوفة تقييم الحالة والتقارير"])

    with tab1:
        st.subheader("قائمة الأصول المسجلة (Addoma Trading Services)")
        assets_data = pd.DataFrame([
            {"الكود": "GEN-01", "الأصل": "مولد Perkins 130KVA", "الموقع": "منطقة التعدين", "الحالة التشغيلية": "ممتازة", "آخر صيانة": "2026-01-15"},
            {"الكود": "COLD-01", "الأصل": "غرفة تبريد Porkka WIC 10", "الموقع": "المستودع الرئيسي", "الحالة التشغيلية": "تحتاج فحص الفلتر", "آخر صيانة": "2026-03-10"},
            {"الكود": "COLD-02", "الأصل": "غرفة تبريد Porkka WIC 40", "الموقع": "المستودع الرئيسي", "الحالة التشغيلية": "مستقرة", "آخر صيانة": "2026-04-02"},
            {"الكود": "PANEL-01", "الأصل": "لوحة مزامنة DSE 8610", "الموقع": "المحطة المركزية", "الحالة التشغيلية": "تعمل بكفاءة", "آخر صيانة": "2026-05-20"}
        ])
        st.dataframe(assets_data, width="stretch")

    with tab2:
        st.subheader("مصفوفة تقييم حالة المعدات وهياكل التصنيع")
        asset_to_evaluate = st.selectbox("اختر الأصل للتقييم:", ["مولد Perkins 2206C", "غرفة تبريد Porkka WIC 10", "غرفة تبريد Porkka WIC 40", "منشأة / مصنع تشكيل حديد"])
        
        damage_level = st.slider("نسبة التلف أو الاهتلاك الإنشائي / الميكانيكي (%)", 0, 100, 15)
        functional_status = st.selectbox("الحالة التشغيلية العامة", ["قابلة للتشغيل الفوري", "تحتاج صيانة جزئية وتغيير قطع غيار", "تحتاج عمرة شاملة", "خارج الخدمة / تالفة تماماً"])
        
        if st.button("إصدار تقييم الحالة الهندسية"):
            st.markdown(f"**تقرير التقييم للأصل: {asset_to_evaluate}**")
            st.write(f"- نسبة التلف المقدرة: {damage_level}%")
            st.write(f"- التوصية الهندسية: {functional_status}")
            if damage_level > 50:
                st.error("⚠️ الأصل يحتاج لتدخل هندسي عاجل وخطة إعادة تأهيل هيكلية.")
            else:
                st.success("✅ الأصل ضمن الحدود المقبولة للتشغيل مع ضرورة الالتزام بجدول الصيانة الوقائية.")
