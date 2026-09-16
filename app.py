from datetime import datetime, timedelta
import io
import json
import os
import re
import urllib.parse
import uuid

import firebase_admin
from firebase_admin import credentials, firestore
from fpdf import FPDF
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
import plotly.express as px
import requests
import streamlit as st

# ---------------------------------------------------------
# 0. إعدادات الصفحة
# ---------------------------------------------------------
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

# ---------------------------------------------------------
# 1. نظام إدارة الاشتراكات وأكواد التفعيل (أيام، أشهر، سنة)
# ---------------------------------------------------------
# سِجل كودات الاشتراكات الفردية وقاعدة طلبات المشتركين
ACTIVATION_CODES_REGISTRY = {
    # أكواد بالأيام (7 أيام)
    "ADDOMA-7D-DEMO": {"days": 7, "plan": "باقة تجريبية (7 أيام)"},
    # أكواد بالشهر (30 يوم)
    "ADDOMA-1M-SUB1": {"days": 30, "plan": "باقة شهرية (30 يوم)"},
    "ADDOMA-1M-SUB2": {"days": 30, "plan": "باقة شهرية (30 يوم)"},
    # أكواد 3 أشهر (90 يوم)
    "ADDOMA-3M-PRO": {"days": 90, "plan": "باقة ربع سنوية (90 يوم)"},
    # أكواد سنوية (365 يوم)
    "ADDOMA-1Y-VIP": {"days": 365, "plan": "باقة سنوية (365 يوم)"},
}

# ---------------------------------------------------------
# 2. الدوال المخبأة (Caching) لتقليل استهلاك المعالج (CPU)
# ---------------------------------------------------------


@st.cache_data(ttl=3600, show_spinner=False)
def search_engineering_resources_cached(query_text):
  """دالة البحث الهندسي مع تخزين مؤقت لمدة ساعة لتقليل طلبات الشبكة"""
  results = {"books": [], "web_articles": []}
  try:
    gbooks_url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(query_text)}&maxResults=3"
    resp = requests.get(gbooks_url, timeout=4)
    if resp.status_code == 200:
      data = resp.json()
      for item in data.get("items", []):
        volume_info = item.get("volumeInfo", {})
        results["books"].append({
            "title": volume_info.get("title", "بدون عنوان"),
            "link": volume_info.get("previewLink", "#"),
            "snippet": (
                volume_info.get("description", "لا يوجد وصف مختصر.")[:150]
                + "..."
            ),
        })
  except Exception:
    pass
  return results


@st.cache_data(show_spinner=False)
def process_maintenance_table_cached(base_parts_json, effective_hours):
  """دالة الحسابات المعقدة لجدول قطع الغيار وتحديد الحالة الفنية"""
  base_parts = json.loads(base_parts_json)
  processed_rows = []
  for row in base_parts:
    cat = row.get("تصنيف القطعة", "عام")
    part = row.get("قطع الغيار / الفلاتر", "قطعة")
    life = float(row.get("العمر الافتراضي (ساعة)", 250.0))
    used = float(row.get("الساعات المنقضية (ساعة)", 0.0))
    rem = life - used
    pct = (used / life) * 100 if life > 0 else 0
    status = "EXPIRED" if rem <= 0 else ("WARNING" if pct >= 80 else "GOOD")

    processed_rows.append({
        "تصنيف القطعة": cat,
        "قطع الغيار / الفلاتر": part,
        "العمر الافتراضي (ساعة)": life,
        "الساعات المنقضية (ساعة)": used,
        "المدة المتبقية (ساعة)": max(0.0, rem),
        "نسبة الاستهلاك": f"{pct:.0f}%",
        "الحالة الفنية": status,
    })
  return pd.DataFrame(processed_rows)


@st.cache_data(show_spinner=False)
def generate_chart_images_cached(df_json):
  """توليد صور الرسوم البيانية لملف PDF حصرياً عند الطلب مع التخزين المؤقت"""
  df = pd.read_json(df_json)

  # الرسم البياني الشريطي
  fig1, ax1 = plt.subplots(figsize=(6.5, 2.5))
  p_short = [
      re.sub(r"[^\x00-\x7F]+", "", str(x))[:12]
      for x in df["قطع الغيار / الفلاتر"]
  ]
  ax1.bar(
      p_short,
      df["الساعات المنقضية (ساعة)"].values,
      label="Used",
      color="#d9534f",
  )
  ax1.bar(
      p_short,
      df["المدة المتبقية (ساعة)"].values,
      bottom=df["الساعات المنقضية (ساعة)"].values,
      label="Remaining",
      color="#28a745",
  )
  ax1.set_title("Spare Parts Lifespan Overview", fontsize=9)
  plt.xticks(rotation=35, ha="right", fontsize=7)
  plt.tight_layout()

  buf_bar = io.BytesIO()
  plt.savefig(buf_bar, format="png", dpi=180)
  plt.close(fig1)
  buf_bar.seek(0)

  # الرسم البياني الدائري
  fig2, ax2 = plt.subplots(figsize=(5, 2.5))
  sc = df["الحالة الفنية"].value_counts()
  ax2.pie(
      sc.values,
      labels=[re.sub(r"[^\x00-\x7F]+", "", k) for k in sc.index],
      autopct="%1.1f%%",
      colors=["#28a745", "#ffc107", "#dc3545"],
  )
  ax2.set_title("Parts Readiness Distribution", fontsize=9)
  plt.tight_layout()

  buf_pie = io.BytesIO()
  plt.savefig(buf_pie, format="png", dpi=180)
  plt.close(fig2)
  buf_pie.seek(0)

  return buf_bar.getvalue(), buf_pie.getvalue()


# ---------------------------------------------------------
# 3. محرك تقارير PDF المعتمد
# ---------------------------------------------------------
def sanitize_latin_only(text):
  if not isinstance(text, str):
    text = str(text)
  clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
  return clean_text if clean_text else "N/A"


class ComprehensivePDF(FPDF):

  def header(self):
    self.set_font("Helvetica", "B", 13)
    self.cell(
        0, 8, "INDUSTRIAL MAINTENANCE & DIAGNOSTIC REPORT", ln=True, align="C"
    )
    self.set_font("Helvetica", "I", 8)
    self.cell(
        0,
        4,
        "Addoma Trading Services - Engineering Platform",
        ln=True,
        align="C",
    )
    self.line(10, 20, 200, 20)
    self.ln(5)

  def footer(self):
    self.set_y(-15)
    self.set_font("Helvetica", "I", 8)
    self.cell(
        0,
        10,
        f"Page {self.page_no()} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        align="C",
    )


def build_pdf_on_demand(
    gen_model, run_hours, future_run_hours, gen_kw, load_kw, load_pct, df_result
):
  """توليد ملف PDF بالكامل في الذاكرة عند الطلب فقط"""
  pdf = ComprehensivePDF()
  pdf.add_page()

  pdf.set_font("Helvetica", "B", 10)
  pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)}", ln=True)
  pdf.cell(
      0,
      5,
      f"Total Run Hours: {run_hours} hrs | Target Hours: {future_run_hours} hrs",
      ln=True,
  )
  pdf.cell(
      0,
      5,
      f"Capacity: {gen_kw} kW | Current Load: {load_kw} kW ({load_pct:.1f}%)",
      ln=True,
  )
  pdf.ln(3)

  # جدول قطع الغيار
  pdf.set_font("Helvetica", "B", 10)
  pdf.cell(0, 6, "Approved Spare Parts Maintenance Schedule:", ln=True)
  pdf.set_font("Helvetica", "B", 8)
  pdf.cell(45, 5, "Part Name", border=1)
  pdf.cell(25, 5, "Lifespan(h)", border=1)
  pdf.cell(25, 5, "Used(h)", border=1)
  pdf.cell(25, 5, "Remaining(h)", border=1)
  pdf.cell(35, 5, "Status", border=1)
  pdf.ln()

  pdf.set_font("Helvetica", "", 8)
  for idx, row in df_result.iterrows():
    pdf.cell(
        45,
        5,
        sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:22],
        border=1,
    )
    pdf.cell(25, 5, str(row["العمر الافتراضي (ساعة)"]), border=1)
    pdf.cell(25, 5, str(row["الساعات المنقضية (ساعة)"]), border=1)
    pdf.cell(25, 5, str(row["المدة المتبقية (ساعة)"]), border=1)
    pdf.cell(35, 5, sanitize_latin_only(str(row["الحالة الفنية"])), border=1)
    pdf.ln()

  # توليد الرسوم المخبأة وإضافتها
  try:
    bar_bytes, pie_bytes = generate_chart_images_cached(df_result.to_json())
    pdf.add_page()

    bar_path = f"temp_bar_{uuid.uuid4().hex}.png"
    pie_path = f"temp_pie_{uuid.uuid4().hex}.png"

    with open(bar_path, "wb") as f:
      f.write(bar_bytes)
    with open(pie_path, "wb") as f:
      f.write(pie_bytes)

    pdf.image(bar_path, x=15, y=20, w=170)
    pdf.image(pie_path, x=25, y=105, w=150)

    if os.path.exists(bar_path):
      os.remove(bar_path)
    if os.path.exists(pie_path):
      os.remove(pie_path)
  except Exception:
    pass

  return bytes(pdf.output())


# ---------------------------------------------------------
# 4. الاتصال بـ Firebase وتتبع المعرفات
# ---------------------------------------------------------
@st.cache_resource
def init_firebase():
  if not firebase_admin._apps:
    firebase_json_env = os.environ.get("FIREBASE_CREDENTIALS")
    if firebase_json_env:
      cred_dict = json.loads(firebase_json_env)
      cred = credentials.Certificate(cred_dict)
    elif "firebase" in st.secrets:
      firebase_dict = dict(st.secrets["firebase"])
      firebase_dict["private_key"] = firebase_dict["private_key"].replace(
          "\\n", "\n"
      )
      cred = credentials.Certificate(firebase_dict)
    else:
      return None
    firebase_admin.initialize_app(cred)
  return firestore.client()


try:
  db = init_firebase()
except Exception:
  db = None

if "device_id" not in st.session_state:
  new_id = str(uuid.uuid4())
  st.session_state.device_id = new_id

device_id = st.session_state.device_id

# ---------------------------------------------------------
# 5. القائمة الجانبية وإدارة الاشتراكات والطلبات
# ---------------------------------------------------------
st.sidebar.title("🔐 مركز التفعيل والاشتراكات")

if "subscription_info" not in st.session_state:
  st.session_state.subscription_info = {
      "expiry": datetime.now() + timedelta(days=7),
      "plan": "فترة تجريبية (7 أيام)",
  }

sub_info = st.session_state.subscription_info
now = datetime.now()
time_left = (sub_info["expiry"] - now).days

st.sidebar.info(f"""
📌 **حالة الحساب الحالي:**
* **الباقة:** {sub_info['plan']}
* **الانتهاء:** `{sub_info['expiry'].strftime('%Y-%m-%d')}`
* **المتبقي:** **{max(0, time_left)}** يوم
""")

# قسم إدخال كود التفعيل
with st.sidebar.expander("🔑 إدخال كود التفعيل المباشر"):
  input_code = st.text_input("أدخل كود الاشتراك:", type="password")
  if st.button("تفعيل الكود"):
    code_clean = input_code.strip().upper()
    if code_clean in ACTIVATION_CODES_REGISTRY:
      data = ACTIVATION_CODES_REGISTRY[code_clean]
      st.session_state.subscription_info["expiry"] = now + timedelta(
          days=data["days"]
      )
      st.session_state.subscription_info["plan"] = data["plan"]
      st.success(f"✅ تم تفعيل {data['plan']} بنجاح!")
      st.rerun()
    else:
      st.error("❌ كود التفعيل غير صحيح أو مستخدم.")

# قسم تقديم طلب اشتراك منفرد جديد
with st.sidebar.expander("📩 تقديم طلب اشتراك جديد (منفرد)"):
  subscriber_name = st.text_input("اسم المشترك / الشركة:")
  plan_choice = st.selectbox(
      "اختر مدة الاشتراك المطلوب:",
      ["7 أيام (تجريبي)", "شهر (30 يوم)", "3 أشهر (90 يوم)", "سنة (365 يوم)"],
  )
  if st.button("ارسال طلب الاشتراك"):
    if subscriber_name:
      if "subscription_requests" not in st.session_state:
        st.session_state.subscription_requests = []
      st.session_state.subscription_requests.append({
          "subscriber": subscriber_name,
          "plan": plan_choice,
          "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
          "status": "قيد المراجعة",
      })
      st.success("✅ تم إرسال طلب الاشتراك بنجاح! سيتم التواصل للتفعيل.")
    else:
      st.warning("يرجى إدخال اسم المشترك أولاً.")

if time_left <= 0:
  st.error("🔒 **انتهت صلاحية الاشتراك:** يرجى التجديد لتفعيل الأدوات.")
  st.stop()

# ---------------------------------------------------------
# 6. واجهة التطبيق الرئيسية (التوليد عند الطلب)
# ---------------------------------------------------------
st.sidebar.divider()
selected_app = st.sidebar.radio(
    "اختر النظام:",
    [
        "⚙️ 1. نظام الصيانة التنبؤية وإصدار التقارير",
        "🤖 2. المساعد الذكي والبحث الهندسي",
        "📋 3. سجل طلبات المشتركين (خاص بالتحكم)",
    ],
)

# --- التطبيق الأول: الصيانة التنبؤية ---
if selected_app == "⚙️ 1. نظام الصيانة التنبؤية وإصدار التقارير":
  st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات")

  col_in1, col_in2 = st.columns(2)
  with col_in1:
    gen_model = st.text_input(
        "طراز المولد", value="Perkins 410 kVA - DSE 7320"
    )
    run_hours = st.number_input(
        "ساعات التشغيل الحالية", min_value=0.0, value=700.0, step=10.0
    )
    future_run_hours = st.number_input(
        "ساعات التشغيل المستهدفة", min_value=0.0, value=940.0, step=10.0
    )
  with col_in2:
    gen_kw = st.number_input(
        "سعة المولد (kW)", min_value=5.0, value=410.0, step=10.0
    )
    load_kw = st.number_input(
        "الحمولة الحالية (kW)", min_value=0.0, value=50.0, step=10.0
    )
    last_oil_change = st.number_input(
        "عداد آخر تغيير زيت وفلاتر", value=460.0, step=10.0
    )

  load_pct = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0
  effective_hours = future_run_hours if future_run_hours > 0 else run_hours
  hours_since_oil = max(0.0, effective_hours - last_oil_change)

  base_parts = [
      {
          "تصنيف القطعة": "Schedule Services",
          "قطع الغيار / الفلاتر": "فلتر زيت (Oil Filter)",
          "العمر الافتراضي (ساعة)": 250.0,
          "الساعات المنقضية (ساعة)": float(hours_since_oil),
      },
      {
          "تصنيف القطعة": "Schedule Services",
          "قطع الغيار / الفلاتر": "فلتر وقود (Fuel Filter)",
          "العمر الافتراضي (ساعة)": 500.0,
          "الساعات المنقضية (ساعة)": float(hours_since_oil),
      },
      {
          "تصنيف القطعة": "Air System",
          "قطع الغيار / الفلاتر": "فلتر هواء (Air Filter)",
          "العمر الافتراضي (ساعة)": 1000.0,
          "الساعات المنقضية (ساعة)": float(effective_hours),
      },
      {
          "تصنيف القطعة": "Coolant System",
          "قطع الغيار / الفلاتر": "قشاط المروحة (Fan Belt)",
          "العمر الافتراضي (ساعة)": 2000.0,
          "الساعات المنقضية (ساعة)": float(effective_hours),
      },
  ]

  # استدعاء دالة الحساب المخبأة لسرعة الأداء
  df_result = process_maintenance_table_cached(
      json.dumps(base_parts), effective_hours
  )
  st.subheader("📊 حالة قطع الغيار والصيانات")
  st.dataframe(df_result, use_container_width=True)

  st.divider()

  # --- قسم التوليد عند الطلب (On-Demand Generation) ---
  st.subheader("🖨️ التوليد عند الطلب: التقارير والرسوم البيانية")
  st.caption(
      "لتوفير معالج النظام والتجنب التام للتقييد، يتم إنشاء الرسوم وملف الـ"
      " PDF فقط عند الضغط على الزر أدناه."
  )

  col_gen1, col_gen2 = st.columns([1, 2])

  with col_gen1:
    if st.button("🔄 تجهيز ملف التقرير والرسوم (PDF)", use_container_width=True):
      with st.spinner("جاري معالجة البيانات وبناء الرسوم والتنفيذ..."):
        st.session_state.pdf_bytes = build_pdf_on_demand(
            gen_model,
            run_hours,
            future_run_hours,
            gen_kw,
            load_kw,
            load_pct,
            df_result,
        )
        st.success("✅ تم تجهيز الملف بنجاح في الذاكرة!")

  with col_gen2:
    if "pdf_bytes" in st.session_state and st.session_state.pdf_bytes:
      st.download_button(
          label="📥 تنزيل التقرير الفني الشامل (PDF)",
          data=st.session_state.pdf_bytes,
          file_name=f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
          mime="application/pdf",
          use_container_width=True,
      )
    else:
      st.info("💡 اضغط على 'تجهيز ملف التقرير' أولاً لتنسيق الملف وتنزيله.")

# --- التطبيق الثاني: المساعد الذكي المخبأ ---
elif selected_app == "🤖 2. المساعد الذكي والبحث الهندسي":
  st.title("🤖 المساعد الذكي والمحرك المخبأ")
  query = st.text_input("أدخل العطل أو اسم المحرك (مثال: Perkins 1104 error):")
  if st.button("بحث في المصادر"):
    if query:
      res = search_engineering_resources_cached(query)
      st.write("### 📚 الكتب والمراجع الهندسية:")
      for b in res["books"]:
        st.markdown(f"- **[{b['title']}]({b['link']})**: {b['snippet']}")

# --- التطبيق الثالث: إدارة طلبات المشتركين ---
elif selected_app == "📋 3. سجل طلبات المشتركين (خاص بالتحكم)":
  st.title("📋 إدارة طلبات المشتركين المنفردة")
  if (
      "subscription_requests" in st.session_state
      and st.session_state.subscription_requests
  ):
    df_reqs = pd.DataFrame(st.session_state.subscription_requests)
    st.table(df_reqs)
  else:
    st.info("لا توجد طلبات اشتراك جديدة حالياً.")
