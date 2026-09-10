import streamlit as st
from datetime import datetime
# from supabase import create_client # تم إيقافه مؤقتاً لتجاوز الخطأ
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore

st.set_page_config(page_title="المساعد الهندسي المرجعي", page_icon="⚙️", layout="wide")

# تم تعطيل الربط بقاعدة بيانات Supabase مؤقتاً لتجاوز خطأ 401 Invalid API key
# supabase_url = st.secrets["SUPABASE_URL"]
# supabase_key = st.secrets["SUPABASE_KEY"]
# supabase = create_client(supabase_url, supabase_key)

# دالة التحقق من كود الاشتراك (معدلة للعمل المباشر بدون إنترنت/قاعدة بيانات)
def check_subscription(key):
    if key == "ENG-MONTH-2026":
        return True, "مرحباً بك (المهندس عثمان)! اشتراكك فعال."
    else:
        return False, "كود الاشتراك غير صحيح أو غير مسجل."

# --- واجهة تسجيل الدخول والتفعيل ---
st.sidebar.title("🔐 تفعيل الاشتراك")
user_license = st.sidebar.text_input("أدخل كود الاشتراك الخاص بك:", type="password")

# التحقق الإجباري
if not user_license:
    st.title("🔒 نظام المساعد الهندسي المغلق")
    st.warning("⚠️ يتطلب استخدام هذا التطبيق اشتراكاً فعالاً.")
    st.info("👈 يرجى إدخال كود الاشتراك الخاص بك في القائمة الجانبية لتأكيد الهوية وفتح الصلاحيات.")
    st.stop()  # إيقاف تنفيذ باقي الكود حتى يتم إدخال الكود

is_valid, msg = check_subscription(user_license)

if not is_valid:
    st.sidebar.error(msg)
    st.title("🔒 الوصول محظور")
    st.error(msg)
    st.stop()  # إيقاف التنفيذ في حال كان الكود غير صحيح أو منتهي الصلاحية

# --- عند إدخال كود صحيح يتم الترحيب ويفتح التطبيق بالكامل ---
st.sidebar.success(msg)

st.title("⚙️ المكتبة الهندسية السحابية والمساعد الذكي")
index_name = "generator-manuals"

user_question = st.text_input("أدخل العطل، كود الخطأ، أو الاستفسار الهندسي:")

if user_question:
    with st.spinner("جاري البحث في الأرشيف الهندسي السحابي..."):
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        vectorstore = PineconeVectorStore(index_name=index_name, embedding=embeddings)
        
        docs = vectorstore.similarity_search(user_question, k=4)
        context_text = "\n\n".join([doc.page_content for doc in docs])
        
        prompt = f"""
        أنت مهندس استشاري خبير في صيانة المولدات، لوحات التحكم، وأنظمة التبريد.
        أجب على السؤال بناءً على المراجع الهندسية المرفقة بخطوات واضحة.
        
        النصوص المرجعية:
        {context_text}
        
        سؤال المهندس/الفني:
        {user_question}
        """
        
        model = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.2)
        response = model.invoke(prompt)
        
        st.write("### 🛠️ التشخيص والحل الهندسي:")
        st.info(response.content)
