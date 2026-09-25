import streamlit as st
import pandas as pd
import numpy as np

# التحقق من تسجيل الدخول من الصفحة الرئيسية
if not st.session_state.get("authenticated", False):
    st.warning("⚠️ يرجى تسجيل الدخول أولاً من الصفحة الرئيسية.")
    st.stop()

st.set_page_config(page_title="توفير الوقود الهجين", page_icon="⚡", layout="wide")

st.title("⚡ محاكي نظام التوليد الهجين وتقليل التكاليف")
st.caption("أداة تقييم الوفر المالي للأنظمة المدمجة (Solar + Diesel Hybrid Microgrid) - Addoma Trading Services")

# --- 1. المدخلات ---
with st.sidebar:
    st.header("⚙️ إعدادات المحطة والأحمال")
    gen_capacity = st.number_input("سعة المولد (kW):", min_value=100, max_value=5000, value=1000, step=50)
    solar_peak = st.number_input("سعة الطاقة الشمسية (kWp):", min_value=0, max_value=5000, value=700, step=50)
    fuel_price = st.number_input("سعر لتر الوقود ($):", min_value=0.1, value=1.0, step=0.1)

# --- 2. دالة حساب استهلاك الوقود الديناميكي ---
def calculate_dynamic_fuel(load_kw, capacity_kw):
    if load_kw <= 0:
        return 0.0
    load_perc = (load_kw / capacity_kw) * 100
    if load_perc < 25:
        sfc = 0.35
    elif load_perc < 50:
        sfc = 0.30
    elif load_perc < 75:
        sfc = 0.27
    else:
        sfc = 0.25
    return load_kw * sfc

# --- 3. بيانات المحاكاة (24 ساعة) ---
hours = np.arange(24)
factory_load = np.array([250, 250, 260, 250, 300, 450, 600, 800, 850, 900, 920, 900, 
                         850, 800, 750, 700, 650, 550, 500, 450, 350, 300, 250, 250])

solar_profile = np.array([0, 0, 0, 0, 0, 0, 0.15, 0.35, 0.60, 0.80, 0.95, 1.0, 
                          1.0, 0.95, 0.75, 0.50, 0.20, 0, 0, 0, 0, 0, 0, 0])

solar_production = solar_profile * solar_peak

results = []
for h in hours:
    load = factory_load[h]
    solar = solar_production[h]
    net_load = max(0, load - solar)
    
    fuel_trad = calculate_dynamic_fuel(load, gen_capacity)
    fuel_hyb = calculate_dynamic_fuel(net_load, gen_capacity)
    
    results.append({
        "الساعة": f"{h:02d}:00",
        "حمل المصنع (kW)": load,
        "توليد الشمس (kW)": min(load, solar),
        "حمل المولد (kW)": net_load,
        "الوقود التقليدي (لتر)": fuel_trad,
        "الوقود الهجين (لتر)": fuel_hyb
    })

df = pd.DataFrame(results)

total_trad = df["الوقود التقليدي (لتر)"].sum()
total_hyb = df["الوقود الهجين (لتر)"].sum()
saved_fuel = total_trad - total_hyb
saved_money = saved_fuel * fuel_price
reduction_perc = (saved_fuel / total_trad) * 100

# --- 4. العرض الفني والمالي ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("الوفر اليومي بالوقود", f"{saved_fuel:,.1f} لتر", f"{reduction_perc:.1f}%-")
col2.metric("الوفر المالي اليومي", f"{saved_money:,.2f}$")
col3.metric("الوفر المالي الشهري", f"{saved_money * 30:,.2f}$")
col4.metric("استهلاك النظام الهجين", f"{total_hyb:,.1f} لتر")

st.divider()
st.subheader("📊 توزيع أحمال التوليد خلال 24 ساعة")
st.area_chart(df.set_index("الساعة")[["توليد الشمس (kW)", "حمل المولد (kW)"]])

with st.expander("📋 عرض جدول البيانات الفني التفصيلي"):
    st.dataframe(df, use_container_width=True)
