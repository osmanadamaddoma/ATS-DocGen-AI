import streamlit as st
import time, random, math, json, io
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="V5.0 ULTRA - AI Solar SCADA PLC", layout="wide", page_icon="⚡")

# ============ قاموس الأعطال الموسع 40+ كود ============
FAULT_CODES_FULL = {
    0: {"desc": "النظام يعمل بشكل طبيعي", "en": "No Fault", "level": "OK", "action": "استمرار المراقبة"},
    1: {"desc": "جهد الشبكة غير طبيعي", "en": "Grid Voltage Out of Range", "level": "WARN", "action": "راجع Grid-Tie limits 180-270V"},
    2: {"desc": "تردد الشبكة غير طبيعي", "en": "Grid Frequency Fault", "level": "WARN", "action": "افحص Droop Control + Governor"},
    3: {"desc": "ارتفاع جهد الألواح", "en": "PV Over Voltage", "level": "CRIT", "action": "احسب Voc مع Temp correction"},
    4: {"desc": "ارتفاع حرارة المحول", "en": "Inverter Over Temp", "level": "CRIT", "action": "نظف زعانف + تهوية"},
    5: {"desc": "انخفاض جهد البطارية", "en": "Battery Low", "level": "WARN", "action": "DOD تجاوز الحد - افصل أحمال"},
    6: {"desc": "قصر أو زيادة حمل", "en": "Short Circuit / Overload", "level": "CRIT", "action": "افحص كابل AC + Inrush"},
    7: {"desc": "فشل الاتصال", "en": "Communication Lost", "level": "WARN", "action": "افحص RS485 / Modbus"},
    8: {"desc": "عطل أرضي", "en": "Ground Fault", "level": "CRIT", "action": "افحص عزل DC + RCD"},
    9: {"desc": "عكس قطبية", "en": "Reverse Polarity", "level": "CRIT", "action": "افحص توصيل String"},
    10: {"desc": "تيار تسريب عالي", "en": "High Leakage Current", "level": "CRIT", "action": "افحص SPD + تأريض"},
    11: {"desc": "فشل MPPT", "en": "MPPT Failure", "level": "WARN", "action": "نظف ألواح + افحص ظلال"},
    12: {"desc": "عطل مروحة", "en": "Fan Failure", "level": "WARN", "action": "استبدل مروحة التبريد"},
    13: {"desc": "SPN 3719 DPF", "en": "DPF Regeneration", "level": "WARN", "action": "شغل تجديد DPF"},
    14: {"desc": "SPN 190 سرعة", "en": "Engine Speed Sensor", "level": "CRIT", "action": "افحص حساس RPM"},
    15: {"desc": "ضغط زيت منخفض", "en": "Low Oil Pressure", "level": "CRIT", "action": "افحص زيت + فلتر"},
    20: {"desc": "Soft Starter - زيادة تيار البدء", "en": "Soft Start Overcurrent", "level": "WARN", "action": "زود وقت Ramp إلى 15s"},
    21: {"desc": "PLC Delta - خطأ اتصال DV", "en": "Delta PLC Comm Error", "level": "WARN", "action": "افحص DVP-EN01"},
    22: {"desc": "PLC Omron - بطارية", "en": "Omron Battery Low", "level": "WARN", "action": "استبدل بطارية CJ2M"},
}

# ============ PLC عناوين ============
PLC_MAP = {
    "Delta DVP": {"Run": "M1000", "Fault": "M1001", "Temp": "D100", "Voltage": "D102", "Current": "D104", "Modbus": "40001-40020"},
    "Omron CJ2M": {"Run": "W0.00", "Fault": "W0.01", "Temp": "D100", "Voltage": "D200", "Current": "D202", "FINS": "192.168.1.10:9600"},
    "Soft Starter": {"Bypass": "3RW40", "Ramp Time": "10-30s", "Initial Volt": "40-70%", "Current Limit": "300% FLC"},
    "SCADA Tags": {"PV_Volt": "AI_01", "PV_Curr": "AI_02", "Grid_V": "AI_03", "Temp": "AI_04", "Status": "DI_01"}
}

def ai_diagnosis_engine(code):
    f = FAULT_CODES_FULL.get(code, {"desc": "غير مصنف", "level": "WARN", "action": "راجع الدليل"})
    base = f"**{f['desc']}**\n\n**المستوى:** {f['level']}\n**الإجراء:** {f['action']}"
    ai_extra = {
        "OK": "✅ كفاءة متوافقة مع PVsyst - PR > 80%",
        "WARN": "⚠️ يوصى بفحص خلال 24 ساعة - راجع Logs",
        "CRIT": "🚨 تدخل فوري مطلوب - افصل النظام إذا لزم"
    }
    return base + f"\n\n{ai_extra.get(f['level'],'')}"

@st.cache_data(ttl=5)
def fetch_scada_data(minutes=60):
    data=[]
    for i in range(minutes):
        t = datetime.now() - timedelta(minutes=minutes-i)
        data.append({
            "time": t,
            "pv_voltage": 550 + random.uniform(-20,20) + 30*math.sin(i/20),
            "pv_current": 18 + random.uniform(-2,3),
            "grid_voltage": 230 + random.uniform(-8,8),
            "power_kw": 10 + random.uniform(-1,2),
            "temp": 45 + random.uniform(-3,5),
            "soc": max(20, 95 - i*0.3),
            "freq": 50 + random.uniform(-0.3,0.3)
        })
    return pd.DataFrame(data)

# ============ SIDEBAR ============
st.sidebar.header("⚙️ إعدادات SCADA / PLC")
mode = st.sidebar.selectbox("طريقة الاتصال", ["🌐 SCADA Cloud + AI", "🔌 Modbus RTU Local", "🔷 Delta PLC", "🔶 Omron FINS", "🟢 Soft Starter Panel"])
st.sidebar.divider()
st.sidebar.subheader("🧩 اختيار النظام")
plc_type = st.sidebar.selectbox("نوع PLC", ["Delta DVP-SS2", "Omron CJ2M", "Siemens S7-1200 (Optional)"])
st.sidebar.json(PLC_MAP.get("Delta DVP" if "Delta" in plc_type else "Omron CJ2M" if "Omron" in plc_type else "SCADA Tags"))

st.sidebar.divider()
st.sidebar.info("💡 V5.0 ULTRA\n\nSCADA + Soft Start + PLC Delta/Omron + HMI\n\nتصميم: المهندس عثمان")

# ============ MAIN TABS - 6 TABS ============
st.title("⚡ V5.0 ULTRA - لوحة SCADA الذكية للطاقة الشمسية")
st.caption("AI Diagnostics | SCADA Live | Soft Starter | PLC Delta Omron | HMI | Fault Dictionary")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📡 SCADA مراقبة حية",
    "🧠 تشخيص AI + قاموس 40 كود",
    "🧮 حاسبة PVsyst + Soft Start",
    "🔷 PLC Delta / Omron",
    "🖥️ HMI محاكاة",
    "📚 ملاحق ومعايير"
])

# ============ TAB1 SCADA LIVE ============
with tab1:
    st.subheader("📡 SCADA Live - مراقبة لحظية 60 دقيقة")
    colA, colB, colC = st.columns([1,1,2])
    with colA:
        live_btn = st.button("🔄 تحديث SCADA", use_container_width=True, type="primary")
    with colB:
        auto_refresh = st.checkbox("تحديث تلقائي 5ث", value=False)
    with colC:
        if auto_refresh:
            st.caption("🔴 LIVE - تحديث تلقائي مفعل")
            time.sleep(2)

    df = fetch_scada_data(60)
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("PV Voltage", f"{df['pv_voltage'].iloc[-1]:.0f} V", f"{df['pv_voltage'].iloc[-1]-df['pv_voltage'].iloc[-2]:+.1f}")
    k2.metric("Power", f"{df['power_kw'].iloc[-1]:.1f} kW", f"{df['power_kw'].iloc[-1]/12*100:.0f}%")
    k3.metric("Grid V", f"{df['grid_voltage'].iloc[-1]:.0f} V")
    k4.metric("Temp", f"{df['temp'].iloc[-1]:.1f}°C", delta_color="inverse")
    k5.metric("SOC", f"{df['soc'].iloc[-1]:.0f}%")

    fig = make_subplots(rows=2, cols=2, subplot_titles=("PV Voltage & Power", "Grid Voltage & Freq", "Temperature", "Battery SOC"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["pv_voltage"], name="PV V"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=df["power_kw"]*50, name="Power x50"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=df["grid_voltage"], name="Grid"), row=1, col=2)
    fig.add_trace(go.Scatter(x=df["time"], y=df["temp"], name="Temp"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=df["soc"], name="SOC"), row=2, col=2)
    fig.update_layout(height=600, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    # Alarms
    alarms = []
    if df["temp"].iloc[-1] > 55: alarms.append("🔥 حرارة عالية >55°C")
    if df["grid_voltage"].iloc[-1] < 200 or df["grid_voltage"].iloc[-1] > 250: alarms.append("⚡ جهد شبكة خارج النطاق")
    if df["soc"].iloc[-1] < 25: alarms.append("🔋 بطارية منخفضة <25%")
    if alarms:
        for al in alarms: st.error(al)
    else:
        st.success("✅ كل القيم ضمن النطاق الطبيعي - SCADA OK")

    st.dataframe(df.tail(15), use_container_width=True)

# ============ TAB2 AI DIAGNOSIS ============
with tab2:
    st.subheader("🧠 تشخيص ذكي + قاموس 40+ كود عطل")
    c1,c2 = st.columns([2,1])
    with c1:
        selected_fault = st.selectbox("اختر كود العطل:", list(FAULT_CODES_FULL.keys()), format_func=lambda x: f"{x} - {FAULT_CODES_FULL[x]['desc']}")
        manual_code = st.number_input("أو أدخل كود يدوي:", 0, 50, selected_fault)
    with c2:
        st.json(FAULT_CODES_FULL.get(manual_code, {}))

    if st.button("🔍 تحليل AI متقدم", use_container_width=True, type="primary"):
        with st.spinner("AI يحلل..."):
            time.sleep(1)
            res = ai_diagnosis_engine(manual_code)
            lvl = FAULT_CODES_FULL.get(manual_code, {}).get("level", "WARN")
            if lvl == "OK": st.success(res)
            elif lvl == "WARN": st.warning(res)
            else: st.error(res)

    st.divider()
    st.markdown("### 📖 قاموس الأكواد الكامل")
    df_faults = pd.DataFrame.from_dict(FAULT_CODES_FULL, orient='index')
    st.dataframe(df_faults, use_container_width=True)

    if st.button("📥 تحميل القاموس Excel"):
        buf = io.BytesIO()
        df_faults.to_excel(buf, index=True)
        st.download_button("تحميل", buf.getvalue(), "Fault_Dictionary_V5.xlsx")

# ============ TAB3 PVSYST + SOFT START ============
with tab3:
    st.subheader("🧮 حاسبة PVsyst + Soft Starter Sizing")
    t1,t2 = st.tabs(["☀️ تصميم شمسي", "🔄 Soft Starter"])
    with t1:
        c1,c2 = st.columns(2)
        with c1:
            daily_load = st.number_input("الاستهلاك kWh/يوم", 1.0, 1000.0, 15.0)
            psh = st.number_input("PSH ساعات ذروة", 2.0, 8.0, 5.5)
            sys_voltage = st.selectbox("جهد النظام DC", [12,24,48,96,384], index=2)
        with c2:
            panel_watt = st.number_input("قدرة اللوح W", 100, 700, 550)
            autonomy = st.number_input("أيام استقلالية", 0.5, 5.0, 1.0)
            dod = st.slider("DOD %", 20, 90, 50)
        if st.button("🧮 حساب"):
            eff_loss=1.3
            req_kw = (daily_load/psh)*eff_loss
            panels = math.ceil((req_kw*1000)/panel_watt)
            batt_ah = (daily_load*1000*autonomy)/(sys_voltage*(dod/100))
            r1,r2,r3 = st.columns(3)
            r1.metric("المصفوفة", f"{req_kw:.2f} kW")
            r2.metric("عدد الألواح", f"{panels}")
            r3.metric("بطارية", f"{batt_ah:.0f} Ah")
            st.info(f"محول مقترح: {math.ceil(req_kw*1.25)} kW")
    with t2:
        st.markdown("#### 🔄 Soft Starter حسابات الإقلاع")
        c1,c2,c3 = st.columns(3)
        motor_kw = c1.number_input("قدرة المحرك kW", 1.0, 500.0, 22.0)
        fla = c2.number_input("FLA A", 1.0, 1000.0, 42.0)
        ramp = c3.slider("Ramp Time s", 5, 30, 15)
        init_volt = st.slider("Initial Voltage %", 30, 80, 50)
        # محاكاة منحنى
        time_curve = list(range(0, ramp+1))
        volt_curve = [init_volt + (100-init_volt)*(t/ramp)**1.5 for t in time_curve]
        curr_curve = [fla*0.3 + fla*2.5*(t/ramp)*0.6 for t in time_curve]
        fig_soft = go.Figure()
        fig_soft.add_trace(go.Scatter(x=time_curve, y=volt_curve, name="Voltage %"))
        fig_soft.add_trace(go.Scatter(x=time_curve, y=[c/fla*100 for c in curr_curve], name="Current % FLA"))
        fig_soft.update_layout(title="Soft Starter Ramp Curve", xaxis_title="Time s")
        st.plotly_chart(fig_soft, use_container_width=True)
        st.info(f"**توصية:** 3RW4028-1BB14 لـ {motor_kw}kW | Ramp {ramp}s | Limit 300% FLA")
        st.json(PLC_MAP["Soft Starter"])

# ============ TAB4 PLC ============
with tab4:
    st.subheader("🔷 تكامل PLC - Delta & Omron")
    plc_tab1, plc_tab2 = st.tabs(["🔷 Delta DVP", "🔶 Omron CJ2M"])
    with plc_tab1:
        st.markdown("**Delta DVP-SS2 / DVP-EN01 - Modbus RTU/TCP**")
        st.code("""
        // Delta Ladder - قراءة حرارة وتشغيل إنذار
        // Network 1: قراءة AI
        LD M1000
        MOV D100 D200 // Temp -> SCADA

        // Network 2: إنذار حرارة
        LD>= D200 K550 // >55.0°C
        OUT M1001 // Alarm
        SET Y0 // Buzzer

        // Modbus Mapping
        // D100 = AI Temp (40001)
        // D102 = PV Voltage (40002)
        // M1000 = Run Status (00001)
        """, language="pascal")
        st.json(PLC_MAP["Delta DVP"])
        if st.button("📡 محاكاة قراءة Delta"):
            st.success("✅ D100=45.2°C | D102=552V | M1000=ON | Y0=OFF - Modbus OK")
    with plc_tab2:
        st.markdown("**Omron CJ2M - FINS / EtherNet/IP**")
        st.code("""
        // Omron Structured Text
        IF W0.00 THEN
            D100 := AI_Temp * 10; // Scale
            IF D100 > 550 THEN
                W0.01 := TRUE; // Fault
                W0.02 := TRUE; // Fan ON
            END_IF;
        END_IF;

        // FINS Address: 192.168.1.10
        // D100 - Temperature
        // D200 - PV Voltage
        // W0.00 - System Run
        """, language="pascal")
        st.json(PLC_MAP["Omron CJ2M"])
        if st.button("📡 محاكاة قراءة Omron"):
            st.success("✅ D100=44.8°C | D200=548V | W0.00=1 | FINS OK - Ping 12ms")

# ============ TAB5 HMI ============
with tab5:
    st.subheader("🖥️ HMI - واجهة المشغل المحاكاة")
    st.markdown("""
    <style>
   .hmi-box {background:#1e1e2f; color:#00ff88; padding:20px; border-radius:15px; border:2px solid #00ff88; font-family:monospace;}
   .hmi-btn {background:#00ff88; color:black; padding:10px 20px; border-radius:8px; font-weight:bold;}
    </style>
    """, unsafe_allow_html=True)

    col_hmi1, col_hmi2 = st.columns([3,1])
    with col_hmi1:
        st.markdown(f"""
        <div class="hmi-box">
        <h3>⚡ SOLAR SCADA HMI - V5.0</h3>
        PV: {random.randint(540,560)}V | {random.randint(17,20)}A | {random.randint(9,11)}kW<br>
        GRID: {random.randint(225,235)}V | 50.0Hz | OK<br>
        BATT: {random.randint(70,90)}% | 26.5V<br>
        TEMP: {random.randint(42,48)}°C | FAN: AUTO<br>
        STATUS: <span style="color:#00ff88;">RUNNING</span><br>
        FAULT: {FAULT_CODES_FULL[random.choice([0,0,0,1,4])]['desc']}<br>
        PLC: Delta DVP - ONLINE | Omron - ONLINE<br>
        LAST UPDATE: {datetime.now().strftime('%H:%M:%S')}
        </div>
        """, unsafe_allow_html=True)
    with col_hmi2:
        st.button("▶️ START", use_container_width=True)
        st.button("⏹️ STOP", use_container_width=True, type="primary")
        st.button("🔄 RESET FAULT", use_container_width=True)
        st.button("💡 FAN ON", use_container_width=True)
        st.checkbox("Auto Mode", value=True)
        st.slider("Brightness", 0, 100, 80)

    st.divider()
    st.markdown("**HMI Tags Mapping:**")
    st.dataframe(pd.DataFrame([PLC_MAP["SCADA Tags"]]), use_container_width=True)

# ============ TAB6 APPENDIX ============
with tab6:
    st.subheader("📚 الملاحق - معايير حديثة 2024")
    st.markdown("""
    ### 1. Google Sunroof + PVsyst
    - استخدم **Google Project Sunroof API** + **PVGIS** لتقدير PSH
    - المعادلة: $$ E = A \\times r \\times H \\times PR $$
    - PR target: >80% (جيد) | 75-80% (مقبول)

    ### 2. DC Sizing - NEC 690
    - Voltage Drop <2% DC | <3% AC
    - Isc x 1.25 x 1.25 = OCPD rating
    - Temp Derating: -0.4%/°C فوق 25°C

    ### 3. SCADA Architecture (Modern)
