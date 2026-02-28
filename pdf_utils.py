import os
import pdfplumber
import re
from PyPDF2 import PdfReader
import unicodedata

def extract_text_from_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"{pdf_path} not found.")
    
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += clean_pdf_text(page_text) + "\n"
    except Exception as e:
        print(f"Warning: Could not extract text from {pdf_path} using pdfplumber: {e}")
        # Fallback to PyPDF2
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += clean_pdf_text(page_text) + "\n"
        except Exception as e2:
            print(f"Error extracting text from {pdf_path}: {e2}")
    
    return text.strip()

def clean_pdf_text(text):

    if not text:
        return ""
    
    text = text.replace('..', '•')
    text = text.replace('\uf0b7', '•')
    
    text = re.sub(r'\s+', ' ', text)
    
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')
    
    text = re.sub(r'Question\s+(\d+)\s*', r'Question \1\n', text, flags=re.IGNORECASE)
    
    text = re.sub(r'Answer:\s*([A-D])', r'Answer: \1', text, flags=re.IGNORECASE)
    
    text = re.sub(r'SECTION\s+[A-Z]:', r'\nSECTION \g<0>\n', text, flags=re.IGNORECASE)
    
    text = unicodedata.normalize('NFKD', text)
    
    return text

def get_all_pdf_files(folder_path):
    pdf_files = []
    if os.path.exists(folder_path):
        for file in os.listdir(folder_path):
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(folder_path, file))
    return sorted(pdf_files)

def extract_lecture_title(text):
    lines = text.split('\n')
    for line in lines:
        if line.strip() and len(line.strip()) > 10:
            # Look for patterns like "LECTURE 01" or "Lecture 1"
            if re.search(r'(?i)lecture\s+\d+', line):
                return line.strip()
            # Or use first non-empty line as title
            return line.strip()[:100]
    return "Unknown Lecture"

def find_matching_question_file(lecture_file, question_files):
    lecture_name = os.path.basename(lecture_file)
    
    # Try to find exact match
    for q_file in question_files:
        q_name = os.path.basename(q_file)
        
        lecture_clean = re.sub(r'[^\w]', '', lecture_name.lower())
        q_clean = re.sub(r'[^\w]', '', q_name.lower())
        
        lecture_num = re.search(r'\d+', lecture_name)
        if lecture_num:
            num = lecture_num.group()
            if num in q_clean:
                return q_file
        
        if 'lec' in q_clean and 'lec' in lecture_clean:
            return q_file
    
    return question_files[0] if question_files else None