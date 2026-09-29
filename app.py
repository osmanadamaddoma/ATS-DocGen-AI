import os
import uuid
from datetime import datetime, timedelta
import math

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx
from google import genai

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة المتغيرات
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)

if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الخرطوم (القائمة الرئيسية)": {
            "الموقع الرئيسي - كافوري (موقع فرعي)": {
                "address": "الخرطوم - المنطقة الصناعية - كافوري",
                "generators": {
                    "G1": {
                        "model": "Perkins 410 kVA",
                        "run_hours": 700.0,
                        "target": 940.0,
                        "kw": 410.0,
                        "load": 250.0,
                        "calib_elec": {
                            "v_nominal": 400.0, "v_measured": 398.0,
                            "freq_nominal": 50.0, "freq_measured": 50.1,
                            "current_max": 600.0, "current_measured": 360.0,
                            "pf": 0.85, "ct_ratio": "600/5"
                        },
                        "calib_engine": {
                            "oil_press_bar": 4.5, "coolant_temp_c": 85.0,
                            "rpm": 1500.0, "battery_v": 26.5,
                            "ambient_temp": 43.0
                        }
                    }
                }
            }
        }
    }

if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "الخرطوم - كافوري",
            "generator": "G1",
            "technician": "أحمد فني الصيانة",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "status": "طبيعي"
        }
    ]

# =========================================================
# 1. إدارة قاعدة بيانات أسرار المشتركين (تم تعديل الصلاحية)
# =========================================================
if "clients_db" not in st.session_state:
    st.session_state.clients_db = {
        "ADDOMA-MASTER-2026": {
            "name": "إدارة الدومة للخدمات التجارية",
            "plan": "التحكم الشامل (Admin)",
            "start_date": "2026-01-01",
            "duration_days": 36500,
            "role": "admin"
        },
        "ADDOMA-2026-PRO": {
            "name": "عثمان آدم أدومة (Addoma Trading Services)",
            "plan": "شهري (Monthly)",
            "start_date": "2026-09-15",
            "duration_days": 30,
            "role": "admin"  # تم التعديل إلى admin لتتمكن من رؤية لوحة التحكم بالمشتركين
        }
    }

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()
saved_code = cookie_manager.get(cookie="activation_code")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if saved_code and not st.session_state.authenticated:
    if saved_code in st.session_state.clients_db:
        st.session_state.authenticated = True
        st.session_state.active_code = saved_code

# --- بوابة التفعيل ---
if not st.session_state.authenticated:
    st.title("🔐 بوابة تفعيل النظام الموحد")
    user_code = st.sidebar.text_input("كود التفعيل / Activation Code:", type="password")
    
    if st.sidebar.button("تفعيل / Activate"):
        if user_code in st.session_state.clients_db:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code
            expires_at = datetime.now() + timedelta(days=30)
            cookie_manager.set("activation_code", user_code, expires_at=expires_at)
            st.rerun()
        else:
            st.sidebar.error("❌ كود التفعيل غير صحيح.")
    st.warning("🔒 أدخل الكود الخاص بك (مثال: ADDOMA-2026-PRO).")
    st.stop()

input_code = st.session_state.get("active_code", "")
is_admin = False
if input_code in st.session_state.clients_db:
    data = st.session_state.clients_db[input_code]
    is_admin = data.get("role", "client") == "admin"
    st.sidebar.success(f"✅ تم التفعيل للعميل: {data['name']}")

# --- القائمة الجانبية ---
with st.sidebar:
    st.header("⚙️ نظام الدومة للخدمات التجارية")
    st.write("---")
    
    if st.button("💬 المساعد الذكي الهندسي", use_container_width=True):
        st.session_state.current_page = "chat"
        
    if st.button("📊 لوحة تحكم الأنظمة", use_container_width=True):
        st.session_state.current_page = "dashboard"

    if st.button("🛠️ التطبيقات الهندسية الشاملة", use_container_width=True):
        st.session_state.current_page = "main_apps"
        
    st.write("---")
    
    # الزر الذي كان مخفياً عنك أصبح يظهر الآن بفضل الصلاحية الجديدة
    if is_admin:
        if st.button("🛡️ إدارة وتحرير أكواد المشتركين (Admin)", type="primary", use_container_width=True):
            st.session_state.current_page = "admin_panel"
        st.write("---")

    if st.button("🚪 تسجيل الخروج", use_container_width=True):
        st.session_state.authenticated = False
        cookie_manager.delete("activation_code")
        st.rerun()

st.sidebar.markdown("🛠️ **التطبيقات المتاحة (نسخة احترافية)**")
apps_list = [
    "⚙️ 1. الصيانة التنبؤية والمولدات",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد",
    "📊 3. المتابعة اليومية والتقارير",
    "🤖 4. المساعد الذكي والكتالوجات",
    "🔍 5. نظام فحص المعدات (WIC)",
    "🧮 6. الحاسبة الهندسية للكهرباء"
]
selected_app = st.sidebar.radio("اختر النظام المطلوب:", apps_list)

# =========================================================
# 2. لوحة الإدارة وتحرير المشتركين (Admin Panel)
# =========================================================
if st.session_state.current_page == "admin_panel" and is_admin:
    st.title("🛡️ إدارة وتحرير أكواد المشتركين")
    st.info("من هذه الشاشة يمكنك إضافة، تعديل، وحذف اشتراكات العملاء.")

    tab1, tab2, tab3 = st.tabs(["➕ إضافة كود", "✏️ تعديل كود", "📋 جميع المشتركين"])

    with tab1:
        c_name = st.text_input("اسم العميل / الشركة:")
        c_plan = st.selectbox("الباقة:", ["تجريبي (Trial)", "شهري (Monthly)", "سنوي (Yearly)", "دائم (Lifetime)"])
        c_days = st.number_input("المدة (أيام):", value=30, min_value=1)
        c_role = st.selectbox("الصلاحية:", ["client", "admin"])
        if st.button("🚀 إنشاء الكود", type="primary"):
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {
                "name": c_name.strip(),
                "plan": c_plan,
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "duration_days": c_days,
                "role": c_role
            }
            st.success(f"تم إنشاء الكود: {new_code}")

    with tab2:
        code_to_edit = st.selectbox("اختر الكود للتعديل:", list(st.session_state.clients_db.keys()))
        if code_to_edit:
            cur_data = st.session_state.clients_db[code_to_edit]
            e_name = st.text_input("الاسم:", value=cur_data.get("name", ""))
            e_days = st.number_input("الأيام:", value=int(cur_data.get("duration_days", 30)))
            c1, c2 = st.columns(2)
            if c1.button("💾 حفظ التعديلات", use_container_width=True):
                st.session_state.clients_db[code_to_edit]["name"] = e_name
                st.session_state.clients_db[code_to_edit]["duration_days"] = e_days
                st.success("تم الحفظ!")
                st.rerun()
            if c2.button("🗑️ حذف الكود", use_container_width=True):
                del st.session_state.clients_db[code_to_edit]
                st.warning("تم الحذف!")
                st.rerun()

    with tab3:
        df_clients = pd.DataFrame.from_dict(st.session_state.clients_db, orient='index').reset_index()
        st.dataframe(df_clients, use_container_width=True)

# =========================================================
# 3. التطبيقات الهندسية الرئيسية (Main Apps)
# =========================================================
elif st.session_state.current_page == "main_apps":
    if "1." in selected_app:
        st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات")
        
        main_sites = list(st.session_state.sites_data.keys())
        selected_main = st.selectbox("🌍 المنطقة الرئيسية:", main_sites) if main_sites else None
        
        if selected_main:
            sub_sites = list(st.session_state.sites_data[selected_main].keys())
            selected_sub = st.selectbox("📍 الموقع الفرعي:", sub_sites) if sub_sites else None
            
            if selected_sub:
                gens = st.session_state.sites_data[selected_main][selected_sub]["generators"]
                gen_selected = st.selectbox("⚙️ اختر المولد:", list(gens.keys()))
                
                # تم استبدال النافذة المنبثقة (Dialog) بموسع (Expander) لضمان العمل على جميع الإصدارات
                with st.expander("📝 فتح لوحة تعديل وتحديث قراءات المولد (بديلة للنافذة المنبثقة)", expanded=False):
                    g_data = gens[gen_selected]
                    with st.form("edit_gen_form"):
                        new_model = st.text_input("الطراز (Model)", value=g_data.get("model", ""))
                        new_kw = st.number_input("السعة (kW)", value=float(g_data.get("kw", 0.0)))
                        new_hours = st.number_input("ساعات التشغيل", value=float(g_data.get("run_hours", 0.0)))
                        new_v = st.number_input("الجهد المقاس (V)", value=float(g_data["calib_elec"]["v_measured"]))
                        new_oil = st.number_input("ضغط الزيت (Bar)", value=float(g_data["calib_engine"]["oil_press_bar"]))
                        
                        if st.form_submit_button("💾 حفظ البيانات", type="primary"):
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected].update({
                                "model": new_model, "kw": new_kw, "run_hours": new_hours
                            })
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected]["calib_elec"]["v_measured"] = new_v
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected]["calib_engine"]["oil_press_bar"] = new_oil
                            st.success("✅ تم حفظ القراءات بنجاح!")
                            st.rerun()

                st.subheader(f"بيانات ومعايرات المولد: {gen_selected}")
                st.json(gens[gen_selected])

    elif "2." in selected_app:
        st.title("🎛️ غرفة التحكم والتشغيل عن بُعد")
        st.success("اتصال SCADA نشط")
        st.button("▶️ تشغيل المولد عن بُعد (Start Gen)")
        st.button("⏹️ إيقاف المولد (Stop Gen)")

    elif "3." in selected_app:
        st.title("📊 المتابعة اليومية وتقارير الإدارة")
        st.dataframe(pd.DataFrame(st.session_state.daily_logs), use_container_width=True)

    elif "4." in selected_app:
        st.title("🤖 المساعد الذكي والكتالوجات")
        st.file_uploader("ارفع الكتالوج (PDF):", type=["pdf"])

    elif "5." in selected_app:
        st.title("🔍 نظام فحص المعدات (WIC 10 & 40)")
        st.checkbox("فحص درجة حرارة المحرك والمكثف")
        st.checkbox("اختبار لوحة Dixell")

    elif "6." in selected_app:
        st.title("🧮 الحاسبة الهندسية")
        c_i = st.number_input("التيار (A):", value=100.0)
        c_d = st.number_input("المسافة (m):", value=50.0)
        c_s = st.number_input("المقطع (mm²):", value=35.0)
        v_drop = round(((1.732 * c_i * c_d * 0.0178 * 0.85) / c_s), 2)
        st.success(f"هبوط الجهد المحسوب: {v_drop} فولت")

# =========================================================
# 4. الشاشات الأخرى
# =========================================================
elif st.session_state.current_page == "dashboard":
    st.title("📊 لوحة التحكم")
    st.info("نظام المراقبة يعمل.")
    
elif st.session_state.current_page == "chat":
    st.title("🤖 المساعد الهندسي")
    st.chat_input("اكتب استفسارك...")
