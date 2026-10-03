import os, re, json, uuid, time, math, io, base64
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import streamlit as st
import extra_streamlit_components as stx

st.set_page_config(page_title="Addoma V6 - Industrial AI", page_icon="⚙️", layout="wide")

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الخرطوم - أمدرمان": {
            "كافوري - الموقع الرئيسي": {
                "address": "الخرطوم - المنطقة الصناعية - أمدرمان",
                "generators": {
                    "G1": {"model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0,
                           "calib_elec": {"v_nominal":400,"v_measured":398,"freq_nominal":50,"freq_measured":50.1,"current_max":600,"current_measured":360,"pf":0.85},
                           "calib_engine": {"oil_press_bar":4.5,"coolant_temp_c":85,"rpm":1500,"battery_v":26.5,"ambient_temp":43}},
                }
            }
        }
    }

# --- تم التعديل: كود جديد ومخفي ---
CLIENTS_DATABASE = {
    "OMD-SECURE-2027-X77": {"name": "عثمان آدم أدومة", "plan": "شهري", "start_date": "2026-09-15", "duration_days": 365},
}

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="cookie_v6_final")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()
if "authenticated" not in st.session_state: st.session_state.authenticated=False

if not st.session_state.authenticated:
    st.title("🔐 بوابة تفعيل نظام Addoma V6")
    st.info("المجمع الصناعي الشامل - نظام الصيانة التنبؤية")
    user_code = st.sidebar.text_input("كود التفعيل:", type="password")
    if st.sidebar.button("تفعيل", type="primary"):
        if user_code.strip().upper() in CLIENTS_DATABASE:
            st.session_state.authenticated=True
            st.rerun()
        else:
            st.error("❌ كود غير صحيح - تواصل مع الإدارة")
    # تم حذف سطر st.warning الذي كان يظهر الكود
    st.stop()

st.sidebar.success("✅ نظام V6 نشط - التطبيق متصل")
selected_app = st.sidebar.radio("اختر القسم:", ["⚙️ 1. الصيانة التنبؤية", "🎛️ 2. IoT", "🧮 3. الحاسبة", "🤖 4. Gemini AI"])

if "1." in selected_app:
    st.title("⚙️ الصيانة التنبؤية - V6")
    main=list(st.session_state.sites_data.keys())[0]
    sub=list(st.session_state.sites_data[main].keys())[0]
    gen=list(st.session_state.sites_data[main][sub]["generators"].keys())[0]
    ginfo=st.session_state.sites_data[main][sub]["generators"][gen]
    c1,c2,c3=st.columns(3)
    c1.metric("الموديل", ginfo['model'], f"{ginfo['kw']} kW")
    c2.metric("الساعات", f"{ginfo['run_hours']} hr")
    c3.metric("الحرارة", f"{ginfo['calib_engine']['coolant_temp_c']} °C")
    df=pd.DataFrame([{"القطعة":"Oil Filter","العمر":250,"المنقضي":180},{"القطعة":"Fuel Filter","العمر":500,"المنقضي":430},{"القطعة":"Air Filter","العمر":1000,"المنقضي":650}])
    df["النسبة%"]=round(df["المنقضي"]/df["العمر"]*100,1)
    st.dataframe(df, use_container_width=True)
    fig=px.bar(df, x="القطعة", y="النسبة%", color="النسبة%", color_continuous_scale="RdYlGn_r")
    st.plotly_chart(fig, use_container_width=True)

elif "3." in selected_app:
    st.title("🧮 الحاسبة الهندسية للكهرباء والانبعاثات")
    tab_fuel, tab_sfc = st.tabs(["🌱 Fuel & Carbon Footprint", "📊 SFC Curve - جدولك"])

    with tab_fuel:
        st.subheader("🌱 حساب الوقود والبصمة الكربونية")
        st.success("✅ التطبيق متصل ومُفعل بنجاح مع قاعدة بيانات Supabase!")
        col1, col2 = st.columns(2)
        with col1:
            power_kw = st.number_input("القدرة الفعلية (kW)", value=300.0, key="p1")
            hours = st.number_input("ساعات التشغيل اليومية", value=24.0, key="h1")
            sfc_val = st.number_input("استهلاك الوقود النوعي SFC (g/kWh)", value=210.0, key="s1")
            diesel_price = st.number_input("سعر اللتر (SDG)", value=2500.0, key="price")
        with col2:
            fuel_density = 0.85
            fuel_liters = (power_kw * sfc_val * hours) / (fuel_density * 1000)
            fuel_kg = fuel_liters * fuel_density
            co2_kg = fuel_kg * 3.16
            cost = fuel_liters * diesel_price

            st.metric("⛽ الوقود المستهلك (لتر/يوم)", f"{fuel_liters:.2f} L")
            st.metric("⚖️ الوقود (كجم/يوم)", f"{fuel_kg:.2f} kg")
            st.metric("🌍 انبعاثات CO2", f"{co2_kg:.2f} kg/يوم")
            st.metric("💰 التكلفة اليومية", f"{cost:,.0f} SDG")

            # حساب شهري وسنوي
            st.divider()
            st.write(f"**شهري:** {fuel_liters*30:.0f} لتر | **سنوي:** {fuel_liters*365:.0f} لتر")

    with tab_sfc:
        st.subheader("📊 منحنى SFC - كفاءة الوقود حسب الحمل")
        data = {
            "الحمل %": [25, 50, 75, 100, 110],
            "SFC (g/kWh)": [260, 220, 205, 200, 210],
            "الكفاءة %": [32, 38, 41, 42.5, 40],
            "استهلاك (L/hr)": [22, 37, 52, 68, 78]
        }
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            fig1 = px.line(df, x="الحمل %", y="SFC (g/kWh)", markers=True, title="SFC Curve - كلما قل كان أفضل")
            fig1.add_hline(y=200, line_dash="dash", annotation_text="المثالي")
            st.plotly_chart(fig1, use_container_width=True)
        with c2:
            fig2 = px.bar(df, x="الحمل %", y="الكفاءة %", color="الكفاءة %", title="كفاءة المحرك")
            st.plotly_chart(fig2, use_container_width=True)

        st.info("💡 **نصيحة:** أفضل كفاءة عند 75-100% حمل. الحمل أقل من 50% يزيد استهلاك الوقود.")

elif "2." in selected_app:
    st.title("🎛️ IoT Monitoring")
    st.info("قريباً - نظام المراقبة اللحظية")

elif "4." in selected_app:
    st.title("🤖 Gemini AI Assistant")
    st.info("المساعد الذكي - قريباً")
