import streamlit as st

st.set_page_config(
    page_title="Industrial Generator Predictive Maintenance Monitor",
    layout="wide"
)

# الشريط الجانبي لإدارة الباقات والتفعيل
st.sidebar.header("🔐 لوحة التحكم وإدارة الباقات")
activation_code = st.sidebar.text_input("أدخل كود الاشتراك (لفتح الميزات المتقدمة):", type="password")

# التحقق من حالة كود التفعيل
is_pro_unlocked = False
if activation_code == "ADDOMA2026" or activation_code == "PRO_ENG":
    is_pro_unlocked = True
    st.sidebar.success("✅ تم تفعيل الباقة الاحترافية للأسطول بنجاح")
elif activation_code != "":
    st.sidebar.error("❌ كود الاشتراك غير صحيح")
else:
    st.sidebar.info("💡 الوضع الحالي: مراقبة الوحدة الأساسية (Single-Unit Mode).")

# العنوان الرئيسي للمنصة الصناعية
st.title("⚙️ نظام مراقبة الصيانة التنبؤية للمولدات الصناعية")
st.markdown("مراقبة حية لمؤشرات الأداء، درجات الحرارة، ضغوط الزيت، والتنبؤ بالأعطال لمولدات (Perkins & Cummins).")

st.divider()

# قسم مؤشرات التشغيل الحية (المتاح للجميع)
st.subheader("📊 المؤشرات الحية للوحدة النشطة")
col1, col2, col3, col4 = st.columns(4)
col1.metric("حالة المولد", "متصل وجاهز", "Online")
col2.metric("ساعات التشغيل", "1,850 ساعة", "+8h اليوم")
col3.metric("حرارة سائل التبريد", "83 °C", "طبيعي")
col4.metric("ضغط الزيت (Oil Pressure)", "4.2 بار", "مستقر")

st.divider()

# قسم الميزات المتقدمة والتنبؤ بالأعطال (يفتح باستخدام كود الباقة)
if is_pro_unlocked:
    st.subheader("🔮 تحليلات التنبؤ بالأعطال وذكاء الأسطول (Advanced Predictive Diagnostics)")
    st.success("🌟 صلاحيات الأسطول الكامل وميزات التنبؤ الذكي مفعلة.")
    
    # عرض بيانات تنبؤية متقدمة
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**حالة نظام الحقن وقود (Fuel System):**")
        st.progress(92, text="كفاءة المضخة: 92% (مستقرة)")
    with col_b:
        st.markdown("**توقع الصيانة القادمة:**")
        st.info("🔧 موعد تغيير الفلاتر القادم خلال: 150 ساعة تشغيل.")
        
    st.code("MODBUS / DSE 8610 MKII: Sync & Load Sharing Status -> Optimal", language="text")

else:
    st.warning("🔒 ميزات التنبؤ المتقدم وتحليل الأكواد الاحترافي مقفلة. يرجى إدخال كود التفعيل الخاص بباقات المؤسسات في الشريط الجانبي لفتحها.")
