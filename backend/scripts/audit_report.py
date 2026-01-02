import json
import os
import re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAST_PAPERS_DIR = PROJECT_ROOT / "data" / "text_extraction_hybrid"
GENERATED_PAPER_PATH = PROJECT_ROOT / "data" / "outputs" / "model_papers" / "agentic_model_paper.json"

BLOOM_KEYWORDS = {
    "Recall/Define": ["define", "list", "name", "state", "what is", "identify"],
    "Understand": ["explain", "describe", "summarize", "discuss", "interpret"],
    "Apply": ["calculate", "solve", "show", "implement", "use", "apply"],
    "Analyze": ["analyze", "compare", "contrast", "distinguish", "differentiate"],
    "Evaluate": ["evaluate", "justify", "critique", "assess", "verify"],
    "Create/Design": ["design", "create", "construct", "develop", "formulate", "propose", "draw"]
}

def load_past_paper_questions():
    all_questions = []
    if not PAST_PAPERS_DIR.exists():
        return []
    
    for paper_dir in PAST_PAPERS_DIR.iterdir():
        if paper_dir.is_dir():
            blueprint_path = paper_dir / "blueprint_with_subquestions.json"
            if blueprint_path.exists():
                try:
                    with open(blueprint_path, "r", encoding="utf-8") as f:
                        questions = json.load(f)
                        for q in questions:
                            # Combine main text and subquestion text for analysis
                            text = q.get("text", "")
                            for sq in q.get("subquestions", []):
                                text += " " + sq.get("text", "")
                            all_questions.append(text)
                except Exception:
                    continue
    return all_questions

def load_generated_questions():
    if not GENERATED_PAPER_PATH.exists():
        return []
    try:
        with open(GENERATED_PAPER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            questions = data.get("questions", [])
            texts = []
            for q in questions:
                text = q.get("question_text", "")
                # If it's a nested dict with subquestions in text
                texts.append(text)
            return texts
    except Exception:
        return []

def classify_complexity(text):
    text = text.lower()
    counts = {level: 0 for level in BLOOM_KEYWORDS}
    for level, keywords in BLOOM_KEYWORDS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                counts[level] += 1
    
    # Return dominant level or "General"
    max_val = max(counts.values())
    if max_val == 0:
        return "Understand" # Default
    return max(counts, key=counts.get)

def run_audit():
    print("\n" + "="*50)
    print("📋 SYSTEM ACCURACY AUDIT REPORT")
    print("="*50)

    past_texts = load_past_paper_questions()
    gen_texts = load_generated_questions()

    if not past_texts:
        print("❌ Error: No past paper data found for comparison.")
        return
    if not gen_texts:
        print("❌ Error: No generated paper found at data/outputs/model_papers/agentic_model_paper.json")
        print("💡 Tip: Run the generator first via /model-paper/generate")
        return

    # 1. Semantic Style Accuracy (TF-IDF + Cosine Similarity)
    print("\n--- 1. SEMANTIC STYLE ACCURACY ---")
    vectorizer = TfidfVectorizer(stop_words='english')
    all_corpus = past_texts + gen_texts
    tfidf_matrix = vectorizer.fit_transform(all_corpus)
    
    past_vectors = tfidf_matrix[:len(past_texts)]
    gen_vectors = tfidf_matrix[len(past_texts):]
    
    # Average similarity of generated questions to the entire past corpus
    similarities = cosine_similarity(gen_vectors, past_vectors)
    avg_sim = np.mean(np.max(similarities, axis=1)) # Take max similarity for each gen question, then average
    
    score_semantic = avg_sim * 100
    status_semantic = "✅ HIGH" if score_semantic > 70 else "⚠️ MODERATE"
    print(f"Style Similarity Score: {score_semantic:.2f}% | Status: {status_semantic}")
    print("Interpretation: Measures how well the prompt phrasing and terminology matches local exam standards.")

    # 2. Complexity Balance (Bloom's Taxonomy)
    print("\n--- 2. COMPLEXITY BALANCE (Bloom's Taxonomy) ---")
    past_dist = {}
    for t in past_texts:
        level = classify_complexity(t)
        past_dist[level] = past_dist.get(level, 0) + 1
    
    gen_dist = {}
    for t in gen_texts:
        level = classify_complexity(t)
        gen_dist[level] = gen_dist.get(level, 0) + 1
    
    # Calculate overlap in distribution
    total_past = len(past_texts)
    total_gen = len(gen_texts)
    
    complexity_diff = 0
    levels = list(BLOOM_KEYWORDS.keys())
    print(f"{'Taxonomy Level':<20} | {'Historical %':<15} | {'Generated %':<15}")
    print("-" * 55)
    for level in levels:
        p_pct = (past_dist.get(level, 0) / total_past) * 100
        g_pct = (gen_dist.get(level, 0) / total_gen) * 100
        complexity_diff += abs(p_pct - g_pct)
        print(f"{level:<20} | {p_pct:>13.1f}% | {g_pct:>13.1f}%")
    
    # Score is inversely proportional to the sum of absolute errors
    # A total diff of 200 means 0% match, 0 means 100%
    score_complexity = max(0, 100 - (complexity_diff / 2))
    print(f"\nComplexity Alignment Score: {score_complexity:.2f}%")

    # 3. Overall Accuracy Result
    print("\n" + "="*50)
    final_score = (score_semantic * 0.4) + (score_complexity * 0.6)
    print(f"🏆 OVERALL AUTHENTICITY SCORE: {final_score:.2f}%")
    
    if final_score > 85:
        print("Verdict: 🏆 EXCELLENT - Suitable for final examination.")
    elif final_score > 70:
        print("Verdict: ✅ GOOD - High pedagogical value.")
    else:
        print("Verdict: ⚠️ CAUTION - Requires minor manual adjustments.")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_audit()
