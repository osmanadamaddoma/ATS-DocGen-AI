import streamlit as st

st.set_page_config(page_title="AI Generator Maintenance", page_icon="⚙️")

st.title("⚙️ نظام الصيانة التنبؤية للمولدات الصناعية")
st.write("أدخل قراءات التشغيل الحالية لفحص احتمالية العطل:")

# إدخال البيانات من الفني
temperature = st.number_input("درجة حرارة المحرك (°C)", min_value=0, max_value=150, value=80)
vibration = st.number_input("معدل الاهتزاز (mm/s)", min_value=0.0, max_value=20.0, value=5.0)
voltage = st.number_input("الجهد الكهربائي (V)", min_value=0, max_value=500, value=400)
hours = st.number_input("ساعات التشغيل (Hours)", min_value=0, value=1500)

# زر الفحص
if st.button("إجراء الفحص التنبؤي"):
    if temperature > 100 or vibration > 10.0:
        st.error("⚠️ تحذير: خطر عطل ميكانيكي أو حراري وشيك. يرجى إيقاف المعدة للمراجعة.")
    else:
        st.success("✅ القراءات طبيعية. لا توجد أعطال متوقعة.")
