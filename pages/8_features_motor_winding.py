import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# ==========================================
# 1. وحدة لف المحركات المتقدمة (Motor Winding Engine)
# ==========================================
class AdvancedMotorWindingEngine:
    def __init__(self, slots, poles, phases, winding_type="Concentric", pitch_type="Full Pitch", q_val=6):
        self.slots = slots                  # عدد المجاري (Stator Slots)
        self.poles = poles                  # عدد الأقطاب
        self.phases = phases                # عدد الأوجه (3-Phase)
        self.winding_type = winding_type    # نوع اللف (Concentric / Lap / Wave)
        self.pitch_type = pitch_type        # نوع الخطوة (Full Pitch / Fractional Pitch)
        self.q_val = q_val                  # عدد الملفات لكل مجموعة (q/Grp)

    def calculate_advanced_parameters(self):
        """حسابات هندسية متقدمة تشمل الخطوة الكسرية والأقطاب المتداخلة"""
        slots_per_pole = self.slots / self.poles
        slots_per_pole_phase = self.slots / (self.poles * self.phases)
        
        ideal_coil_span = slots_per_pole
        if self.pitch_type == "Fractional Pitch":
            practical_coil_span = int(np.floor(ideal_coil_span))
            pitch_factor = np.sin((practical_coil_span / ideal_coil_span) * (np.pi / 2))
        else:
            practical_coil_span = int(round(ideal_coil_span))
            pitch_factor = 1.0

        terminal_connections = "24 External Jumper Connections (Multi-Parallel / Star-Delta)" if self.slots >= 48 else "Standard Terminal Configuration (6 Terminals)"

        results = {
            "Total Stator Slots (Z)": self.slots,
            "Number of Poles (2p)": self.poles,
            "Slots per Pole (q_total)": round(slots_per_pole, 2),
            "Slots per Pole per Phase (q)": round(slots_per_pole_phase, 2),
            "Coils per Group (q_grp)": self.q_val,
            "Ideal Coil Span": round(ideal_coil_span, 1),
            "Selected Coil Span (Y)": practical_coil_span,
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
        """رسم تخطيطي هندسي تنفيذي احترافي للملفات، المجاري، الأقطاب والأطراف (Us, Ue, Vs, Ve, Ws, We)"""
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.set_aspect('equal')
        ax.axis('off')
        
        r_inner = 3.0
        r_slot = 3.5
        r_outer = 4.0
        
        # دوائر الستاتور الأساسية
        ax.add_patch(plt.Circle((0, 0), r_inner, color='#2c3e50', fill=False, linewidth=2.5))
        ax.add_patch(plt.Circle((0, 0), r_outer, color='#2c3e50', fill=False, linewidth=2.5))
        
        phase_colors = {
            'U (Phase A)': '#d63031',  # أحمر
            'V (Phase B)': '#00b894',  # أخضر
            'W (Phase C)': '#0984e3'   # أزرق
        }
        
        angles = np.deg2rad(df_map["Mechanical Angle (deg)"].values - 90)
        
        # رسم المجاري وترقيمها
        for i, row in df_map.iterrows():
            angle = angles[i]
            x_in, y_in = r_inner * np.cos(angle), r_inner * np.sin(angle)
            x_out, y_out = r_outer * np.cos(angle), r_outer * np.sin(angle)
            
            ax.plot([x_in, x_out], [y_in, y_out], color='#b2bec3', linewidth=1)
            
            x_s, y_s = r_slot * np.cos(angle), r_slot * np.sin(angle)
            color = phase_colors.get(row["Phase"], '#7f8c8d')
            ax.scatter(x_s, y_s, c=color, s=50, zorder=4, edgecolors='black', linewidths=0.5)
            
            xt, yt = 2.3 * np.cos(angle), 2.3 * np.sin(angle)
            font_size = 6 if self.slots > 36 else 8
            ax.text(xt, yt, str(row["Slot No"]), fontsize=font_size, ha='center', va='center', fontweight='bold', color='#2d3436')

        # رسم أقواس الملفات والخطوات المتموجة (Concentric / Grouped Winding Loops)
        span = int(self.slots / self.poles)
        for i, row in df_map.iterrows():
            if i % max(1, int(self.slots / (self.poles * self.phases))) == 0:
                idx1 = i
                idx2 = (i + span) % self.slots
                ang1 = angles[idx1]
                ang2 = angles[idx2]
                
                t = np.linspace(0, np.pi, 50)
                r_loop = r_outer + 0.6 + ((i // max(1, self.q_val)) % 3) * 0.35
                
                base_x1, base_y1 = r_outer * np.cos(ang1), r_outer * np.sin(ang1)
                base_x2, base_y2 = r_outer * np.cos(ang2), r_outer * np.sin(ang2)
                
                curve_x = np.linspace(base_x1, base_x2, 50) + r_loop * 0.3 * np.sin(t)
                curve_y = np.linspace(base_y1, base_y2, 50) + r_loop * 0.3 * np.cos(t)
                
                color = phase_colors.get(row["Phase"], '#7f8c8d')
                ax.plot(curve_x, curve_y, color=color, linewidth=1.2, alpha=0.85)

        # رسم أطراف البدايات والنهايات للأقطاب (Us, Ue, Vs, Ve, Ws, We)
        for p_idx in range(self.poles):
            p_angle = (p_idx * 2 * np.pi / self.poles) - np.pi/2 + (np.pi / self.poles)
            
            label_r = r_outer + 2.0
            lx = label_r * np.cos(p_angle)
            ly = label_r * np.sin(p_angle)
            
            term_label = f"Pole {p_idx+1} [N/S]\n" \
                         f"Us{p_idx+1} ●──● Ue{p_idx+1}\n" \
                         f"Vs{p_idx+1} ●──● Ve{p_idx+1}\n" \
                         f"Ws{p_idx+1} ●──● We{p_idx+1}"
            
            ax.text(lx, ly, term_label, fontsize=7.5, fontweight='bold', ha='center', va='center',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9f9', edgecolor='#7f8c8d', alpha=0.95))

        ax.set_xlim(-7.5, 7.5)
        ax.set_ylim(-7.5, 7.5)
        ax.set_title("مخطط لف المحرك الهندسي التنفيذي المعتمد (Stator Winding & Terminals Blueprint)", fontsize=12, fontweight='bold', pad=25, color='#2c3e50')
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
        self.d_theta = phase_angle_diff

    def evaluate_synchronization(self):
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
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            slots = st.number_input("Slots (Z)", min_value=12, max_value=144, value=48)
        with col2:
            poles = st.number_input("Poles", min_value=2, max_value=16, step=2, value=4)
        with col3:
            winding_type = st.selectbox("Type", ["Grouped (Custom)", "Lap (Single Layer)", "Lap (Double Layer)", "Wave (Sequential)"])
        with col4:
            q_val = st.number_input("q/Grp", min_value=1, max_value=12, value=6)
        with col5:
            pitch_type = st.selectbox("Pitch Style", ["Full Pitch (خطوة كاملة)", "Fractional Pitch (خطوة كسرية)"])

        engine = AdvancedMotorWindingEngine(slots=slots, poles=poles, phases=3, winding_type=winding_type, pitch_type=pitch_type, q_val=q_val)
        params = engine.calculate_advanced_parameters()
        
        st.subheader("📊 النتائج الحسابية وخصائص اللف:")
        st.json(params)
        
        st.subheader("🎨 المخطط الهندسي التنفيذي للملفات، المجاري وأطراف الأقطاب (Winding Blueprint):")
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
