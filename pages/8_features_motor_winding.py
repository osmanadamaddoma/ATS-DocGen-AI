import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import math

# ==========================================
# 1. محرك Winding CAD Pro الهندسي المتقدم (مع دعم تباين خطوات الأقطاب)
# ==========================================
class WindingCADProEngine:
    def __init__(self, Z, poles, winding_type, Y_base, q_val, style, pole_step_variation):
        self.Z = Z                              # عدد المجاري (Slots)
        self.poles = poles                      # عدد الأقطاب (Poles)
        self.winding_type = winding_type        # نوع اللف
        self.Y_base = Y_base                    # الخطوة الأساسية (Base Step Y)
        self.q_val = q_val                      # عدد الملفات لكل مجموعة (q/Grp)
        self.style = style                      # نمط اللف
        self.pole_step_variation = pole_step_variation # تباين الخطوات بين الأقطاب

    def get_phase_color(self, slot_idx):
        p_pairs = self.poles / 2
        alpha_e = p_pairs * 360.0 / self.Z
        theta_e = (slot_idx * alpha_e) % 360.0
        if 0 <= theta_e < 60 or 180 <= theta_e < 240:
            return '#d63031'       # أحمر (U)
        elif 60 <= theta_e < 120 or 240 <= theta_e < 300:
            return '#0984e3'       # أزرق (W)
        else:
            return '#00b894'       # أخضر (V)

    def get_connections_and_leads(self):
        connections = []
        leads = []
        
        if "Grouped" in self.winding_type:
            groups_per_phase = self.poles
            phase_names = ['U', 'V', 'W']
            phase_colors = ['#d63031', '#00b894', '#0984e3']
            
            for phase_idx, color in enumerate(phase_colors):
                phase_start_slot = int(round((self.Z / 3.0) * phase_idx))
                p_name = phase_names[phase_idx]
                
                for p in range(groups_per_phase):
                    group_start = (phase_start_slot + p * int(round(self.Z / self.poles))) % self.Z
                    
                    # تطبيق خطوة مخصصة ومتغيرة لكل قطب بناءً على خيار المستخدم
                    current_Y = self.Y_base + (p * self.pole_step_variation)
                    
                    if "Concentric" in self.style:
                        lead_s = (group_start - (self.q_val - 1)) % self.Z
                        lead_e = (group_start + current_Y + (self.q_val - 1)) % self.Z
                    else:
                        lead_s = group_start % self.Z
                        lead_e = (group_start + (self.q_val - 1) + current_Y) % self.Z
                        
                    leads.append({'slot': lead_s, 'label': f"{p_name}s{p+1}", 'color': color, 'is_start': True, 'pole': p+1})
                    leads.append({'slot': lead_e, 'label': f"{p_name}e{p+1}", 'color': color, 'is_start': False, 'pole': p+1})
                    
                    for i in range(self.q_val):
                        if "Concentric" in self.style:
                            s1 = (group_start - i) % self.Z
                            s2 = (group_start + current_Y + i) % self.Z
                        else:
                            s1 = (group_start + i) % self.Z
                            s2 = (s1 + current_Y) % self.Z
                            
                        connections.append((s1, s2, color, i, p))
        else:
            for i in range(self.Z):
                color = self.get_phase_color(i)
                next_idx = (i + self.Y_base) % self.Z
                is_double = "Double" in self.winding_type
                connections.append((i, next_idx, color, 0, 0))
                if i % int(max(1, self.Z/12)) == 0:
                    leads.append({'slot': i, 'label': f"L_{i+1}", 'color': color, 'is_start': True, 'pole': 1})
                    
        return connections, leads

    def generate_matplotlib_diagram(self):
        """توليد الرسم الهندسي الدائري بأقواس متباعدة وفصل كامل للأقطاب"""
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.set_aspect('equal')
        ax.axis('off')
        
        R = 3.5
        r_inner = R * 0.70
        r_outer = R
        r_text = R * 0.52
        
        # رسم حلقات الستاتور الأساسية
        ax.add_patch(plt.Circle((0, 0), r_outer, color='#2d3436', fill=False, linewidth=2.5))
        ax.add_patch(plt.Circle((0, 0), r_inner, color='#2d3436', fill=False, linewidth=1.5))
        
        slot_positions = []
        for i in range(self.Z):
            angle_rad = math.radians((i * 360.0 / self.Z) - 90)
            x1 = r_inner * math.cos(angle_rad)
            y1 = r_inner * math.sin(angle_rad)
            x2 = r_outer * math.cos(angle_rad)
            y2 = r_outer * math.sin(angle_rad)
            
            slot_positions.append((x2, y2, angle_rad))
            ax.plot([x1, x2], [y1, y2], color='#b2bec3', linewidth=1.2)
            
            xt = r_text * math.cos(angle_rad)
            yt = r_text * math.sin(angle_rad)
            font_sz = 6 if self.Z > 36 else 8
            ax.text(xt, yt, str(i + 1), fontsize=font_sz, ha='center', va='center', fontweight='bold', color='black')

        connections, leads = self.get_connections_and_leads()

        # رسم الأقواس المنحنية مع تباعد هندسي واسع لكل قطب لمنع التداخل
        for s1, s2, color, coil_idx, pole_idx in connections:
            x_start, y_start, ang_start = slot_positions[s1]
            x_end, y_end, ang_end = slot_positions[s2]
            
            diff = (ang_end - ang_start) % (2 * math.pi)
            if diff > math.pi: diff -= 2 * math.pi
            if diff < -math.pi: diff += 2 * math.pi
            mid_angle = ang_start + diff / 2.0
            
            r_apex = r_outer + 0.45 + (coil_idx * 0.16) + (pole_idx * 0.35)
            
            theta_curve = np.linspace(ang_start, ang_end, 40)
            if abs(ang_start - ang_end) > math.pi:
                theta_curve = np.linspace(ang_start, ang_end + 2*math.pi if ang_end < ang_start else ang_end - 2*math.pi, 40)
            
            r_curve = np.linspace(r_outer, r_apex, 20).tolist() + np.linspace(r_apex, r_outer, 20).tolist()
            if len(r_curve) == 40:
                curve_x = r_curve * np.cos(theta_curve)
                curve_y = r_curve * np.sin(theta_curve)
                ax.plot(curve_x, curve_y, color=color, linewidth=1.3, alpha=0.9)

        # رسم الأطراف والبدايات والنهايات في نطاق واسع للخارج
        if leads:
            slot_counts = {}
            for lead in leads:
                s_idx = lead['slot']
                slot_counts[s_idx] = slot_counts.get(s_idx, 0) + 1

            slot_current_index = {}
            for lead in leads:
                s_idx = lead['slot']
                angle_rad = math.radians((s_idx * 360.0 / self.Z) - 90)
                
                if slot_counts[s_idx] > 1:
                    idx_occ = slot_current_index.get(s_idx, 0)
                    slot_current_index[s_idx] = idx_occ + 1
                    angle_rad += (-0.035 if idx_occ == 0 else 0.035)
                
                x_start_lead = r_outer * math.cos(angle_rad)
                y_start_lead = r_outer * math.sin(angle_rad)
                
                lead_length = 2.2
                x_end_lead = (r_outer + lead_length) * math.cos(angle_rad)
                y_end_lead = (r_outer + lead_length) * math.sin(angle_rad)
                
                color = lead['color']
                label = lead['label']
                is_start = lead['is_start']
                
                style_line = (0, (2, 2)) if not is_start else '-'
                ax.plot([x_start_lead, x_end_lead], [y_start_lead, y_end_lead], color=color, linewidth=1.3, linestyle=style_line)
                
                marker_face = color if is_start else 'black'
                ax.scatter(x_end_lead, y_end_lead, c=marker_face, edgecolors=color, s=35, zorder=5)
                
                text_radius = r_outer + lead_length + 0.35
                x_text = text_radius * math.cos(angle_rad)
                y_text = text_radius * math.sin(angle_rad)
                
                text_color = color if is_start else "#2d3436"
                ax.text(x_text, y_text, label, color=text_color, fontsize=8, fontweight='bold', ha='center', va='center')

        ax.set_xlim(-8.5, 8.5)
        ax.set_ylim(-8.5, 8.5)
        ax.set_title("Winding CAD Pro - Variable Pole Steps Blueprint", fontsize=12, fontweight='bold', pad=20, color='#2c3e50')
        return fig

# ==========================================
# 2. وحدة التزامن للمولدات (Generator Sync Engine)
# ==========================================
class GeneratorSyncEngine:
    def __init__(self, v1, v2, f1, f2, angle):
        self.v1 = v1
        self.v2 = v2
        self.f1 = f1
        self.f2 = f2
        self.d_theta = angle

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
        "1. حسابات وخرائط لف المحركات المتقدمة (Winding CAD Pro)",
        "2. وحدة التزامن والمزامنة للمولدات (Sync)",
        "3. إدارة وتوسيع أقسام الصيانة التنبؤية"
    ])

    if app_mode == "1. حسابات وخرائط لف المحركات المتقدمة (Winding CAD Pro)":
        st.header("⚡ محاكي Winding CAD Pro الهندسي المتقدم لف المحركات")
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            Z = st.number_input("Slots (Z)", min_value=12, max_value=144, value=72)
        with col2:
            poles = st.number_input("Poles", min_value=2, max_value=16, step=2, value=4)
        with col3:
            winding_type = st.selectbox("Type", ["Grouped (Custom)", "Lap (Single Layer)", "Lap (Double Layer)", "Wave (Sequential)"])
        with col4:
            q_val = st.number_input("q/Grp", min_value=1, max_value=12, value=6)
        with col5:
            Y = st.number_input("Base Step (Y)", min_value=1, max_value=36, value=13)
        with col6:
            pole_step_var = st.number_input("Pole Step Var", min_value=0, max_value=5, value=0, help="تدرج خطوة الملفات من قطب لآخر")

        style = st.selectbox("Style", ["Concentric (+2 Step)", "Equal Pitch"])

        engine = WindingCADProEngine(Z=Z, poles=poles, winding_type=winding_type, Y_base=Y, q_val=q_val, style=style, pole_step_variation=pole_step_var)
        
        p_pairs = poles / 2
        alpha_e = (p_pairs * 360.0) / Z
        
        st.subheader("📊 النتائج الحسابية وخصائص اللف:")
        st.json({
            "Total Stator Slots (Z)": Z,
            "Number of Poles": poles,
            "Slots per Pole (q_total)": round(Z / poles, 2),
            "Electrical Angle (αe)": round(alpha_e, 2),
            "Base Step (Y)": Y,
            "Pole Step Variation": pole_step_var,
            "Winding Style": winding_type,
            "Sub-Style": style
        })
        
        st.subheader("🎨 المخطط الهندسي التنفيذي بمتغير خطوات الأقطاب:")
        fig = engine.generate_matplotlib_diagram()
        st.pyplot(fig)
        plt.close(fig)

    elif app_mode == "2. وحدة التزامن والمزامنة للمولدات (Sync)":
        st.header("🔄 نظام المزامنة والربط المتوازي للمولدات (Parallel Generators)")
        col1, col2 = st.columns(2)
        with col1:
            v1 = st.number_input("جهد المصدر الأول (V)", value=400.0)
            f1 = st.number_input("تردد المصدر الأول (Hz)", value=50.0)
        with col2:
            v2 = st.number_input("جهد المولد الداخل (V)", value=401.0)
            f2 = st.number_input("تردد المولد الداخل (Hz)", value=50.0)
            angle = st.slider("فرق الزاوية (Phase Angle 𝚫θ)", -30.0, 30.0, 1.5)

        sync_engine = GeneratorSyncEngine(v1, v2, f1, f2, angle)
        sync_results = sync_engine.evaluate_synchronization()
        
        if "SAFE" in sync_results["Synchronization Status"]:
            st.success(f"حالة المزامنة: {sync_results['Synchronization Status']}")
        else:
            st.error(f"حالة المزامنة: {sync_results['Synchronization Status']}")
        st.json(sync_results)

    elif app_mode == "3. إدارة وتوسيع أقسام الصيانة التنبؤية":
        st.header("🧩 إدارة وتوسيع الأقسام البرمجية للمجمع الصناعي")
        st.info("منصة معيارية مجهزة لربط خوارزميات الذكاء الاصطناعي، بيانات الاهتزازات، وتحليل أداء محركات الديزل ومولدات CAT وCummins.")

if __name__ == "__main__":
    main()
