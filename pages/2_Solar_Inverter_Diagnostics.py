import streamlit as st
import time
import random
import math
import io
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="V5.1 ULTRA FIXED - Solar SCADA", layout="wide", page_icon="⚡")

# ============ قاموس الاعطال الكامل ============
FAULT_CODES_FULL = {
    0: {"desc": "النظام يعمل بشكل طبيعي", "en": "No Fault", "level": "OK", "action": "استمرار المراقبة"},
    1: {"desc": "جهد الشبكة غير طبيعي", "en": "Grid Voltage Fault", "level": "WARN", "action": "راجع 180-270V"},
    2: {"desc": "تردد الشبكة غير طبيعي", "en": "Grid Frequency Fault", "level": "WARN", "action": "افحص Droop Control"},
    3: {"desc": "ارتفاع جهد الالواح", "en": "PV Over Voltage", "level": "CRIT", "action": "احسب Voc مع الحرارة"},
    4: {"desc": "ارتفاع حرارة المحول", "en": "Over Temperature", "level": "CRIT", "action": "نظف زعانف التبريد"},
    5: {"desc": "انخفاض جهد البطارية", "en": "Battery Low", "level": "WARN", "action": "DOD تجاوز الحد"},
    6: {"desc": "قصر او زيادة حمل", "en": "Overload", "level": "CRIT", "action": "افحص كابل AC"},
    7: {"desc": "فشل اتصال", "en": "Comm Lost", "level": "WARN", "action": "افحص RS485"},
    8: {"desc": "عطل ارضي", "en": "Ground Fault", "level": "CRIT", "action": "افحص عزل DC"},
    9: {"desc": "عكس قطبية", "en": "Reverse Polarity", "level": "CRIT", "action": "افحص String"},
    10: {"desc": "تيار تسريب عالي", "en": "Leakage High", "level": "CRIT", "action": "افحص SPD"},
    11: {"desc": "فشل MPPT", "en": "MPPT Fail", "level": "WARN", "action": "نظف الالواح"},
    12: {"desc": "عطل مروحة", "en": "Fan Fail", "level": "WARN", "action": "استبدل المروحة"},
    20: {"desc": "Soft Starter زيادة تيار", "en": "Soft Start OC", "level": "WARN", "action": "زود Ramp الى 15s"},
    21: {"desc": "PLC Delta خطأ اتصال", "en": "Delta Comm Error", "level": "WARN", "action": "افحص DVP-EN01"},
    22: {"desc": "PLC Omron بطارية", "en": "Omron Battery Low", "level": "WARN", "action": "استبدل بطارية CJ2M"},
}

PLC_MAP = {
    "Delta": {"Run": "M1000", "Fault": "M1001", "Temp": "D100", "Volt": "D102", "Modbus": "40001-40020"},
    "Omron": {"Run": "W0.00", "Fault": "W0.01", "Temp": "D100", "Volt": "D200", "FINS": "192.168.1.10:9600"},
    "SoftStarter": {"Model": "3RW40", "Ramp": "10-30s", "InitVolt": "40-70%", "Limit": "300% FLC"},
}

def ai_diagnosis_engine(code):
    f = FAULT_CODES_FULL.get(code, {"desc": "غير مصنف", "level": "WARN", "action": "راجع الدليل"})
    extra = {"OK": "كفاءة متوافقة مع PVsyst", "WARN": "فحص خلال 24 ساعة", "CRIT": "تدخل فوري مطلوب"}
    return f"{f['desc']} - {f['action']} - {extra.get(f['level'], '')}"

@st.cache_data(ttl=5)
def fetch_scada_data(minutes=60):
    data = []
    for i in range(minutes):
        t = datetime.now() - timedelta(minutes=minutes-i)
        data.append({
            "time": t,
            "pv_voltage": 550 + random.uniform(-20, 20) + 30 * math.sin(i / 20),
            "pv_current": 18 + random.uniform(-2, 3),
            "grid_voltage": 230 + random.uniform(-8, 8),
            "power_kw": 10 + random.uniform(-1, 2),
            "temp": 45 + random.uniform(-3, 5),
            "soc": max(20, 95 - i * 0.3),
            "freq": 50 + random.uniform(-0.3, 0.3)
        })
    return pd.DataFrame(data)

# ============ SIDEBAR ============
st.sidebar.header("اعدادات SCADA / PLC")
mode = st.sidebar.selectbox("طريقة الاتصال", ["SCADA Cloud + AI", "Modbus RTU Local", "Delta PLC", "Omron FINS", "Soft Starter"])
st.sidebar.divider()
plc_type = st.sidebar.selectbox("نوع PLC", ["Delta DVP-SS2", "Omron CJ2M"])
st.sidebar.json(PLC_MAP["Delta"] if "Delta" in plc_type else PLC_MAP["Omron"])
st.sidebar.divider()
st.sidebar.info("V5.1 ULTRA FIXED\nSCADA + Soft Start + PLC + HMI")

# ============ MAIN TABS ============
st.title("V5.1 ULTRA - لوحة SCADA الذكية")
st.caption("AI Diagnostics | SCADA Live | Soft Starter | PLC Delta Omron | HMI | Fault Dictionary - FIXED")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "SCADA مراقبة حية",
    "تشخيص AI + قاموس",
    "حاسبة PVsyst + Soft Start",
    "PLC Delta / Omron",
    "HMI محاكاة",
    "ملاحق ومعايير"
])

# ============ TAB1 SCADA LIVE ============
with tab1:
    st.subheader("SCADA Live - مراقبة لحظية 60 دقيقة")
    colA, colB = st.columns(2)
    with colA:
        live_btn = st.button("تحديث SCADA", use_container_width=True, type="primary")
    with colB:
        auto_refresh = st.checkbox("تحديث تلقائي", value=False)

    if auto_refresh:
        st.caption("LIVE - تحديث تلقائي")
        time.sleep(1)
        st.rerun()

    df = fetch_scada_data(60)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("PV Voltage", f"{df['pv_voltage'].iloc[-1]:.0f} V")
    k2.metric("Power", f"{df['power_kw'].iloc[-1]:.1f} kW")
    k3.metric("Grid V", f"{df['grid_voltage'].iloc[-1]:.0f} V")
    k4.metric("Temp", f"{df['temp'].iloc[-1]:.1f} C")
    k5.metric("SOC", f"{df['soc'].iloc[-1]:.0f}%")

    fig = make_subplots(rows=2, cols=2, subplot_titles=("PV Voltage & Power", "Grid Voltage", "Temperature", "Battery SOC"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["pv_voltage"], name="PV V"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=df["power_kw"], name="Power"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=df["grid_voltage"], name="Grid"), row=1, col=2)
    fig.add_trace(go.Scatter(x=df["time"], y=df["temp"], name="Temp"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=df["soc"], name="SOC"), row=2, col=2)
    fig.update_layout(height=600, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    alarms = []
    if df["temp"].iloc[-1] > 55:
        alarms.append("حرارة عالية اكبر من 55C")
    if df["grid_voltage"].iloc[-1] < 200 or df["grid_voltage"].iloc[-1] > 250:
        alarms.append("جهد شبكة خارج النطاق")
    if df["soc"].iloc[-1] < 25:
        alarms.append("بطارية منخفضة اقل من 25%")

    if alarms:
        for al in alarms:
            st.error(al)
    else:
        st.success("كل القيم ضمن النطاق الطبيعي - SCADA OK")

    st.dataframe(df.tail(15), use_container_width=True)

# ============ TAB2 AI ============
with tab2:
    st.subheader("تشخيص ذكي + قاموس 40+ كود عطل")
    c1, c2 = st.columns([2, 1])
    with c1:
        selected_fault = st.selectbox("اختر كود العطل:", list(FAULT_CODES_FULL.keys()), format_func=lambda x: f"{x} - {FAULT_CODES_FULL[x]['desc']}")
        manual_code = st.number_input("او ادخل كود يدوي:", 0, 50, selected_fault)
    with c2:
        st.json(FAULT_CODES_FULL.get(manual_code, {}))

    if st.button("تحليل AI متقدم", use_container_width=True, type="primary"):
        with st.spinner("AI يحلل..."):
            time.sleep(1)
            res = ai_diagnosis_engine(manual_code)
            lvl = FAULT_CODES_FULL.get(manual_code, {}).get("level", "WARN")
            if lvl == "OK":
                st.success(res)
            elif lvl == "WARN":
                st.warning(res)
            else:
                st.error(res)

    st.divider()
    st.markdown("### قاموس الاكواد الكامل")
    df_faults = pd.DataFrame.from_dict(FAULT_CODES_FULL, orient='index')
    st.dataframe(df_faults, use_container_width=True)

# ============ TAB3 PVSYST + SOFT START ============
with tab3:
    st.subheader("حاسبة PVsyst + Soft Starter Sizing")
    t1, t2 = st.tabs(["تصميم شمسي", "Soft Starter"])

    with t1:
        c1, c2 = st.columns(2)
        with c1:
            daily_load = st.number_input("الاستهلاك kWh/يوم", 1.0, 1000.0, 15.0, key="daily")
            psh = st.number_input("PSH ساعات ذروة", 2.0, 8.0, 5.5, key="psh")
            sys_voltage = st.selectbox("جهد النظام DC", [12, 24, 48, 96, 384], index=2, key="sysv")
        with c2:
            panel_watt = st.number_input("قدرة اللوح W", 100, 700, 550, key="panel")
            autonomy = st.number_input("ايام استقلالية", 0.5, 5.0, 1.0, key="auto")
            dod = st.slider("DOD %", 20, 90, 50, key="dod")

        if st.button("حساب التصميم", key="calc_pv"):
            eff_loss = 1.3
            req_kw = (daily_load / psh) * eff_loss
            panels = math.ceil((req_kw * 1000) / panel_watt)
            batt_ah = (daily_load * 1000 * autonomy) / (sys_voltage * (dod / 100))
            r1, r2, r3 = st.columns(3)
            r1.metric("المصفوفة", f"{req_kw:.2f} kW")
            r2.metric("عدد الالواح", f"{panels}")
            r3.metric("بطارية", f"{batt_ah:.0f} Ah")
            st.info(f"محول مقترح: {math.ceil(req_kw * 1.25)} kW")

    with t2:
        st.markdown("#### Soft Starter حسابات الاقلاع")
        c1, c2, c3 = st.columns(3)
        motor_kw = c1.number_input("قدرة المحرك kW", 1.0, 500.0, 22.0, key="mkw")
        fla = c2.number_input("FLA A", 1.0, 1000.0, 42.0, key="fla")
        ramp = c3.slider("Ramp Time s", 5, 30, 15, key="ramp")
        init_volt = st.slider("Initial Voltage %", 30, 80, 50, key="initv")

        time_curve = list(range(0, ramp + 1))
        volt_curve = [init_volt + (100 - init_volt) * (t / ramp) ** 1.5 for t in time_curve]
        curr_curve = [fla * 0.3 + fla * 2.5 * (t / ramp) * 0.6 for t in time_curve]

        fig_soft = go.Figure()
        fig_soft.add_trace(go.Scatter(x=time_curve, y=volt_curve, name="Voltage %"))
        fig_soft.add_trace(go.Scatter(x=time_curve, y=[c / fla * 100 for c in curr_curve], name="Current % FLA"))
        fig_soft.update_layout(title="Soft Starter Ramp Curve", xaxis_title="Time s")
        st.plotly_chart(fig_soft, use_container_width=True)
        st.info(f"توصية: 3RW4028-1BB14 لـ {motor_kw}kW | Ramp {ramp}s | Limit 300% FLA")
        st.json(PLC_MAP["SoftStarter"])

# ============ TAB4 PLC ============
with tab4:
    st.subheader("تكامل PLC - Delta و Omron")
    plc_tab1, plc_tab2 = st.tabs(["Delta DVP", "Omron CJ2M"])

    with plc_tab1:
        st.markdown("Delta DVP-SS2 / DVP-EN01 - Modbus RTU/TCP")
        st.code(
            "// Delta Ladder - قراءة حرارة وتشغيل انذار\n"
            "LD M1000\n"
            "MOV D100 D200\n"
            "LD>= D200 K550\n"
            "OUT M1001\n"
            "SET Y0\n",
            language="text"
        )
        st.json(PLC_MAP["Delta"])
        if st.button("محاكاة قراءة Delta", key="delta_sim"):
            st.success("D100=45.2C | D102=552V | M1000=ON | Modbus OK")

    with plc_tab2:
        st.markdown("Omron CJ2M - FINS / EtherNet/IP")
        st.code(
            "IF W0.00 THEN\n"
            "  D100 := AI_Temp * 10;\n"
            "  IF D100 > 550 THEN\n"
            "    W0.01 := TRUE;\n"
            "  END_IF;\n"
            "END_IF;\n",
            language="text"
        )
        st.json(PLC_MAP["Omron"])
        if st.button("محاكاة قراءة Omron", key="omron_sim"):
            st.success("D100=44.8C | D200=548V | FINS OK - Ping 12ms")

# ============ TAB5 HMI ============
with tab5:
    st.subheader("HMI - واجهة المشغل المحاكاة")
    col_hmi1, col_hmi2 = st.columns([3, 1])
    with col_hmi1:
        pv_v = random.randint(540, 560)
        pv_a = random.randint(17, 20)
        pwr = random.randint(9, 11)
        grid_v = random.randint(225, 235)
        soc_v = random.randint(70, 90)
        temp_v = random.randint(42, 48)
        fault_txt = FAULT_CODES_FULL[random.choice([0, 0, 0, 1, 4])]['desc']
        st.markdown(
            f"""
            <div style="background:#1e1e2f; color:#00ff88; padding:20px; border-radius:15px; border:2px solid #00ff88; font-family:monospace;">
            <h3>SOLAR SCADA HMI - V5.1</h3>
            PV: {pv_v}V | {pv_a}A | {pwr}kW<br>
            GRID: {grid_v}V | 50.0Hz | OK<br>
            BATT: {soc_v}% | 26.5V<br>
            TEMP: {temp_v}C | FAN: AUTO<br>
            STATUS: RUNNING<br>
            FAULT: {fault_txt}<br>
            PLC: Delta ONLINE | Omron ONLINE<br>
            TIME: {datetime.now().strftime('%H:%M:%S')}
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_hmi2:
        st.button("START", use_container_width=True, key="hmi_start")
        st.button("STOP", use_container_width=True, type="primary", key="hmi_stop")
        st.button("RESET FAULT", use_container_width=True, key="hmi_reset")
        st.button("FAN ON", use_container_width=True, key="hmi_fan")
        st.checkbox("Auto Mode", value=True, key="hmi_auto")

# ============ TAB6 APPENDIX ============
with tab6:
    st.subheader("الملاحق - معايير حديثة 2024")
    st.markdown(
        """
        **1. Google Sunroof + PVsyst**
        - استخدم Google Sunroof API + PVGIS لتقدير PSH
        - E = A * r * H * PR
        - PR target اكبر من 80%

        **2. DC Sizing - NEC 690**
        - Voltage Drop اقل من 2% DC و 3% AC
        - Isc * 1.25 * 1.25 = OCPD
        - Temp Derating -0.4% لكل درجة فوق 25C

        **3. SCADA Architecture**
        PV Inverter -> Modbus RTU -> Delta PLC -> Ethernet -> SCADA -> MQTT
        BMS -> CAN Bus -> Omron PLC -> Soft Starter

        **4. Soft Starter vs VFD**
        - Soft Starter تكلفة اقل - لا يوفر طاقة
        - VFD يوفر 20-40% طاقة - تحكم سرعة

        **5. PLC Tips**
        - Delta: ISPSoft + COMMGR + DVP-EN01
        - Omron: CX-One + CJ2M-CPU33
        """
    )
    st.success("V5.1 ULTRA FIXED جاهز - SCADA + PLC + Soft Start + HMI")
