from datetime import datetime
import streamlit as st

st.set_page_config(
    page_title="Industrial Generator Monitor", layout="wide"
)

# قائمة الأكواد الشهرية المعتمدة وتاريخ انتهاء صلاحيتها (YYYY-MM-DD)
VALID_MONTHLY_CODES = {
    "OCT-2026-X89": "2026-10-31",  # كود ينتهي بنهاية أكتوبر 2026
    "NOV-2026-A12": "2026-11-30",  # كود ينتهي بنهاية نوفمبر 2026
    "ADDOMA-PRO-1M": "2026-09-30",  # اشتراك شهري ينتهي في 30 سبتمبر 2026
}

st.sidebar.header("🔐 إدارة الاشتراك الشهري")
user_code = st.sidebar.text_input(
    "أدخل كود الاشتراك الشهري:", type="password"
)

is_pro = False

if user_code in VALID_MONTHLY_CODES:
    expiry_date_str = VALID_MONTHLY_CODES[user_code]
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    today = datetime.now().date()

    if today <= expiry_date:
        is_pro = True
        days_left = (expiry_date - today).days
        st.sidebar.success(
            f"✅ الاشتراك فعال! متبقي {days_left} يومًا (ينتهي في {expiry_date_str})."
        )
    else:
        st.sidebar.error(
            f"❌ انتهت صلاحية هذا الكود بتاريخ {expiry_date_str}. يرجى التجديد للشهر الجديد."
        )
elif user_code != "":
    st.sidebar.error("❌ كود الاشتراك غير صحيح.")
else:
    st.sidebar.info("💡 أدخل كود الاشتراك الشهري لفتح الخصائص التنبؤية.")
