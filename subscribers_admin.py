import streamlit as st
import datetime

# إعداد إعدادات الصفحة
st.set_page_config(page_title="نظام إدارة الاشتراكات", layout="centered")

# 1. إنشاء النافذة المنبثقة (Pop-up) باستخدام @st.dialog
@st.dialog("إصدار اشتراك جديد")
def issue_subscription_dialog():
    st.write("الرجاء إدخال بيانات المشترك الجديد أدناه:")
    
    # حقول الإدخال
    client_name = st.text_input("اسم العميل")
    activation_code = st.text_input("كود التفعيل (أو السيريال)")
    
    # تحديد المدة الزمنية للاشتراك (بالأيام أو الأشهر حسب رغبتك)
    duration_days = st.number_input("المدة الزمنية للاشتراك (بالأيام)", min_value=1, value=30, step=1)
    
    # زر الحفظ داخل النافذة المنبثقة
    if st.button("تفعيل واستصدار الاشتراك"):
        if client_name and activation_code:
            # حساب تاريخ انتهاء الصلاحية بناءً على المدة المدخلة
            activation_date = datetime.date.today()
            expiry_date = activation_date + datetime.timedelta(days=duration_days)
            
            # حفظ البيانات في حالة الجلسة (أو يمكنك حفظها في قاعدة بيانات/ملف JSON)
            st.session_state.new_subscriber = {
                "Client Name": client_name,
                "Activation Code": activation_code,
                "Activation Date": str(activation_date),
                "Expiry Date": str(expiry_date),
                "Status": "Active"
            }
            
            st.success(f"تم تفعيل اشتراك العميل ({client_name}) بنجاح!")
            # إعادة تحميل الصفحة لتحديث البيانات وإغلاق النافذة
            st.rerun()
        else:
            st.error("⚠️ الرجاء تعبئة جميع الحقول المطلوبة (اسم العميل وكود التفعيل).")

# 2. الواجهة الرئيسية للوحة التحكم
st.title("لوحة تحكم المشتركين")
st.write("إدارة تفعيل أكواد العملاء وإصدار الاشتراكات.")

# زر لفتح النافذة المنبثقة
if st.button("➕ إضافة مشترك جديد (نافذة منبثقة)", type="primary"):
    issue_subscription_dialog()

st.divider()

# 3. عرض بيانات المشتركين الفعالة (لتأكيد العملية)
st.subheader("سجل أحدث الاشتراكات المُصدرة")

# التحقق من وجود بيانات تم إدخالها للتو وعرضها
if "new_subscriber" in st.session_state:
    st.json(st.session_state.new_subscriber)
else:
    st.info("لا توجد اشتراكات جديدة تم إصدارها في هذه الجلسة.")
