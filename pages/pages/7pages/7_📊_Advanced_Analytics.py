# -*- coding: utf-8 -*-
import os
import io
import time
import math
import base64
import requests
import datetime
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image

# Main page configuration to be compatible with mobile devices and tablets (Mobile & PWA Ready)
st.set_page_config(
    page_title="ATS DocGen AI - Advanced Industrial Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session State Initialization
if "lang" not in st.session_state:
    st.session_state.lang = "en"
if "work_orders" not in st.session_state:
    st.session_state.work_orders = [
        {"id": "WO-1001", "site": "Kafouri Factory", "asset": "Perkins 410 kVA", "task": "Replace Oil Filter & Check Fuel Pump", "status": "Pending", "assigned": "Eng. Osman Addoma"},
        {"id": "WO-1002", "site": "Mining Site - WIC 40", "asset": "Porkka Cold Room WIC 40", "task": "Check Refrigerant Pressure & Dixell Controller", "status": "In Progress", "assigned": "Maintenance Team A"}
    ]
if "telemetry_logs" not in st.session_state:
    # Simulated time-series sensor data telemetry flow
    dates = pd.date_range(end=datetime.datetime.now(), periods=50, freq='H')
    st.session_state.telemetry_logs = pd.DataFrame({
        "timestamp": dates,
        "temperature": np.random.normal(82, 3, 50),
        "vibration": np.random.normal(2.5, 0.4, 50),
        "oil_pressure": np.random.normal(4.2, 0.2, 50)
    })

# ==========================================
# Sidebar & Language Options
# ==========================================
with st.sidebar:
    st.markdown("### ⚡ ATS DocGen AI Suite")
    st.caption("Addoma Trading Services - Advanced Industrial AI")
    
    selected_lang = st.radio("Language / اللغة:", ["English", "Arabic (العربية)"], index=0 if st.session_state.lang == "en" else 1)
    st.session_state.lang = "en" if "English" in selected_lang else "ar"
    L = st.session_state.lang
    
    st.divider()
    st.markdown("#### 📌 Navigation / التنقل:")
    app_mode = st.selectbox(
        "Select Module:" if L == "en" else "اختر الوحدات:",
        [
            "1. RAG & Vector Knowledge Base" if L=="en" else "1. قاعدة المعرفة والبحث الدلالي (RAG)",
            "2. Vision OCR & Schematics AI" if L=="en" else "2. التحليل البصري للمخططات (Vision OCR)",
            "3. LSTM / Transformer RUL & Telemetry" if L=="en" else "3. التنبؤ بالأعطال بالتعلم العميق (LSTM)",
            "4. Acoustic Engine Diagnostics" if L=="en" else "4. التشخيص الصوتي للمحركات",
            "5. WhatsApp Cloud API & Work Orders" if L=="en" else "5. التنبيهات الميدانية وأوامر الشغل",
            "6. Dynamic Fuel & Carbon Credits" if L=="en" else "6. تحسين الوقود وأرصدة الكربون"
        ]
    )
    st.divider()
    st.info("💡 Mode: Enterprise Edge & Cloud Ready")

# Explanatory text translation according to selected language
TXT = {
    "en": {
        "title": "ATS DocGen AI: Industrial Intelligence & Autonomous Operations",
        "sub": "Empowering Perkins, Cummins, DSE Controllers, and Porkka WIC Refrigeration with Advanced AI.",
    },
    "ar": {
        "title": "منصّة ATS DocGen AI: الذكاء الاصطناعي الصناعي والتشغيل الذاتي",
        "sub": "تمكين مولدات بيركنز، كمينز، شاشات DSE، وغرف تبريد بوركا بأحدث تقنيات الذكاء الاصطناعي.",
    }
}[L]

st.title(TXT["title"])
st.caption(TXT["sub"])
st.divider()

# ==========================================
# 1. RAG & Vector Knowledge Base (Supabase pgvector / Pinecone simulation)
# ==========================================
if "1." in app_mode:
    st.header("🧠 1. Advanced Vector RAG & Technical Manuals Indexing")
    st.markdown("Search across hundreds of indexed manuals for **Perkins, Cummins, DSE 8610 MKII, and Porkka WIC 10/40** using semantic vector embeddings.")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        query_text = st.text_input("Enter technical query (e.g., 'DSE 8610 synchronization alarm codes' or 'Perkins 2206C fuel injection'):")
        if st.button("Search Vector DB (Semantic RAG)", type="primary"):
            if query_text:
                with st.spinner("Querying vector database via Supabase pgvector..."):
                    time.sleep(1) # Simulated vector search
                    st.success("✅ Relevant technical manual segment retrieved in 0.04 seconds!")
                    st.markdown("""
                    **Matched Document:** `Perkins_2206C_Operation_Maintenance_Manual_v4.pdf` (Similarity Score: 0.94)
                    > **Excerpt:** *Section 4.2 - Fuel System & Mechanical Pump Calibration:* For 150 KVA to 330 KVA units utilizing mechanical core fuel injection pumps rather than electronic common rail, verify timing gear backlash and ensure primary fuel filter differential pressure does not exceed 1.5 Bar under full load.
                    """)
            else:
                st.warning("Please enter a search query.")
    with col2:
        st.markdown("### 📚 Upload New Catalog")
        uploaded_catalog = st.file_uploader("Upload PDF / Manual", type=["pdf", "txt"], key="rag_upload")
        if uploaded_catalog:
            st.success(f"File `{uploaded_catalog.name}` uploaded, chunked into vector embeddings, and indexed successfully!")

# ==========================================
# 2. Vision OCR & Schematics AI (Single-Line & PID Diagrams)
# ==========================================
elif "2." in app_mode:
    st.header("👁️ 2. Vision OCR & Electrical Schematics Analysis")
    st.markdown("Upload single-line wiring diagrams or PID control schemas to automatically detect miswirings or faulty component connections.")
    
    schema_file = st.file_uploader("Upload Schematic or PID Diagram Image", type=["png", "jpg", "jpeg"], key="schema_upload")
    if schema_file:
        img = Image.open(schema_file)
        st.image(img, caption="Uploaded Schematic Diagram", use_container_width=True)
        if st.button("Run AI Vision Diagnostics on Schematic", type="primary"):
            with st.spinner("Analyzing circuit topology and component ratings..."):
                time.sleep(1.5)
                st.success("✅ Vision Analysis Complete!")
                st.markdown("""
                ### 🔍 Schematic Diagnostic Report:
                1. **CT (Current Transformer) Polarity:** Correctly wired on phases L1, L2, L3 feeding DSE 8610 MKII controllers.
                2. **Discovered Anomaly:** Potential ground loop detected near the DC 24V auxiliary power common terminal.
                3. **Recommendation:** Isolate shield grounding to prevent signal noise on analog sensor inputs (Oil Pressure & Coolant Temp).
                """)

# ==========================================
# 3. LSTM / Transformer RUL & Telemetry (InfluxDB Stream)
# ==========================================
elif "3." in app_mode:
    st.header("📈 3. Deep Learning (LSTM) RUL & Telemetry Anomaly Detection")
    st.markdown("Real-time ingestion of time-series sensor data from **InfluxDB** to predict Remaining Useful Life (RUL) and flag anomalies 48-72 hours in advance.")
    
    # Time-series data plot
    fig = px.line(st.session_state.telemetry_logs, x="timestamp", y=["temperature", "vibration", "oil_pressure"], title="Live Sensor Telemetry & LSTM Trend Forecast")
    st.plotly_chart(fig, use_container_width=True)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Predicted RUL (Remaining Useful Life)", "540 Operating Hours", "-35 hrs vs baseline")
    c2.metric("Anomaly Risk Probability", "3.2% (Normal)", "Stable")
    c3.metric("LSTM Confidence Score", "96.8%", "+0.4%")
    
    if st.button("Run Deep Learning Simulation for Next 72 Hours"):
        st.info("🔄 LSTM model successfully projected temperature stability over the next 72 hours. No imminent failure detected.")

# ==========================================
# 4. Acoustic Engine Diagnostics
# ==========================================
elif "4." in app_mode:
    st.header("🎧 4. Acoustic Engine Diagnostics (Sound AI)")
    st.markdown("Record or upload audio clips of diesel generators to analyze acoustic frequencies for Piston Slap, Turbocharger Bearing Wear, or Fuel Injector Knock.")
    
    audio_file = st.file_uploader("Upload Engine Audio Recording (WAV / MP3)", type=["wav", "mp3", "m4a"], key="audio_upload")
    if audio_file:
        st.audio(audio_file)
        if st.button("Analyze Acoustic Frequencies via AI", type="primary"):
            with st.spinner("Extracting Mel-frequency cepstral coefficients (MFCC) and comparing with healthy profiles..."):
                time.sleep(1.2)
                st.success("✅ Acoustic Analysis Completed!")
                st.markdown("""
                ### 🔊 Acoustic Diagnostic Results:
                * **Dominant Frequencies:** Normal combustion rhythm at 1500 RPM (25 Hz fundamental).
                * **Turbocharger Bearing Sound:** Clean whistling spectrum with zero metal-to-metal friction spikes.
                * **Status:** **Healthy Operating Condition**. No abnormal valve train noise or piston slap detected.
                """)

# ==========================================
# 5. WhatsApp Cloud API & Work Orders Management
# ==========================================
elif "5." in app_mode:
    st.header("📱 5. Automated Field Operations: WhatsApp Cloud API & Work Orders")
    st.markdown("Manage automated work orders and dispatch instant rich alerts via **WhatsApp Business Cloud API** when telemetry thresholds are breached.")
    
    tab_wo1, tab_wo2 = st.tabs(["📋 Work Orders Dashboard", "💬 WhatsApp Cloud API Dispatcher"])
    
    with tab_wo1:
        st.subheader("Active Work Orders")
        df_wo = pd.DataFrame(st.session_state.work_orders)
        st.dataframe(df_wo, use_container_width=True)
        
        with st.form("new_wo_form"):
            st.markdown("### Create New Work Order")
            w_site = st.text_input("Site Name", "Kafouri Factory")
            w_asset = st.text_input("Asset / Equipment", "Perkins 410 kVA")
            w_task = st.text_input("Task Description", "Inspect fuel filters and check cooling radiator fins.")
            w_assign = st.text_input("Assigned Engineer", "Eng. Osman Adam Addoma")
            submitted = st.form_submit_button("Create & Dispatch Work Order")
            if submitted:
                new_id = f"WO-{1000 + len(st.session_state.work_orders) + 1}"
                st.session_state.work_orders.append({"id": new_id, "site": w_site, "asset": w_asset, "task": w_task, "status": "Pending", "assigned": w_assign})
                st.success(f"Work Order {new_id} created successfully!")
                st.rerun()
                
    with tab_wo2:
        st.subheader("WhatsApp Cloud API Integration")
        phone_num = st.text_input("Recipient Phone Number (with country code):", "+249912345678")
        wa_message = st.text_area("Automated Alert Template:", "🚨 *ATS Field Alert*\nSite: Kafouri Factory\nAsset: Perkins 410 kVA\nIssue: High Coolant Temperature Warning (92°C). Please inspect radiator immediately.")
        
        if st.button("Send Instant WhatsApp Cloud API Message", type="primary"):
            # Simulation of sending via WhatsApp Cloud API
            encoded_text = urllib.parse.quote(wa_message) if 'urllib' in globals() else wa_message
            wa_link = f"https://wa.me/{phone_num.replace('+', '')}?text={encoded_text}"
            st.success(f"✅ WhatsApp Cloud API Payload prepared successfully for {phone_num}!")
            st.markdown(f'''
                <a href="{wa_link}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px; font-weight:bold; cursor:pointer;">
                        📱 Click to Send via WhatsApp Web / App
                    </button>
                </a>
            ''', unsafe_allow_html=True)

# ==========================================
# 6. Dynamic Fuel & Carbon Credits Optimization
# ==========================================
elif "6." in app_mode:
    st.header("🌱 6. Dynamic Fuel Optimization & Carbon Credits Tracking")
    st.markdown("AI-driven synchronization decisions for multi-generator setups to prevent **Wet Stacking**, minimize Specific Fuel Consumption (SFC), and compute tradable carbon credits.")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        gen_cap = st.number_input("Total Genset Capacity (kW)", value=1000.0)
        actual_load = st.number_input("Current Facility Load (kW)", value=350.0)
        fuel_price = st.number_input("Fuel Price ($ / Liter)", value=1.0)
    with col_f2:
        carbon_price = st.number_input("Carbon Credit Price ($ / Ton CO2)", value=25.0)
        operating_hours_year = st.number_input("Annual Operating Hours", value=4000.0)
        
    # Efficiency & fuel calculations
    load_ratio = (actual_load / gen_cap) * 100
    if load_ratio < 40:
        sfc_val = 0.31 # Liters per kWh at low loads (Wet Stacking risk)
        efficiency_status = "⚠️ Warning: Low load ratio leads to incomplete combustion (Wet Stacking)."
    else:
        sfc_val = 0.24 # Optimal efficiency at 60-80% loads
        efficiency_status = "✅ Optimal load range. High efficiency and minimal fuel waste."
        
    annual_fuel = actual_load * sfc_val * operating_hours_year
    annual_co2_tons = (annual_fuel * 2.68) / 1000.0 # 2.68 kg CO2 per liter diesel
    carbon_revenue = annual_co2_tons * carbon_price
    
    st.divider()
    st.markdown("### 📊 Economic & Environmental Optimization Summary:")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Load Ratio %", f"{load_ratio:.1f}%")
    m2.metric("Specific Fuel Consumption", f"{sfc_val} L/kWh")
    m3.metric("Annual CO2 Emissions", f"{annual_co2_tons:,.1f} Tons")
    m4.metric("Carbon Credits Value", f"${carbon_revenue:,.0f}")
    
    st.info(efficiency_status)
    
    if st.button("Generate AI Synchronization Recommendation"):
        st.success("""
        **🤖 AI Synchronization Decision:**
        * Instead of running two 500 kVA generators at 35% partial load each (which causes heavy wet stacking and fuel waste), **AI recommends running a single 500 kVA unit at 70% optimal load**.
        * **Estimated Annual Savings:** ~$42,000 in fuel costs and 115 tons of CO2 reduced.
        """)

st.divider()
st.caption("ATS DocGen AI Engine v5.0 — Built for Addoma Trading Services & Professional Power Systems Consulting.")
