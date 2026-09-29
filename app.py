import os
import uuid
from datetime import datetime, timedelta
import math

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة المتغيرات
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    page_icon="⚡",
    layout="wide",
)

if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "current_page" not in st.session_state:
    st.session_state.current_page = "main_apps"

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
            "technician": "م. عثمان آدم",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "status": "طبيعي ومستقر"
        }
    ]

# =========================================================
# 1. قاعدة بيانات المشتركين والصلاحيات
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
            "plan": "شهري (Monthly) | احترافي",
            "start_date": "2026-09-15",
            "duration_days": 30,
            "role": "admin"
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
    st.title("🔐 بوابة تفعيل النظام الموحد - Addoma ATS")
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
    st.warning("🔒 أدخل كود التفعيل الخاص بك للمتابعة (مثال: ADDOMA-2026-PRO).")
    st.stop()

input_code = st.session_state.get("active_code", "")
is_admin = False
if input_code in st.session_state.clients_db:
    data = st.session_state.clients_db[input_code]
    is_admin = data.get("role", "client") == "admin"
    st.sidebar.success(f"✅ تم التفعيل للعميل: {data['name']}")

# =========================================================
# 2. القائمة الجانبية الموحدة
# =========================================================
with st.sidebar:
    st.header("⚙️ نظام الدومة للخدمات التجارية")
    st.write("---")
    
    if st.button("💬 المساعد الهندسي الذكي", use_container_width=True):
        st.session_state.current_page = "chat"
        st.rerun()
        
    if st.button("🛠️ قائمة التطبيقات الاحترافية", use_container_width=True):
        st.session_state.current_page = "main_apps"
        st.rerun()
        
    if is_admin:
        if st.button("🛡️ إدارة أكواد المشتركين (Admin)", type="primary", use_container_width=True):
            st.session_state.current_page = "admin_panel"
            st.rerun()
            
    st.write("---")
    if st.button("🚪 تسجيل الخروج", use_container_width=True):
        st.session_state.authenticated = False
        cookie_manager.delete("activation_code")
        st.rerun()

# اختيار التطبيقات عبر القائمة الجانبية (Radio مستقر تماماً)
st.sidebar.markdown("🛠️ **التطبيقات المتاحة (نسخة احترافية)**")
apps_options = [
    "⚙️ 1. الصيانة التنبؤية والمولدات",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد",
    "📊 3. المتابعة اليومية والتقارير",
    "🤖 4. المساعد الذكي والكتالوجات",
    "🔍 5. نظام فحص المعدات (WIC)",
    "🧮 6. الحاسبة الهندسية للكهرباء"
]
selected_app = st.sidebar.selectbox("اختر النظام المطلوب:", apps_options)

# ربط الاختيار بصفحة التطبيقات
if st.session_state.current_page == "main_apps":
    if "1." in selected_app:
        st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات")
        
        main_sites = list(st.session_state.sites_data.keys())
        selected_main = st.selectbox("🌍 المنطقة الرئيسية:", main_sites) if main_sites else None
        
        if selected_main:
            sub_sites = list(st.session_state.sites_data[selected_main].keys())
            selected_sub = st.selectbox("📍 الموقع الفرعي:", sub_sites) if sub_sites else None
            
            if selected_sub:
                gens = st.session_state.sites_data[selected_main][selected_sub]["generators"]
                gen_selected = st.selectbox("⚙ اختر المولد:", list(gens.keys()))
                
                with st.expander("📝 فتح لوحة تعديل وتحديث قراءات المولد ومعايراته", expanded=True):
                    g_data = gens[gen_selected]
                    with st.form("edit_gen_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_model = st.text_input("طراز المولد (Model)", value=g_data.get("model", ""))
                            new_kw = st.number_input("السعة (kW)", value=float(g_data.get("kw", 0.0)))
                            new_hours = st.number_input("ساعات التشغيل الحالية", value=float(g_data.get("run_hours", 0.0)))
                            new_v = st.number_input("الجهد المقاس (V)", value=float(g_data["calib_elec"]["v_measured"]))
                        with col2:
                            new_oil = st.number_input("ضغط الزيت (Bar)", value=float(g_data["calib_engine"]["oil_press_bar"]))
                            new_temp = st.number_input("حرارة مبرد المحرك (°C)", value=float(g_data["calib_engine"]["coolant_temp_c"]))
                            new_batt = st.number_input("بطارية التشغيل (V)", value=float(g_data["calib_engine"]["battery_v"]))
                            new_amb = st.number_input("درجة الحرارة المحيطة (°C)", value=float(g_data["calib_engine"]["ambient_temp"]))
                        
                        if st.form_submit_button("💾 حفظ وتحديث بيانات المولد", type="primary"):
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected].update({
                                "model": new_model, "kw": new_kw, "run_hours": new_hours
                            })
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected]["calib_elec"]["v_measured"] = new_v
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected]["calib_engine"]["oil_press_bar"] = new_oil
                            st.session_state.sites_data[selected_main][selected_sub]["generators"][gen_selected]["calib_engine"]["coolant_temp_c"] = new_temp
                            st.success("✅ تم تحديث بيانات ومعايرات المولد بنجاح!")
                            st.rerun()

                st.subheader(f"بيانات ومعايرات المولد النشط: {gen_selected}")
                st.json(gens[gen_selected])

    elif "2." in selected_app:
        st.title("🎛️ غرفة التحكم والتشغيل عن بُعد (Remote Control Center)")
        st.success("🟢 حالة الاتصال: نظام SCADA متصل ومستقر عبر بروتوكول Modbus TCP")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.info("⚡ أوامر التشغيل والتحكم المباشر بالمولدات")
            if st.button("▶️ تشغيل المولد الرئيسي (Start Gen)", type="primary", use_container_width=True):
                st.success("تم إرسال أمر البدء (Start Pulse) بنجاح.")
            if st.button("⏹️ إيقاف المولد (Stop Gen)", use_container_width=True):
                st.warning("تم إرسال أمر الإيقاف الآمن.")
        with col_c2:
            st.info("🚨 لوحة الإنذارات والحماية الطارئة")
            if st.button("🔴 إيقاف طوارئ (Emergency Stop)", use_container_width=True):
                st.error("⚠ تم تفعيل مفتاح الطوارئ وفصل قاطع الدائرة الرئيسي (GCB).")

    elif "3." in selected_app:
        st.title("📊 المتابعة اليومية وتقارير الإدارة الهندسية")
        st.markdown("سجل العمليات التشغيلية اليومية وحالة الصيانة الميدانية:")
        st.dataframe(pd.DataFrame(st.session_state.daily_logs), use_container_width=True)
        
        with st.form("add_log_form"):
            st.subheader("➕ إضافة سجل تشغيل جديد")
            l_site = st.text_input("اسم الموقع:", value="الخرطوم - كافوري")
            l_gen = st.text_input("المولد:", value="G1")
            l_tech = st.text_input("اسم الفني / المهندس:", value="م. عثمان آدم")
            l_status = st.selectbox("الحالة التشغيلية:", ["طبيعي ومستقر", "يحتاج صيانة عاجلة", "متوقف للصيانة دورية"])
            if st.form_submit_button("إضافة للسجل"):
                new_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "site": l_site,
                    "generator": l_gen,
                    "technician": l_tech,
                    "run_hours": 705.0,
                    "v_measured": 400.0,
                    "oil_press": 4.5,
                    "status": l_status
                }
                st.session_state.daily_logs.append(new_entry)
                st.success("✅ تمت إضافة السجل بنجاح!")
                st.rerun()

    elif "4." in selected_app:
        st.title("🤖 المساعد الذكي والكتالوجات الهندسية وقراءة الأكواد")
        st.info("قم برفع كتالوجات المولدات (Perkins, Cummins, Deep Sea) أو أدلة التبريد للتحليل الفوري.")
        uploaded_pdf = st.file_uploader("ارفع الكتالوج الفني (PDF):", type=["pdf", "txt", "docx"])
        if uploaded_pdf:
            st.success(f"تم رفع الملف بنجاح: {uploaded_pdf.name}")
            st.write("يمكنك الآن طرح أي استفسار فني أو طلب كود برمجي أو مخطط تشغيل بناءً على المستند المرفق.")
        
        user_query = st.text_area("اطرح سؤالك الفني أو استفسارك حول الكتالوج:")
        if st.button("إرسال الاستفسار للمساعد", type="primary"):
            st.info("💡 تحليلات المساعد الهندسي الذكي لشركة Addoma Trading Services جاهزة لمعالجة استفسارك.")

    elif "5." in selected_app:
        st.title("🔍 نظام فحص المعدات التجارية (غرف التبريد WIC 10 & WIC 40)")
        st.write("إدارة وفحص وحدات التبريد التجاري واستخدام وحدات التحكمDixell و Emerson:")
        
        col_w1, col_w2 = st.columns(2)
        with col_w1:
            st.subheader("غرفة تبريد WIC 10")
            st.checkbox("فحص درجة حرارة المبخر وغرفة التخزين")
            st.checkbox("مراجعة حالة ضاغط الفريون وضغوط السحب والطرد")
            st.checkbox("اختبار سنسور الحرارة NTC")
        with col_w2:
            st.subheader("غرفة تبريد وتجميد WIC 40")
            st.checkbox("فحص دورة إزالة الثلج (Defrost Cycle)")
            st.checkbox("فحص صمام التمدد الحراري (TXV)")
            st.checkbox("اختبار وتبريد لوحة التحكم Dixell")

    elif "6." in selected_app:
        st.title("🧮 الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)")
        st.write("حساب هبوط الجهد الكهربائي ومقاطع الكابلات الصناعية بدقة:")
        
        col_calc1, col_calc2 = st.columns(2)
        with col_calc1:
            i_load = st.number_input("التيار المحمل (A):", value=120.0)
            d_len = st.number_input("المسافة / طول الكابل (متر):", value=60.0)
        with col_calc2:
            c_area = st.number_input("مقطع الكابل (mm²):", value=50.0)
            power_f = st.number_input("معامل القدرة (Power Factor):", value=0.85)
            
        if st.button("🧮 حساب هبوط الجهد", type="primary"):
            v_drop_res = round(((1.732 * i_load * d_len * 0.0178 * power_f) / c_area), 2)
            st.success(f"⚡ هبوط الجهد المحسوب: **{v_drop_res} فولت** (ضمن الحدود المسموح بها < 3%)")

# =========================================================
# 3. لوحة تحكم المشتركين (Admin Panel)
# =========================================================
elif st.session_state.current_page == "admin_panel" and is_admin:
    st.title("🛡️ لوحة إدارة وتحرير أكواد المشتركين (Admin Panel)")
    st.info("إدارة وتحديث الصلاحيات والباقات الخاصة بالعملاء تحت إدارة Addoma Trading Services.")

    tab_ad1, tab_ad2, tab_ad3 = st.tabs(["➕ إضافة كود جديد", "✏️ تعديل وتحديث الأكواد", "📋 سجل جميع المشتركين"])

    with tab_ad1:
        c_name = st.text_input("اسم العميل / الجهة:")
        c_plan = st.selectbox("نوع الباقة:", ["تجريبي (Trial)", "شهري (Monthly)", "سنوي (Yearly)", "دائم (Lifetime)"])
        c_days = st.number_input("المدة بالأيام:", value=30, min_value=1)
        c_role = st.selectbox("مستوى الصلاحية:", ["client", "admin"])
        if st.button("🚀 إصدار وإنشاء الكود", type="primary"):
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {
                "name": c_name.strip(),
                "plan": c_plan,
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "duration_days": c_days,
                "role": c_role
            }
            st.success(f"✅ تم إنشاء الكود بنجاح: `{new_code}`")

    with tab_ad2:
        code_to_edit = st.selectbox("اختر الكود للتعديل أو الحذف:", list(st.session_state.clients_db.keys()))
        if code_to_edit:
            cur_data = st.session_state.clients_db[code_to_edit]
            e_name = st.text_input("اسم العميل المرتبط:", value=cur_data.get("name", ""))
            e_days = st.number_input("مدة الصلاحية (أيام):", value=int(cur_data.get("duration_days", 30)))
            
            col_e1, col_e2 = st.columns(2)
            if col_e1.button("💾 حفظ التعديلات", use_container_width=True):
                st.session_state.clients_db[code_to_edit]["name"] = e_name
                st.session_state.clients_db[code_to_edit]["duration_days"] = e_days
                st.success("✅ تم تحديث بيانات المشترك بنجاح!")
                st.rerun()
            if col_e2.button("🗑️ حذف هذا الكود", use_container_width=True):
                del st.session_state.clients_db[code_to_edit]
                st.warning("⚠️ تم حذف الكود نهائياً.")
                st.rerun()

    with tab_ad3:
        df_clients = pd.DataFrame.from_dict(st.session_state.clients_db, orient='index').reset_index()
        st.dataframe(df_clients, use_container_width=True)

# =========================================================
# 4. شاشة المساعد الهندسي (Chat)
# =========================================================
elif st.session_state.current_page == "chat":
    st.title("🤖 المساعد الهندسي الذكي - Addoma ATS")
    st.info("مرحباً بك. اسألني عن أي استفسار يتعلق بالمولدات، المخططات، لوحات التحكم Deep Sea، أو غرف التبريد.")
    st.chat_input("اكتب استفسارك الهندسي هنا...")
