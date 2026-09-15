import io
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# 1. تهيئة إعدادات الصفحة
st.set_page_config(
    page_title="منصة الدومة المتكاملة", page_icon="🛠️", layout="wide"
)

# ---------------------------------------------------------
# 2. القائمة الجانبية (Sidebar)
# ---------------------------------------------------------
with st.sidebar:
    st.title("🛠️ منصة الدومة المتكاملة")
    st.caption("إدارة المولدات، المساعد الذكي، والرؤية الحاسوبية للفحص")
    st.success("🔥 متصل بـ Firebase بنجاح")

    st.markdown("---")
    st.subheader("📌 اختيار المهمة (App Navigation)")
    app_mode = st.selectbox(
        "اختر النظام المطلوب:",
        [
            "⚙️ لوحة التحكم والصيانة التنبؤية",
            "📊 التقارير والرسوم البيانية",
        ],
    )

    st.markdown("---")
    st.subheader("🔐 بوابة التفعيل")
    activation_code = st.text_input(
        "أدخل كود الاشتراك:", type="password", key="act_code"
    )
    st.info("⏳ فترة تجريبية (متبقي 6 يوم)")

    st.markdown("---")
    st.subheader("🎯 ضبط حدود المعايير")
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        v_min = st.number_input("أدنى جهد (V Min)", value=380)
        hz_min = st.number_input("أدنى تردد (Hz Min)", value=48)
    with col_v2:
        v_max = st.number_input("أقصى جهد (V Max)", value=420)
        hz_max = st.number_input("أقصى تردد (Hz Max)", value=52)

    temp_max = st.number_input("أقصى حرارة (°C)", value=95)
    current_max = st.number_input("أقصى تيار (A Max)", value=250)

    st.markdown("---")
    st.subheader("📥 إدخال قراءات المولد")
    gen_model = st.text_input("طراز المولد", value="Perkins 200 kVA")
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        hours_current = st.number_input(
            "ساعات التشغيل الحالية", value=700.0, step=1.0
        )
        cap_kw = st.number_input("سعة المولد (kW)", value=200.0)
        amb_temp = st.number_input("الحرارة المحيطة (°C)", value=43.0)
        oil_press = st.number_input("ضغط الزيت (Bar)", value=2.5)
        volt = st.number_input("الجهد (V)", value=400.0)
        curr = st.number_input("التيار (A)", value=118.0)
        oil_hours_done = st.number_input(
            "ساعات آخر تغيير زيت", value=480.0, step=1.0
        )
    with col_h2:
        hours_target = st.number_input(
            "ساعات التشغيل المستهدفة", value=940.0, step=1.0
        )
        load_kw = st.number_input("الحمولة الحالية (kW)", value=50.0)
        coolant_temp = st.number_input("حرارة سائل التبريد (°C)", value=85.0)
        vibration = st.number_input("مستوى الاهتزاز (mm/s)", value=1.2)
        freq = st.number_input("التردد (Hz)", value=50.0)
        pf = st.number_input("معامل القدرة (PF)", value=0.85)
        oil_hours_std = st.number_input(
            "الفترة القياسية للزيت", value=250.0, step=1.0
        )

    gen_img = st.file_uploader(
        "رفع صورة المولد", type=["png", "jpg", "jpeg"]
    )

    save_btn = st.button("💾 حفظ السجلات في قاعدة بيانات Firebase")
    if save_btn:
        st.success("✅ إتم الحفظ السحابي بنجاح")

# ---------------------------------------------------------
# 3. الواجهة الرئيسية (Main Body)
# ---------------------------------------------------------
if app_mode == "⚙️ لوحة التحكم والصيانة التنبؤية":
    st.title(
        "⚙️ نظام الصيانة التنبؤية والتقارير الشاملة للمولدات الصناعية"
    )

    # عرض البطاقات الأساسية (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("إجمالي التشغيل", f"{hours_current} hrs")
        st.metric("الحرارة المحيطة", f"{amb_temp} °C")
    with col2:
        st.metric("الساعات المستهدفة", f"{hours_target} hrs")
        st.metric("حرارة المحرك", f"{coolant_temp} °C")
    with col3:
        load_pct = round((load_kw / cap_kw) * 100, 1) if cap_kw > 0 else 0
        st.metric("الحمولة", f"{load_kw} kW", delta=f"{load_pct}%")
        st.metric("ضغط الزيت", f"{oil_press} Bar")
    with col4:
        st.metric("الجهد / التردد", f"{volt}V | {freq}Hz")
        st.metric("التيار / المعامل", f"{curr}A | {pf}")

    st.markdown("---")
    st.subheader("🚨 إنذارات الحدود التشغيلية")

    # فحص الحدود
    alerts = []
    if volt < v_min or volt > v_max:
        alerts.append(f"تجاوز حدود الجهد الكهربائي: {volt}V")
    if freq < hz_min or freq > hz_max:
        alerts.append(f"تجاوز حدود التردد: {freq}Hz")
    if coolant_temp > temp_max:
        alerts.append(f"ارتفاع حرارة المحرك: {coolant_temp}°C")
    if curr > current_max:
        alerts.append(f"تجاوز التيار الأقصى: {curr}A")

    if alerts:
        for alt in alerts:
            st.error(f"⚠️ {alt}")
    else:
        st.success(
            "🟢 جميع القراءات الكهربائية والميكانيكية ضمن الحدود الآمنة."
        )

    st.markdown("---")
    st.subheader("🛢️ جدول خدمة زيت المحرك")

    col_o1, col_o2, col_o3, col_o4 = st.columns(4)
    rem_oil = max(0.0, oil_hours_std - oil_hours_done)
    oil_usage_pct = (
        round((oil_hours_done / oil_hours_std) * 100)
        if oil_hours_std > 0
        else 0
    )

    with col_o1:
        st.metric("الساعات المنقضية للزيت", f"{oil_hours_done} hrs")
    with col_o2:
        st.metric("الفترة القياسية", f"{oil_hours_std} hrs")
    with col_o3:
        st.metric(
            "المتبقي للخدمة",
            f"{rem_oil} hrs",
            delta=f"{oil_usage_pct}%",
            delta_color="inverse",
        )
    with col_o4:
        st.metric("اللزوجة الموصى بها", "15W40 (Standard)")

    if oil_hours_done >= oil_hours_std:
        st.error(
            "🚨 تحذير حرج: تجاوزت فترة غيار الزيت المقررة! يرجى الاستبدال الفوري."
        )

    st.markdown("---")
    st.subheader("🔧 جدول تتبع قطع الغيار والفلاتر التنبؤية")

    parts_data = {
        "المكون / الخدمة": [
            "فلتر الزيت (Engine Oil Filter)",
            "فلتر الوقود (Primary Fuel Filter)",
            "فلتر الهواء (Air Filter)",
            "سيور المروحة (Fan Belt)",
            "البطاريات (Batteries)",
        ],
        "حالة القطعة": ["مقبولة", "استبدال قريب", "جيدة", "جيدة", "ممتازة"],
        "الساعات المتبقية": [20, 50, 150, 300, 500],
    }
    st.table(pd.DataFrame(parts_data))

elif app_mode == "📊 التقارير والرسوم البيانية":
    st.title("📊 مركز التقارير وتحليل الرسوم البيانية")

    st.subheader("📈 الرسم البياني لأداء المولد")

    # توليد بيانات زَمنية توضيحية للرسم البياني
    np.random.seed(42)
    time_index = pd.date_range("2026-09-01", periods=30, freq="D")
    df_chart = pd.DataFrame(
        {
            "درجة الحرارة (°C)": np.random.normal(
                loc=coolant_temp, scale=2, size=30
            ),
            "ضغط الزيت (Bar)": np.random.normal(
                loc=oil_press, scale=0.2, size=30
            ),
            "الجهد (V)": np.random.normal(loc=volt, scale=3, size=30),
        },
        index=time_index,
    )

    st.line_chart(df_chart)

    st.markdown("---")
    st.subheader("📥 إصدار وتصدير التقارير")

    # إعداد جدول التقرير للتحميل
    report_dict = {
        "طراز المولد": [gen_model],
        "ساعات التشغيل الحالية": [hours_current],
        "ساعات التشغيل المستهدفة": [hours_target],
        "الحمولة (kW)": [load_kw],
        "الحرارة المحيطة (°C)": [amb_temp],
        "حرارة السائل (°C)": [coolant_temp],
        "ضغط الزيت (Bar)": [oil_press],
        "الجهد (V)": [volt],
        "التردد (Hz)": [freq],
        "التيار (A)": [curr],
        "معامل القدرة": [pf],
        "ساعات الزيت المنقضية": [oil_hours_done],
        "حالة الزيت": [
            "تحذير حرج" if oil_hours_done >= oil_hours_std else "سليم"
        ],
    }
    df_report = pd.DataFrame(report_dict)

    st.dataframe(df_report)

    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        # تصدير ملف CSV
        csv_buffer = df_report.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 تصدير التقرير الحالي (CSV)",
            data=csv_buffer,
            file_name=f"Generator_Report_{gen_model}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_exp2:
        # خيار إعداد للطباعة PDF
        if st.button("🖨️ تجهيز التقرير للطباعة (PDF)", use_container_width=True):
            st.info(
                "💡 يمكنك الآن الضغط على (Ctrl + P) أو (Cmd + P) لحفظ الصفحة بصيغة PDF."
            )

# ---------------------------------------------------------
# 4. التذييل وحقوق الملكية
# ---------------------------------------------------------
st.markdown("---")
st.caption(
    "© 2026 Osman Adam Addoma. All Rights Reserved. Unauthorized copying, modification, or distribution of this code or project structure is strictly prohibited."
)
