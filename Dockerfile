# 1. استخدام بيئة بايثون رسمية خفيفة
FROM python:3.10-slim

# 2. تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# 3. نسخ ملف المتطلبات وتثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. نسخ كافة ملفات التطبيق إلى داخل الحاوية
COPY . .

# 5. فتح المنفذ الخارجي الذي يتطلبه Cloud Run
EXPOSE 8080

# 6. أمر تشغيل تطبيق Streamlit على المنفذ المخصص لـ Cloud Run
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
