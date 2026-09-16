from fpdf import FPDF
import io

def generate_full_pdf_bytes(report_data, uploaded_image=None):
    pdf = FPDF()
    pdf.add_page()
    
    # ضبط الخط (تأكد من دعم الخطوط العربية أو استخدام الخط الافتراضي مع النصوص الإنجليزية والبيانات)
    pdf.set_font("Arial", size=12)
    
    # عنوان التقرير
    pdf.cell(200, 10, txt="Industrial Predictive Maintenance Report", ln=True, align="C")
    pdf.ln(10)
    
    # بيانات التقرير الأساسية
    pdf.cell(200, 10, txt=f"Generator / Machine ID: {report_data.get('machine_id', 'N/A')}", ln=True)
    pdf.cell(200, 10, txt=f"Status: {report_data.get('status', 'N/A')}", ln=True)
    pdf.cell(200, 10, txt=f"Date: {report_data.get('date', 'N/A')}", ln=True)
    pdf.ln(10)
    
    # قسم الصور المرفوعة للمولد أو الآلية
    if uploaded_image is not None:
        pdf.cell(200, 10, txt="Attached Equipment / Damage Image:", ln=True)
        pdf.ln(5)
        # حفظ الصورة مؤقتًا في الذاكرة لتضمينها داخل ملف الـ PDF
        image_path = "temp_uploaded_img.png"
        with open(image_path, "wb") as f:
            f.write(uploaded_image.getbuffer())
        
        # إدراج الصورة في ملف PDF (تحديد العرض بـ 100 ملم)
        pdf.image(image_path, w=100)
        pdf.ln(10)

    # استخراج الـ PDF كبيانات ثنائية مباشرة بدون استخدام .encode() لإصلاح الخطأ
    pdf_output = pdf.output(dest='S')
    
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1", errors="replace")
    return pdf_output
