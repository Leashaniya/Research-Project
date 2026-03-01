import re
import easyocr
import fitz
import numpy as np
from PIL import Image

#  PDF  breaks
def normalize_pdf_text(text):
    lines = text.split("\n")
    rebuilt = []
    buffer = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if not buffer:
            buffer = line
        elif buffer[-1] not in ".?:":
            buffer += " " + line
        else:
            rebuilt.append(buffer)
            buffer = line

    if buffer:
        rebuilt.append(buffer)

    return " ".join(rebuilt)




reader = easyocr.Reader(['en'], gpu=False)

def ocr_image_easyocr(image):

    img = np.array(image)
    results = reader.readtext(img, detail=0, paragraph=True)
    return "\n".join(results)


def extract_text_from_pdf_with_ocr(pdf_path):
    doc = fitz.open(pdf_path)
    full_text = ""

    for page in doc:
        text = page.get_text().strip()

        if text:
            full_text += text + "\n"
        else:
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text = ocr_image_easyocr(img)
            full_text += ocr_text + "\n"

    return full_text


# Extract questions

def extract_questions(raw_text):
    text = normalize_pdf_text(raw_text)

    # Remove noise
    text = re.sub(r'Question\s*\d+', '', text, flags=re.I)
    text = re.sub(r'\(\d+\s*marks?\)', '', text, flags=re.I)
    text = re.sub(r'Page\s*\d+.*', '', text, flags=re.I)
    text = re.sub(r'--.*?--', '', text)

    # Split by sub-question labels
    parts = re.split(
        r'(?:^|\s)(?:[a-z]\)|[ivx]+\.)\s+',
        text,
        flags=re.I
    )

    questions = []
    for part in parts:
        part = clean_question(part)
        if is_valid_question(part):
            questions.append(part)

    return questions


# Clean and validate questions

def clean_question(q):
    q = re.sub(r'\s+', ' ', q)
    return q.strip()

def is_valid_question(q):

    if len(q.split()) < 5:  # too short, likely noise
        return False


    theory_keywords = (
        "refers to", "is the", "consists of", "includes", "comprises", "we discuss", "shows that"
    )
    for k in theory_keywords:
        if k in q.lower():
            return False


    interrogatives = ("what", "who", "which", "when", "where", "how", "find", "calculate", "determine", "list", "compute", "show")
    if not any(word in q.lower() for word in interrogatives) and not q.strip().endswith("?"):
        return False


    forbidden_keywords = (
        "draw", "illustrate", "diagram", "figure", "chart", "graph", "table",
        "depict", "show the", "extendible hashed", "b+ tree","shown below","that appears"
    )
    for k in forbidden_keywords:
        if k in q.lower():
            return False

    return True
