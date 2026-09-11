from datetime import datetime
import streamlit as st

# 1. إعداد الصفحة
st.set_page_config(
    page_title="Industrial Generator Monitor & Client Subscriptions",
    layout="wide",
)

st.title("⚙️ نظام مراقبة وصيانة المولدات الصناعية - إدارة العملاء")

# 2. قاعدة بيانات العملاء وأكواد التفعيل (شهري أو سنوي مع اسم العميل)
CLIENTS_DATABASE = {
    "ADDOMA2026": {
        "client_name": "عثمان آدم (Addoma Trading Services)",
        "sub_type": "سنوي (Yearly Subscription)",
        "expiry_date": "2026-12-31",
    },
    "CLI-M-101": {
        "client_name": "شركة النيل للصناعات الهندسية",
        "sub_type": "شهري (Monthly Subscription)",
        "expiry_date": "2026-10-15",
    },
    "CLI-Y-202": {
        "client_name": "مصانع الحديد والصلب الوطنية",
        "sub_type": "سنوي (Yearly Subscription)",
        "expiry_date": "2027-06-30",
    },
}

# 3. الشريط الجانبي لإدخال كود التفعيل والتحقق من اسم العميل
st.sidebar.header("🔐 بوابة تفعيل حساب العملاء")

user_code = st.sidebar.text_input("أدخل كود التفعيل الخاص بالعميل:", type="password")

is_pro = False
current_client_name = "زیر (Visitor / Free)"
sub_info = "غير متصل"

if user_code in CLIENTS_DATABASE:
  client_data = CLIENTS_DATABASE[user_code]
  expiry_str = client_data["expiry_date"]
  expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
  today = datetime.now().date()

  if today <= expiry_date:
    is_pro = True
    current_client_name = client_data["client_name"]
    sub_type = client_data["sub_type"]
    days_left = (expiry_date - today).days

    st.sidebar.success(f"✅ تم التحقق بنجاح!")
    st.sidebar.markdown(f"**👤 اسم العميل:** {current_client_name}")
    st.sidebar.markdown(f"**📦 نوع الاشتراك:** {sub_type}")
    st.sidebar.markdown(
        f"⏳ **المتبقي لانتهاء الصلاحية:** {days_left} يوم (ينتهي في {expiry_str})"
    )
  else:
    st.sidebar.error(
        f"❌ انتهت صلاحية اشتراك هذا العميل بتاريخ ({expiry_str}). يرجى تجديد الاشتراك."
    )
elif user_code != "":
  st.sidebar.error(
      "❌ كود التفعيل غير صحيح. تأكد من الكود المخصص لاسم العميل."
  )
else:
  st.sidebar.info("💡 أدخل كود التفعيل لعرض بيانات العميل وفتح ميزات المراقبة.")

st.sidebar.divider()

# 4. نموذج إدخال القراءات التشغيلية للمولد
st.sidebar.header("📥 إدخال القراءات الحية")

with st.sidebar.form("generator_data_form"):
  st.subheader("المؤشرات الميكانيكية")
  temp = st.number_input(
      "درجة الحرارة Coolant Temp (°C)", min_value=0.0, max_value=150.0, value=85.0
  )
  oil_press = st.number_input(
      "ضغط الزيت Oil Pressure (Bar)", min_value=0.0, max_value=10.0, value=4.2
  )
  vibration = st.number_input(
      "مستوى الاهتزاز Vibration (mm/s)",
      min_value=0.0,
      max_value=50.0,
      value=2.2,
      disabled=not is_pro,
  )

  st.subheader("المؤشرات الكهربائية")
  voltage = st.number_input(
      "الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0
  )
  freq = st.number_input(
      "التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0
  )
  current = st.number_input(
      "التيار Amperes (A)", min_value=0.0, max_value=2000.0, value=300.0
  )
  pf = st.number_input(
      "معامل القدرة Power Factor (PF)",
      min_value=0.0,
      max_value=1.0,
      value=0.85,
      disabled=not is_pro,
  )

  submit_btn = st.form_submit_button("تحليـل القراءات")

# 5. عرض لوحة المؤشرات الرئيسية ومعلومات العميل النشط
st.subheader("📊 لوحة المراقبة التشغيلية للعميل")
st.info(f"🔹 **العميل الحالي المسجل بالجلسة:** {current_client_name}")

col1, col2, col3 = st.columns(3)
col1.metric("درجة الحرارة", f"{temp} °C", "حرج" if temp >= 95 else "طبيعي")
col2.metric("ضغط الزيت", f"{oil_press} Bar", "منخفض" if oil_press < 2.5 else "مستقر")
col3.metric(
    "مستوى الاهتزاز", f"{vibration} mm/s" if is_pro else "🔒 مقفل (يتطلب تفعيل)"
)

col4, col5, col6, col7 = st.columns(4)
col4.metric("الجهد", f"{voltage} V")
col5.metric("التردد", f"{freq} Hz")
col6.metric("التيار", f"{current} A")
col7.metric(
    "معامل القدرة (PF)", f"{pf}" if is_pro else "🔒 مقفل (يتطلب تفعيل)"
)

# 6. التنبؤ بالأعطال والتحليل الذكي للعميل
st.divider()
st.subheader("🔍 تقرير التنبؤ بالأعطال (AI Diagnostics)")

if is_pro:
  st.success(
      f"🌟 حساب العميل (**{current_client_name}**) مفعل بنجاح. يتم تحليل كافة"
      " المعلمات بدقة."
  )

  alerts = []
  if vibration > 4.0:
    alerts.append(
        "⚠️ **تحذير اهتزاز عالي:** يشير إلى عدم توازن في المحور أو تآكل كراسي"
        " المحرك."
    )
  if pf < 0.8:
    alerts.append(
        "💡 **معامل قدرة منخفض:** يوصى بمراجعة مكثفات تحسين القدرة (PFC)."
    )
  if temp >= 95:
    alerts.append("⚠️ **تحذير حرارة:** ارتفاع غير طبيعي في سائل التبريد.")
  if oil_press < 2.5:
    alerts.append("🚨 **خطر ضغط الزيت:** انخفاض ضغط الزيت عن 2.5 Bar.")

  if alerts:
    for alert in alerts:
      st.error(alert)
  else:
    st.success("✅ جميع الأنظمة تعمل ضمن الكفاءة القصوى والمثلى.")
else:
  if temp >= 95 or oil_press < 2.5:
    st.warning(
        "⚠️ تم رصد مؤشرات حرجة أساسية. يرجى إدخال كود العميل المخصص للحصول على"
        " تقرير التنبؤ الكامل."
    )
  else:
    st.info(
        "ℹ️ النظام يعمل في وضع الزائر. أدخل كود التفعيل الخاص بك في الشريط"
        " الجانبي لعرض اسم العميل وحالة الاشتراك (شهري/سنوي)."
    )
