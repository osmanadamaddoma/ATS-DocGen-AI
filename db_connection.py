import streamlit as st
from supabase import create_client, Client

# استخدام cache_resource يضمن فتح اتصال واحد فقط وعدم استهلاك الموارد
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["supabase"]["SUPABASE_URL"]
    key = st.secrets["supabase"]["SUPABASE_KEY"]
    return create_client(url, key)
