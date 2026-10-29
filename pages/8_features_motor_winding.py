import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# ==========================================
# 1. وحدة لف المحركات المتقدمة (Motor Winding Engine)
# ==========================================
class AdvancedMotorWindingEngine:
    def __init__(self, slots, poles, phases, winding_type="Concentric", pitch_type="Full Pitch"):
        self.slots = slots                  # عدد المجاري (Stator Slots)
        self.poles = poles                  # عدد الأقطاب
        self.phases = phases                # عدد الأوجه (3-Phase)
        self.winding_type = winding_type    # نوع اللف (Concentric / Lap / Wave)
        self.pitch_type = pitch_type        # نوع الخطوة (Full Pitch / Fractional Pitch)

    def calculate_advanced_parameters(self):
        """حسابات هندسية متقدمة تشمل الخطوة الكسرية والأقطاب المتداخلة"""
        slots_per_pole = self.slots / self.poles
        slots_per_pole_phase = self.slots / (self.poles * self.phases)
        
        # حساب خطوة اللف النظرية والعملية للخطوة الكسرية
        ideal_coil_span = slots_per_pole
        if self.pitch_type == "Fractional Pitch":
            # تقريب خطوة اللف لخطوة كسرية عملية (مثلاً تقليل خطوة واحدة لتخفيف التوافقية)
            practical_coil_span = int(np.floor(ideal_coil_span))
            pitch_factor = np.sin((practical_coil_span / ideal_coil_span) * (np.pi / 2))
        else:
            practical_coil_span = int(round(ideal_coil_span))
            pitch_factor = 1.0

        # إعدادات الوصلات الخارجية (مثلاً 24 طرفاً للأطراف والبدايات للمحركات الكبيرة)
        terminal_connections = "24 External Jumper Connections (Multi-Parallel / Star-Delta)" if self.slots >= 48 else "Standard Terminal Configuration (6 Terminals)"

        results = {
            "Total Stator Slots": self.slots,
            "Number of Poles": self.poles,
            "Slots per Pole (q_total)": round(slots_per_pole, 2),
            "Slots per Pole per Phase (q)": round(slots_per_pole_phase, 2),
            "Ideal Coil Span": round(ideal_coil_span, 1),
            "Selected Coil Span": practical_coil_span,
            "Pitch Factor (Kp)": round(pitch_factor, 3),
            "Winding Style": self.winding_type,
            "Terminal Layout & Jumpers": terminal_connections
        }
        return results

    def generate_detailed_pole_map(self):
        """توليد خريطة تفصيلية لتوزيع المجاري والأقطاب والخطوات المتداخلة"""
        phase_distribution = []
        slot_angle = 360.0 / self.slots
        
        for s in range(1, self.slots + 1):
            phase_idx = (s - 1) % self.phases
            phase_name = ['U (Phase A)', 'V (Phase B)', 'W (Phase C)'][phase_idx] if self.phases == 3 else f"Phase {phase_idx+1}"
            
            # تحديد ما إذا كان المجرى يقع في منطقة قطب شمالي أو جنوبي (Consequent / Alternating)
            pole_zone = int(((s - 1) / self.slots) * self.poles) + 1
            magnetic_polarity = "North (N)" if pole_zone % 2 != 0 else "South (S)"
            
            phase_distribution.append({
                "Slot No": s,
                "Phase": phase_name,
                "Pole Zone": pole_zone,
                "Polarity": magnetic_polarity,
                "Mechanical Angle (deg)": round(s * slot_angle, 1)
            })
            
        return pd.DataFrame(phase_distribution)

    def generate_stator_plot(self, df_map):
        """رسم مخطط بصري قطبي دائري يوضح توزيع المجاري والأوجه"""
        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={'projection': 'polar'})
        theta = np.deg2rad(df_map["Mechanical Angle (deg)"])
        r = np.ones_like(theta) * 10
        
        phase_colors = {'U (Phase A)': '#ff4b4b', 'V (Phase B)': '#00cc66', 'W (Phase C)': '#3399ff'}
        colors = [phase_colors.get(p, '#888888') for p in df_map["Phase"]]
        
        ax.scatter(theta, r, c=colors, s=120, edgecolors='black', linewidths=1.2, zorder=3)
        ax.set_rticks([])
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_title("مخطط توزيع المجاري والأقطاب (Stator Winding Map)", va='bottom', fontsize=12, fontweight='bold')
        return fig

# ==========================================
# 2. وحدة التزامن والمزامنة للمولدات (Synchronization)
# ==========================================
class GeneratorSyncEngine:
    def __init__(self, gen1_voltage, gen2_voltage, gen1_freq, gen2_freq, phase_angle_diff):
        self.v1 = gen1_voltage
        self.v2 = gen2_voltage
        self.f1 = gen1_freq
        self.f2 = gen2_freq
        self.d_theta = phase_angle_diff  # فرق الوجه بالدرجات

    def evaluate_synchronization(self):
        """التحقق من شروط التزامن المتوازي للمولدات (Parallel Connection)"""
        voltage_diff = abs(self.v1 - self.v2)
        freq_diff = abs(self.f1 - self.f2)
        
        v_ok = voltage_diff <= (0.05 * self.v1)
        f_ok = freq_diff <= 0.1
        angle_ok = abs(self.d_theta) <= 5.0
        
        status = "SAFE TO SYNCHRONIZE (Parallel Close)" if (v_ok and f_ok and angle_ok) else "LOCK OUT - CONDITIONS NOT MET"
        
        return {
            "Voltage Difference (V)": round(voltage_diff, 2),
            "Frequency Difference (Hz)": round(freq_diff, 2),
            "Phase Angle Diff (deg)": self.d_theta,
            "Synchronization Status": status
        }

# ==========================================
# 3. واجهة التحكم الشاملة (Streamlit Hub)
# ==========================================
def main():
    st.set_page_config(page_title="المجمع الصناعي الشامل للصيانة والتزامن", layout="wide")
    
    st.sidebar.title("🛠️ لوحة تحكم المجمع الصناعي")
    app_mode = st.sidebar.selectbox("اختر القسم الفني:", [
        "1. حسابات وخرائط لف المحركات المتقدمة (AC/DC)",
        "2. وحدة التزامن والمزامنة للمولدات (Sync)",
        "3. إدارة وتوسيع أقسام الصيانة التنبؤية"
    ])

    if app_mode == "1. حسابات وخرائط لف المحركات المتقدمة (AC/DC)":
        st.header("⚡ المحاكي الهندسي المتقدم لف المحركات والخطوات الكسرية")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            slots = st.number_input("عدد المجاري (Stator Slots)", min_value=12, max_value=144, value=48)
        with col2:
            poles = st.selectbox("عدد الأقطاب (Poles)", [2, 4, 6, 8, 12], index=1)
        with col3:
            winding_type = st.selectbox("نوع اللف", ["Concentric (متداخلة)", "Lap Winding (تموجية/طبقات)", "Wave Winding"])
        with col4:
            pitch_type = st.selectbox("نوع الخطوة", ["Full Pitch (خطوة كاملة)", "Fractional Pitch (خطوة كسرية)"])

        engine = AdvancedMotorWindingEngine(slots=slots, poles=poles, phases=3, winding_type=winding_type, pitch_type=pitch_type)
        params = engine.calculate_advanced_parameters()
        
        st.subheader("📊 النتائج الحسابية وخصائص اللف:")
        st.json(params)
        
        st.subheader("🎨 الرسم البصري التوضيحي للمجاري والأقطاب (Stator Diagram):")
        df_map = engine.generate_detailed_pole_map()
        fig = engine.generate_stator_plot(df_map)
        st.pyplot(fig)

        st.subheader("🗺️ خريطة توزيع المجاري والأقطاب التفصيلية:")
        st.dataframe(df_map, use_container_width=True)

    elif app_mode == "2. وحدة التزامن والمزامنة للمولدات (Sync)":
        st.header("🔄 نظام المزامنة والربط المتوازي للمولدات (Parallel Generators)")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Busbar / Generator 1")
            v1 = st.number_input("جهد المصدر الأول (V)", value=400.0)
            f1 = st.number_input("تردد المصدر الأول (Hz)", value=50.0)
        with col2:
            st.markdown("### Incoming Generator 2")
            v2 = st.number_input("جهد المولد الداخل (V)", value=401.0)
            f2 = st.number_input("تردد المولد الداخل (Hz)", value=50.0)
            angle = st.slider("فرق الزاوية (Phase Angle 𝚫θ)", -30.0, 30.0, 1.5)

        sync_engine = GeneratorSyncEngine(v1, v2, f1, f2, angle)
        sync_results = sync_engine.evaluate_synchronization()
        
        st.subheader("🚦 تقرير حالة التزامن (Synchronization Report):")
        if "SAFE" in sync_results["Synchronization Status"]:
            st.success(f"حالة المزامنة: {sync_results['Synchronization Status']}")
        else:
            st.error(f"حالة المزامنة: {sync_results['Synchronization Status']}")
        
        st.json(sync_results)

    elif app_mode == "3. إدارة وتوسيع أقسام الصيانة التنبؤية":
        st.header("🧩 إدارة وتوسيع الأقسام البرمجية للمجمع الصناعي")
        st.info("منصة معيارية مجهزة لربط خوارزميات الذكاء الاصطناعي، بيانات الاهتزازات، وتحليل أداء محركات الديزل ومولدات CAT وCummins.")
        
        new_module_name = st.text_input("اسم القسم البرمجي الجديد المراد إضافته:")
        module_category = st.selectbox("تصنيف القسم:", ["تحليل الاهتزازات (Vibration Analysis)", "مراقبة نظام الوقود (Fuel System Diagnostics)", "العمر الإنتبائي المتبقي (RUL Estimation)"])
        
        if st.button("تفعيل وهيكلة القسم الجديد في المنظومة"):
            if new_module_name:
                st.success(f"تم إنشاء وتكامل القسم [{new_module_name}] تحت تصنيف ({module_category}) بنجاح داخل هيكل المنظومة!")
            else:
                st.warning("الرجاء إدخال اسم القسم الجديد.")

if __name__ == "__main__":
    main()
