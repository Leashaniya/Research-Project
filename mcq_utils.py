import os
import pandas as pd
import numpy as np
import re
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from config import EMBED_MODEL_NAME

embedder = SentenceTransformer(EMBED_MODEL_NAME)

def extract_questions_from_pdf(pdf_text, use_openai_for_answers=False):
    questions = []
    
    if not pdf_text:
        return questions
    with open("debug_raw_text.txt", "w", encoding="utf-8") as f:
        f.write(pdf_text[:5000])
    
    # Clean the text
    pdf_text = clean_text_for_parsing(pdf_text)
    
    # Look for format
    pattern1 = r'(Question\s+\d+[\.\)]?\s*)(.*?)(?=(Question\s+\d+[\.\)]?|SECTION\s+[A-Z]|\Z))'
    matches1 = re.findall(pattern1, pdf_text, re.DOTALL | re.IGNORECASE)
    
    if matches1:
        for match in matches1:
            question_data = parse_question_content(match[1].strip(), len(questions) + 1)
            if question_data and question_data['text']:
                questions.append(question_data)
    
    if len(questions) < 5:
        pattern2 = r'(\d+[\.\)]\s*)(.*?)(?=(\d+[\.\)]|Question\s+\d+|SECTION\s+[A-Z]|\Z))'
        matches2 = re.findall(pattern2, pdf_text, re.DOTALL)
        
        if matches2:
            for match in matches2:
                q_num = int(re.search(r'\d+', match[0]).group())
                question_data = parse_question_content(match[1].strip(), q_num)
                if question_data and question_data['text']:
                    questions.append(question_data)
    
    questions.sort(key=lambda x: x.get('number', 0))
    
    return questions

def clean_text_for_parsing(text):
    text = text.replace('•', '\n•')
    text = text.replace('.', '\n•')
    text = re.sub(r'(Question\s+\d+)', r'\n\1', text, flags=re.IGNORECASE)
    text = re.sub(r'(SECTION\s+[A-Z])', r'\n\1\n', text, flags=re.IGNORECASE)
    text = re.sub(r'(Answer:\s*[A-D])', r'\n\1\n', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text

def parse_question_content(content, question_number):
    if not content or len(content.strip()) < 20:
        return None
    
    # Split into lines
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    question_text = ""
    options = []
    answer = ""
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if line is an option
        option_match = re.match(r'^•\s*([A-D])[\.\)]\s*(.*)', line)
        if option_match:
            option_letter = option_match.group(1)
            option_text = option_match.group(2).strip()
            options.append(f"{option_letter}. {option_text}")
        
        elif re.match(r'^[A-D][\.\)]\s', line):
            options.append(line)
        
        elif line.lower().startswith('answer:'):
            answer_match = re.search(r'answer:\s*([A-D])', line, re.IGNORECASE)
            if answer_match:
                answer = answer_match.group(1).upper()
        
        elif not question_text:
            question_text = line
        else:
            question_text += " " + line
        
        i += 1
    
    # Clean question text
    if question_text:
        question_text = re.sub(r'\s*[A-D][\.\)].*$', '', question_text)
        question_text = re.sub(r'\s*•\s*.*$', '', question_text)
        question_text = question_text.strip()
        
        question_text = re.sub(r'Answer:\s*[A-D].*', '', question_text, flags=re.IGNORECASE)
        question_text = question_text.strip()
    
    if not options and question_text:
        option_pattern = r'([A-D])[\.\)]\s*([^A-D]*?)(?=[A-D][\.\)]|Answer:|$)'
        option_matches = re.findall(option_pattern, content, re.DOTALL)
        
        if option_matches:
            for match in option_matches:
                option_letter = match[0]
                option_text = match[1].strip()
                options.append(f"{option_letter}. {option_text}")
                
                # Remove from question text
                option_str = f"{option_letter}. {option_text}"
                question_text = question_text.replace(option_str, '')
    
    return {
        'text': question_text,
        'options': options,
        'number': question_number,
        'answer': answer
    }

def create_mcq_dataframe(questions, lecture_id):
    data = []
    
    for q in questions:
        q_id = f"{lecture_id}_Q{q['number']}"
        data.append({
            'id': q_id,
            'lecture_id': lecture_id,
            'question': q['text'],
            'options': ' | '.join(q['options']) if q['options'] else '',
            'answer': q.get('answer', ''),
            'question_number': q['number'],
            'source': 'pdf'
        })
    
    return pd.DataFrame(data)

def compute_similarities(topics, mcq_df):
    if mcq_df.empty:
        return np.array([]), np.array([])
    
    mcq_texts = mcq_df['question'].tolist()
    mcq_embeddings = embedder.encode(mcq_texts, show_progress_bar=False, convert_to_numpy=True)
    
    # Get topic embeddings
    topic_embs = []
    for t in topics:
        if 'embeddings' in t:
            topic_embs.append(np.mean(t['embeddings'], axis=0))
        elif 'centroid_embedding' in t:
            topic_embs.append(t['centroid_embedding'])
        else:
            topic_text = ' '.join(t.get('keywords', []))
            topic_embs.append(embedder.encode([topic_text])[0])
    
    topic_embs = np.vstack(topic_embs)
    sims = cosine_similarity(topic_embs, mcq_embeddings)
    
    return sims, mcq_embeddings

#   Get transformer-based similarity
def get_transformer_similarity(text1, text2):
    """
    Compute cosine similarity between two texts using transformer embeddings
    """
    emb1 = embedder.encode([text1])[0]
    emb2 = embedder.encode([text2])[0]
    return cosine_similarity([emb1], [emb2])[0][0]