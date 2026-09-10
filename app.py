import os
import streamlit as st
from datetime import datetime
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore

# تهيئة شاشة التطبيق والتنسيق
st.set_page_config(
    page_title="المساعد الهندسي المرجعي", 
    page_icon="⚙️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

def check_subscription(key):
    if key == "ENG-MONTH-2026":
        return True, "مرحباً بك (المهندس عثمان)! اشتراكك فعال."
    else:
        return False, "كود الاشتراك غير صحيح أو غير مسجل."

st.sidebar.title("🔐 تفعيل الاشتراك")
user_license = st.sidebar.text_input("أدخل كود الاشتراك الخاص بك:", type="password")

if not user_license:
    st.subheader("🔒 نظام المساعد الهندسي المغلق")
    st.warning("⚠️ يتطلب استخدام هذا التطبيق اشتراكاً فعالاً.")
    st.info("👈 يرجى إدخال كود الاشتراك الخاص بك في القائمة الجانبية لتأكيد الهوية وفتح الصلاحيات.")
    st.stop()

is_valid, msg = check_subscription(user_license)

if not is_valid:
    st.sidebar.error(msg)
    st.subheader("🔒 الوصول محظور")
    st.error(msg)
    st.stop()

st.sidebar.success(msg)

st.title("⚙️ المساعد الهندسي المرجعي")
st.markdown("##### المكتبة السحابية الذكية لصيانة المولدات وأنظمة التحكم")

index_name = "generator-manuals"

user_question = st.text_input("أدخل العطل، كود الخطأ، أو الاستفسار الهندسي:", placeholder="مثال: طريقة ضبط DSE 8610 أو عطل ارتفاع الحرارة")

if user_question:
    with st.spinner("جاري البحث في الأرشيف الهندسي السحابي..."):
        # استدعاء المفاتيح صراحة
        pinecone_key = st.secrets["PINECONE_API_KEY"]
        google_key = st.secrets["GOOGLE_API_KEY"]
        os.environ["PINECONE_API_KEY"] = pinecone_key
        
        # تمرير المفاتيح بشكل مباشر للدوال
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001", 
            google_api_key=google_key
        )
        vectorstore = PineconeVectorStore(
            index_name=index_name, 
            embedding=embeddings,
            pinecone_api_key=pinecone_key
        )
        
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
        
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro", 
            temperature=0.2, 
            google_api_key=google_key
        )
        response = model.invoke(prompt)
        
        st.markdown("---")
        st.subheader("🛠️ التشخيص والحل الهندسي:")
        st.info(response.content)
