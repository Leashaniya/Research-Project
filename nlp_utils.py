import spacy
import textwrap
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer
from config import EMBED_MODEL_NAME, TOP_KEYWORDS_PER_TOPIC

# Load NLP & embedding model
nlp = spacy.load("en_core_web_sm")
if "sentencizer" not in nlp.pipe_names:
    nlp.add_pipe("sentencizer")

embedder = SentenceTransformer(EMBED_MODEL_NAME)

def split_sentences(text):
    doc = nlp(text.replace('\n', ' '))
    return [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]

def preprocess_for_tfidf(sentences):
    return [s.lower() for s in sentences]

def shorten(text, max_chars=80):
    if len(text) <= max_chars:
        return text
    return textwrap.shorten(text, width=max_chars, placeholder="...")

def extract_topic_keywords(sentences, labels, n_topics, top_n=TOP_KEYWORDS_PER_TOPIC):
    vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1,2), stop_words="english")
    X = vectorizer.fit_transform(sentences)
    feature_names = np.array(vectorizer.get_feature_names_out())
    
    topic_keywords = {}
    for topic in range(n_topics):
        idxs = np.where(labels == topic)[0]
        if len(idxs) == 0:
            topic_keywords[topic] = []
            continue
        
        cluster_tfidf = X[idxs].mean(axis=0).A1
        top_indices = cluster_tfidf.argsort()[::-1][:top_n]
        topic_keywords[topic] = feature_names[top_indices].tolist()
    
    return topic_keywords

def extract_topics_from_text(text, n_topics=6, max_sentences=100):
    sentences = split_sentences(text)
    
    if len(sentences) == 0:
        return []
    
    # Limit number of sentences
    if len(sentences) > max_sentences:
        step = max(1, len(sentences) // max_sentences)
        sentences = [sentences[i] for i in range(0, len(sentences), step)]
    
    preproc = preprocess_for_tfidf(sentences)
    sent_embeddings = embedder.encode(preproc, show_progress_bar=False, convert_to_numpy=True)
    
    n_clusters = min(n_topics, max(1, len(sentences)))
    if n_clusters < 2:
        n_clusters = 2
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(sent_embeddings)
    centroids = kmeans.cluster_centers_
    
    keywords = extract_topic_keywords(preproc, labels, n_clusters, top_n=TOP_KEYWORDS_PER_TOPIC)
    
    topics = []
    for t in range(n_clusters):
        topic_sentences = [sentences[i] for i in range(len(sentences)) if labels[i] == t]
        topic_embeddings = [sent_embeddings[i] for i in range(len(sentences)) if labels[i] == t]
        
        rep_sentence = shorten(topic_sentences[0]) if topic_sentences else ""
        
        topics.append({
            "topic_id": t,
            "keywords": keywords.get(t, []),
            "rep_sentence": rep_sentence,
            "sentences": topic_sentences[:5],  # Keep first 5 sentences
            "embeddings": topic_embeddings,
            "centroid_embedding": centroids[t]
        })
    
    return topics