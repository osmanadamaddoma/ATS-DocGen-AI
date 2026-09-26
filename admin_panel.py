import streamlit as st
import sqlite3
import uuid
from datetime import datetime, timedelta
import pandas as pd

# دالة لإنشاء قاعدة البيانات والجدول إذا لم يكونا موجودين
def init_db():
    conn = sqlite3.connect('subscribers.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS codes
                 (code TEXT PRIMARY KEY, duration TEXT, expiry_date TIMESTAMP, status TEXT)''')
    conn.commit()
    conn.close()

# دالة لتوليد كود عشوائي قصير
def generate_random_code():
    return str(uuid.uuid4())[:8].upper()

st.title("لوحة تحكم الإدارة - إصدار أكواد المشتركين ⚙️")

# التأكد من وجود قاعدة البيانات
init_db()

# قسم إصدار الأكواد
st.subheader("إصدار كود جديد")
duration_options = {
    "يوم واحد": 1,
    "شهر واحد": 30,
    "6 أشهر": 180,
    "سنة واحدة": 365
}

selected_duration = st.selectbox("اختر مدة الصلاحية", list(duration_options.keys()))

if st.button("توليد وحفظ الكود"):
    new_code = generate_random_code()
    days = duration_options[selected_duration]
    expiry_date = datetime.now() + timedelta(days=days)
    
    # حفظ الكود في قاعدة البيانات
    conn = sqlite3.connect('subscribers.db')
    c = conn.cursor()
    c.execute("INSERT INTO codes (code, duration, expiry_date, status) VALUES (?, ?, ?, ?)",
              (new_code, selected_duration, expiry_date, "Active"))
    conn.commit()
    conn.close()
    
    st.success(f"تم إصدار الكود بنجاح: {new_code}")
    st.info(f"صالح حتى: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}")

# قسم عرض الأكواد المصدرة
st.divider()
st.subheader("الأكواد الفعالة والسابقة")
conn = sqlite3.connect('subscribers.db')
df = pd.read_sql_query("SELECT * FROM codes", conn)
conn.close()

if not df.empty:
    st.dataframe(df)
else:
    st.write("لا توجد أكواد مصدرة بعد.")
