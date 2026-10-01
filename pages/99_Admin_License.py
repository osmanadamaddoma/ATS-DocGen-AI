# -*- coding: utf-8 -*-
import streamlit as st
import json, os, uuid, pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Admin - Codes", page_icon="🔑", layout="wide")

# ---------------------------------------------------------
# 1. نفس سطر معلومات الاشتراك الموجود حاليا في app.py
# ---------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.get("authenticated", False):
    st.warning("يرجى تسجيل الدخول اولا من الصفحة الرئيسية")
    st.stop()

# ---------------------------------------------------------
# 2. قفل اضافي - يمنع اي مشترك من رؤية هذه الصفحة
# حتى بعد دخوله بكود مفعل - فقط انت
# ---------------------------------------------------------
ADMIN_CODES = ["ADDOMA-2026-PRO"]  # نفس الكود الموجود في app.py

active_code = st.session_state.get("active_code", "")

if active_code not in ADMIN_CODES:
    st.error("⛔ هذه الصفحة خاصة بالادمن فقط")
    st.warning("انت مشترك - لا يمكنك اصدار اكواد")
    st.stop()

# ---------------------------------------------------------
# 3. من هنا نافذة تفعيل اكواد المشتركين - تظهر لك انت فقط
# ---------------------------------------------------------
st.title("🔑 نافذة تفعيل اكواد المشتركين - للادمن فقط")
st.caption("تجريبي - شهري - سنوي | نفس قاعدة بيانات app.py")

# نفس قاعدة البيانات الموجودة في app.py
if "clients_db" not in st.session_state:
    st.session_state.clients_db = {}

# تحميل من Supabase مثل app.py
try:
    from supabase import create_client
    supabase_url = st.secrets.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY")
    supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None
except:
    supabase = None

@st.dialog("🔑 اصدار كود جديد")
def generate_modal():
    client_name = st.text_input("اسم العميل / الشركة:")
    plan_type = st.selectbox("نوع الباقة:", ["تجريبي 7 ايام", "تجريبي 14 يوم", "شهري 30 يوم", "سنوي 365 يوم"])
    days_map = {"تجريبي 7 ايام":7, "تجريبي 14 يوم":14, "شهري 30 يوم":30, "سنوي 365 يوم":365}

    if st.button("🚀 اصدار الكود", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            today = datetime.now().strftime("%Y-%m-%d")

            # حفظ في Session مثل app.py
            st.session_state.clients_db[new_code] = {
                "name": client_name.strip(),
                "plan": plan_type,
                "start_date": today,
                "duration_days": days_map[plan_type]
            }

            # حفظ دائم في Supabase مثل app.py
            if supabase:
                try:
                    supabase.table("subscriptions").insert({
                        "code": new_code,
                        "client_name": client_name.strip(),
                        "plan": plan_type,
                        "duration_days": days_map[plan_type],
                        "start_date": today
                    }).execute()
                    st.success("✅ تم الحفظ في Supabase")
                except Exception as e:
                    st.error(f"خطأ Supabase: {e}")

            st.success("✅ تم اصدار الكود")
            st.code(new_code)
        else:
            st.error("ادخل اسم العميل")

col1, col2 = st.columns([1,2])

with col1:
    if st.button("➕ اصدار كود جديد", type="primary", use_container_width=True):
        generate_modal()

    st.divider()
    st.write(f"**كودك الحالي:** {active_code}")
    st.write("**حالتك:** ادمن ✅")

with col2:
    st.subheader("سجل الاكواد - من Supabase")
    if supabase:
        try:
            res = supabase.table("subscriptions").select("*").order("start_date", desc=True).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                st.dataframe(df[["code","client_name","plan","start_date","duration_days"]], use_container_width=True, height=400)
            else:
                st.info("لا يوجد اكواد بعد")
        except Exception as e:
            st.error(f"خطأ تحميل: {e}")
    else:
        st.info("Supabase غير متصل - الاكواد في الذاكرة فقط")
        if st.session_state.clients_db:
            st.dataframe(pd.DataFrame.from_dict(st.session_state.clients_db, orient='index'), use_container_width=True)
