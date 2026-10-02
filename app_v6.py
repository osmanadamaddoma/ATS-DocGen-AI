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

CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة", "plan": "شهري", "start_date": "2026-09-15", "duration_days": 365},
}

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="cookie_v6_final")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()
if "authenticated" not in st.session_state: st.session_state.authenticated=False

if not st.session_state.authenticated:
    st.title("🔐 بوابة تفعيل نظام Addoma V6")
    user_code = st.sidebar.text_input("كود التفعيل:", type="password")
    if st.sidebar.button("تفعيل", type="primary"):
        if user_code.strip().upper() in CLIENTS_DATABASE:
            st.session_state.authenticated=True
            st.rerun()
        else: st.error("❌ كود غير صحيح")
    st.warning("أدخل: ADDOMA-2026-PRO")
    st.stop()

st.sidebar.success("✅ نظام V6 نشط")
selected_app = st.sidebar.radio("اختر:", ["⚙️ 1. الصيانة التنبؤية", "🎛️ 2. IoT", "🧮 3. الحاسبة", "🤖 4. Gemini"])

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
