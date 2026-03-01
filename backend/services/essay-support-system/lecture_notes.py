import os
import fitz
import re

LECTURE_DIR = "Data/Lecture_Notes"

def extract_lecture_topics():
    topics = set()

    for file in os.listdir(LECTURE_DIR):
        if file.lower().endswith(".pdf"):
            doc = fitz.open(os.path.join(LECTURE_DIR, file))
            for page in doc:
                text = page.get_text()

                # Capture headings / key concepts
                for line in text.split("\n"):
                    line = line.strip()
                    if len(line.split()) <= 8 and line.isupper():
                        topics.add(line.title())

                    if re.match(r'^\d+(\.\d+)*\s+[A-Z]', line):
                        topics.add(line)

    return list(topics)
