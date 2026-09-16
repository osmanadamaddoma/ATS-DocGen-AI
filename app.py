import streamlit as st
import pandas as pd
import time
import datetime
import re

# إعداد الصفحة
st.set_page_config(
    page_title="نظام الصيانة التنبؤية وإدارة الاشتراكات",
    layout="wide"
)

# ------------------------------------------
# 1. التخزين المؤقت (@st.cache_data) للدوال الثقيلة
# ------------------------------------------

@st.cache_data
def load_maintenance_schedule():
    """تحميل جدول الصيانة لـ 14 وحدة مع المدة الافتراضية"""
    data = {
        "الرقم": list(range(1, 15)),
        "الوحدة / الجزء": [
            "زيت المحرك (Engine Oil)", 
            "فلاتر الزيت (Oil Filters)", 
            "فلاتر الوقود (Fuel Filters)", 
            "فلاتر الهواء (Air Filters)", 
            "سائل التبريد والراديتر (Coolant System)", 
            "البطاريات وشاحن البطارية (Batteries)", 
            "السيور (Drive Belts)", 
            "طلمبة حقن الوقود (Fuel Injectors)", 
            "الشاحن التوربيني (Turbocharger)", 
            "المولد الأساسي (Alternator Winding)", 
            "لوحات التحكم (Control Panels)", 
            "الحساسات والمستشعرات (Sensors)", 
            "نظام العادم (Exhaust System)", 
            "خلوص الصمامات (Valve Clearance)"
        ],
        "المدة الافتراضية (ساعات التشغيل / الزمن)": [
            "250 ساعة / 6 أشهر",
            "250 ساعة / 6 أشهر",
            "500 ساعة / 12 شهر",
            "500 ساعة / 12 شهر",
            "1000 ساعة / سنتان",
            "فحص شهري / استبدال كل سنتين",
            "500 ساعة / 12 شهر",
            "1500 ساعة",
            "2000 ساعة",
            "فحص وعزل كل 1000 ساعة",
            "فحص وبرمجة كل 6 أشهر",
            "فحص ومعايرة كل 6 أشهر",
            "1000 ساعة / فحص تسريب",
            "1000 ساعة / سنة واحدة"
        ],
        "حالة الصيانة": ["جيد"] * 14
    }
    return pd.DataFrame(data)

@st.cache_data
def process_heavy_files(file_name):
    """محاكاة لمعالجة الصور أو الملفات المعقدة لتجنب إعادة التحميل"""
    time.sleep(1)
    return f"تمت معالجة الملف '{file_name}' بنجاح."

def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"

# ==========================================
# واجهة المستخدم الرئيسية
# ==========================================

st.title("⚙️ نظام الصيانة التنبؤية وإدارة الاشتراكات")
st.markdown("---")

# تقسيم الشاشة إلى تبويبات
tab1, tab2, tab3, tab4 = st.tabs([
    "📅 جدول الصيانة (14 وحدة)", 
    "📂 رفع الصور والكتالوجات", 
    "📊 التوليد عند الطلب (PDF/رسوم)", 
    "🔐 إدارة الاشتراكات"
])

# ------------------------------------------
# التبويب الأول: جدول الصيانة التنبؤية
# ------------------------------------------
with tab1:
    st.header("جدول الصيانة التنبؤية للمعدات")
    st.info("هذا الجدول يستخدم `@st.cache_data` ليتم تحميله مرة واحدة فقط لتخفيف العبء على المعالج.")
    
    df_schedule = load_maintenance_schedule()
    
    edited_df = st.data_editor(
        df_schedule,
        use_container_width=True,
        hide_index=True,
        column_config={
            "حالة الصيانة": st.column_config.SelectboxColumn(
                "حالة الصيانة",
                options=["جيد", "يحتاج صيانة", "عاجل"],
                required=True
            )
        }
    )

# ------------------------------------------
# التبويب الثاني: رفع الصور والكتالوجات
# ------------------------------------------
with tab2:
    st.header("رفع المرفقات (صور وكتالوجات)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("رفع الصور (أجزاء المعدات)")
        image_file = st.file_uploader("اختر صورة (JPG, PNG)", type=["jpg", "png", "jpeg"], key="img_up")
        if image_file:
            st.image(image_file, caption="معاينة الصورة", use_column_width=True)
            with st.spinner("جاري المعالجة..."):
                result = process_heavy_files(image_file.name)
                st.success(result)

    with col2:
        st.subheader("رفع الكتالوجات (PDF)")
        pdf_file = st.file_uploader("اختر ملف كتالوج (PDF)", type=["pdf"], key="pdf_up")
        if pdf_file:
            st.write(f"📄 **اسم الملف:** {pdf_file.name}")
            with st.spinner("جاري تحليل الكتالوج..."):
                result = process_heavy_files(pdf_file.name)
                st.success(result)

# ------------------------------------------
# التبويب الثالث: التوليد عند الطلب (On-Demand)
# ------------------------------------------
with tab3:
    st.header("توليد التقارير والرسوم البيانية")
    st.warning("لا يتم توليد أي تقارير أو رسوم البيانية إلا عند الضغط على الأزرار أدناه للحفاظ على أداء التطبيق.")
    
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("📊 توليد الرسم البياني لحالة المعدات", use_container_width=True):
            st.subheader("الرسم البياني لحالة الصيانة")
            status_counts = edited_df["حالة الصيانة"].value_counts()
            st.bar_chart(status_counts)
            st.success("تم توليد الرسم البياني بنجاح!")

    with col_btn2:
        if st.button("📥 توليد تقرير PDF", use_container_width=True):
            with st.spinner("جاري إنشاء ملف PDF..."):
                time.sleep(1)
                st.success("تم توليد ملف PDF بنجاح!")
                st.download_button(
                    label="تحميل التقرير",
                    data="PDF Content Placeholder",
                    file_name="maintenance_report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

# ------------------------------------------
# التبويب الرابع: نظام الاشتراكات
# ------------------------------------------
with tab4:
    st.header("إدارة باقات الاشتراكات للعملاء")
    
    if "subscribers" not in st.session_state:
        st.session_state.subscribers = []

    with st.expander("➕ إضافة طلب اشتراك جديد", expanded=True):
        with st.form("subscription_form"):
            sub_name = st.text_input("اسم المشترك / الشركة")
            sub_type = st.selectbox("نوع الباقة", ["أيام", "شهور", "سنة"])
            
            if sub_type == "أيام":
                duration = st.number_input("عدد الأيام", min_value=1, max_value=30, value=7)
            elif sub_type == "شهور":
                duration = st.number_input("عدد الشهور", min_value=1, max_value=11, value=1)
            else:
                duration = st.number_input("عدد السنوات", min_value=1, max_value=5, value=1)
            
            sub_notes = st.text_area("ملاحظات الطلب (طلبات منفردة)")
            submit_sub = st.form_submit_button("تفعيل الاشتراك")
            
            if submit_sub and sub_name:
                start_date = datetime.date.today()
                if sub_type == "أيام":
                    end_date = start_date + datetime.timedelta(days=duration)
                elif sub_type == "شهور":
                    end_date = start_date + datetime.timedelta(days=duration * 30)
                else:
                    end_date = start_date + datetime.timedelta(days=duration * 365)

                st.session_state.subscribers.append({
                    "الاسم": sub_name,
                    "الباقة": f"{duration} {sub_type}",
                    "تاريخ البدء": start_date.strftime("%Y-%m-%d"),
                    "تاريخ الانتهاء": end_date.strftime("%Y-%m-%d"),
                    "ملاحظات": sub_notes
                })
                st.success(f"تم تفعيل اشتراك '{sub_name}' بنجاح!")

    st.subheader("📋 قائمة طلبات المشتركين الحالية")
    if st.session_state.subscribers:
        df_subs = pd.DataFrame(st.session_state.subscribers)
        st.dataframe(df_subs, use_container_width=True)
    else:
        st.info("لا توجد اشتراكات مفعلة حالياً.")
