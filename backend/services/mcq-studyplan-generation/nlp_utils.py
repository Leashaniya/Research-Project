import spacy
import textwrap
import numpy as np
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer
from config import EMBED_MODEL_NAME, TOP_KEYWORDS_PER_TOPIC

# Load NLP model (download if missing)
def _load_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        return spacy.load("en_core_web_sm")

nlp = _load_nlp()
if "sentencizer" not in nlp.pipe_names:
    nlp.add_pipe("sentencizer")

embedder = SentenceTransformer(EMBED_MODEL_NAME)

def split_sentences(text):
    doc = nlp(text.replace('\n', ' '))
    return [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]

def preprocess_for_tfidf(sentences):
    return [s.lower() for s in sentences]


_GENERIC_TOPIC_WORDS = {
    "data", "table", "tables", "row", "rows", "column", "columns", "value", "values",
    "field", "fields", "record", "records", "database", "db", "sql", "query", "queries",
    "name", "student", "students", "id", "ids", "number", "numbers", "entity", "entities",
}

_CONCEPT_RULES = [
    ("Aggregation (GROUP BY)", {"group", "group by", "count", "sum", "avg", "average", "aggregation", "aggregate"}),
    ("SQL Joins", {"join", "joins", "inner join", "left join", "right join", "outer join"}),
    ("Entity Relationships", {"entity relationship", "entity relationships", "relationship", "relationships", "erd", "er model"}),
    ("Keys and Constraints", {"primary key", "foreign key", "candidate key", "super key", "constraints", "constraint"}),
    ("Normalization", {"normalization", "normal form", "1nf", "2nf", "3nf", "bcnf"}),
    ("Transactions and ACID", {"transaction", "transactions", "commit", "rollback", "acid"}),
    ("Indexing and Performance", {"index", "indexes", "indexing", "query optimization", "performance"}),
    ("Views and Triggers", {"view", "views", "trigger", "triggers"}),
    ("Database Access", {"login", "authentication", "authorization", "access control", "privilege", "privileges"}),
    ("SQL Queries", {"select", "where", "having", "order by", "distinct", "subquery"}),
]

DBMS_TOPIC_MAP = {
    "normal": "Normalization",
    "normaliz": "Normalization",
    "1nf": "Normalization",
    "2nf": "Normalization",
    "3nf": "Normalization",
    "bcnf": "Normalization",
    "functional": "Functional Dependency",
    "dependency": "Functional Dependency",
    "relation": "Relational Algebra",
    "algebra": "Relational Algebra",
    "join": "SQL Joins",
    "sql": "SQL Queries",
    "query": "SQL Queries",
    "select": "SQL Queries",
    "entity": "Entity Relationships",
    "er": "Entity Relationships",
    "erd": "Entity Relationships",
    "relationship": "Entity Relationships",
    "key": "Keys and Constraints",
    "constraint": "Keys and Constraints",
    "primary": "Keys and Constraints",
    "foreign": "Keys and Constraints",
    "transaction": "Transactions",
    "acid": "Transactions",
    "commit": "Transactions",
    "rollback": "Transactions",
    "concurren": "Concurrency Control",
    "lock": "Concurrency Control",
    "deadlock": "Concurrency Control",
    "index": "Indexing",
    "b-tree": "Indexing",
    "btree": "Indexing",
    "hash": "Hashing",
    "view": "Views and Triggers",
    "trigger": "Views and Triggers",
    "aggregat": "Aggregation",
    "group by": "Aggregation",
    "count": "Aggregation",
    "storage": "Storage and File Organization",
    "file": "Storage and File Organization",
    "schema": "Database Design",
    "design": "Database Design",
    "integrity": "Integrity Constraints",
    "security": "Database Security",
    "user": "Database Security",
    "privilege": "Database Security",
    "recovery": "Recovery",
    "backup": "Recovery",
    "nosql": "NoSQL Databases",
    "mongodb": "NoSQL Databases",
}


def _normalize_keyword(token: str) -> str:
    text = (token or "").strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def _is_noisy_keyword(token: str) -> bool:
    if not token:
        return True
    if len(token) < 3:
        return True
    if token in _GENERIC_TOPIC_WORDS:
        return True
    if re.fullmatch(r"\d+", token):
        return True
    if re.search(r"\d", token) and token not in {"1nf", "2nf", "3nf", "bcnf"}:
        return True
    if token.endswith(" id") or token.endswith("_id"):
        return True
    if re.fullmatch(r"[a-z]{1,2}\d{2,}", token):
        return True
    return False


def _matches_rule(token: str, trigger: str) -> bool:
    return trigger == token or trigger in token or token in trigger


def _concept_group_keywords(candidate_keywords: list[str], score_map: dict[str, float], top_n: int) -> list[str]:
    concept_scores = []
    for label, triggers in _CONCEPT_RULES:
        score = 0.0
        for kw in candidate_keywords:
            if any(_matches_rule(kw, t) for t in triggers):
                score += float(score_map.get(kw, 0.0))
        if score > 0:
            concept_scores.append((score, label))
    concept_scores.sort(key=lambda x: x[0], reverse=True)
    selected = [label for _, label in concept_scores[: min(5, max(3, top_n // 2 or 3))]]
    return selected


def _canonical_topic_name(keywords: list[str]) -> str:
    """Return one clean DBMS topic name from cluster keywords."""
    for kw in keywords:
        normalized = _normalize_keyword(kw)
        if not normalized:
            continue
        for trigger, topic_name in DBMS_TOPIC_MAP.items():
            if trigger in normalized or normalized in trigger:
                return topic_name
    if keywords:
        return str(keywords[0]).strip().title()
    return "General DBMS Topic"

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
        top_indices = cluster_tfidf.argsort()[::-1][: max(24, top_n * 4)]
        raw_keywords = feature_names[top_indices].tolist()
        cleaned = []
        score_map = {}
        for idx, kw in zip(top_indices, raw_keywords):
            norm = _normalize_keyword(kw)
            if _is_noisy_keyword(norm):
                continue
            if norm not in cleaned:
                cleaned.append(norm)
            score_map[norm] = max(float(score_map.get(norm, 0.0)), float(cluster_tfidf[idx]))

        concept_labels = _concept_group_keywords(cleaned, score_map, top_n=top_n)

        # Keep a few residual meaningful phrases for graph context (non-generic)
        residual = [kw for kw in cleaned if kw not in _GENERIC_TOPIC_WORDS and len(kw) >= 3]
        residual = [kw.title() for kw in residual[: max(0, top_n - len(concept_labels))]]
        topic_keywords[topic] = (concept_labels + residual)[:top_n]
    
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
        
        selected_keywords = keywords.get(t, [])
        topic_label = _canonical_topic_name(selected_keywords)

        topics.append({
            "topic_id": t,
            # Keep one canonical, human-readable topic name.
            "keywords": [topic_label],
            "rep_sentence": rep_sentence,
            "sentences": topic_sentences[:5],  # Keep first 5 sentences
            "embeddings": topic_embeddings,
            "centroid_embedding": centroids[t]
        })
    
    return topics