import json
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict

# Add backend to path
sys.path.append(os.getcwd())

def analyze_templates():
    """
    Analyzes template_questions.json to find:
    1. Most frequent topic for each question position
    2. Most recent paper with that topic
    3. Exact sub-question structure from that paper
    """
    
    # Paths
    # Paths relative to project root
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    template_path = PROJECT_ROOT / "data" / "artifacts" / "template_questions.json"
    output_path = PROJECT_ROOT / "data" / "artifacts" / "canonical_templates.json"
    
    if not template_path.exists():
        print(f"❌ Error: Could not find {template_path}")
        return
    
    print("📊 Loading templates...")
    with open(template_path, "r", encoding="utf-8") as f:
        templates = json.load(f)
    
    # Group by question position
    by_position = defaultdict(list)
    for t in templates:
        q_id = t.get("question_id", "?")
        by_position[q_id].append(t)
    
    canonical = {}
    
    # Helper function to map keywords to topic names
    def keywords_to_topic(keywords):
        """Convert cluster keywords to a meaningful topic name."""
        kw_str = " ".join(keywords[:5]).lower()
        
        if any(word in kw_str for word in ["functional dependencies", "functional", "normalization"]):
            return "Functional Dependencies and Normalization"
        elif any(word in kw_str for word in ["int", "varchar", "table", "sql", "query", "select"]):
            return "SQL Database Schema and Queries"
        elif any(word in kw_str for word in ["eer", "model", "diagram", "entity", "attribute"]):
            return "ER and EER Diagrams"
        elif any(word in kw_str for word in ["account", "customer", "branch", "bank"]):
            return "Database Design (Banking System)"
        elif any(word in kw_str for word in ["tree", "index", "b-tree", "search", "leaf"]):
            return "Database Indexing and B-Trees"
        elif any(word in kw_str for word in ["transaction", "concurrency", "acid", "lock", "serial"]):
            return "Transaction Management and Concurrency"
        elif any(word in kw_str for word in ["relational algebra", "pi", "sigma", "join", "union"]):
            return "Relational Algebra Operations"
        else:
            return " ".join(keywords[:3])  # Fallback to keywords
    
    for q_id, questions in sorted(by_position.items()):
        print(f"\n🔍 Analyzing Q{q_id}...")
        
        # Count topic frequency (using cluster_label_keywords as proxy)
        topic_counter = Counter()
        topic_to_papers = defaultdict(list)
        
        for q in questions:
            # Use first 3 keywords as topic signature
            keywords = q.get("cluster_label_keywords", [])[:3]
            topic_sig = " ".join(keywords) if keywords else "General"
            
            topic_counter[topic_sig] += 1
            topic_to_papers[topic_sig].append(q)
        
        # Get most frequent topic
        if not topic_counter:
            print(f"  ⚠️ No topics found for Q{q_id}")
            continue
            
        dominant_topic, frequency = topic_counter.most_common(1)[0]
        print(f"  ✅ Dominant topic: '{dominant_topic}' ({frequency}/{len(questions)} papers)")
        
        # Get most recent paper with that topic
        papers_with_topic = topic_to_papers[dominant_topic]
        
        # Sort by year (extract from pdf_stem like "2023 II" or "2023")
        def extract_year(paper):
            stem = paper.get("pdf_stem", "0")
            try:
                return int(stem.split()[0])
            except:
                return 0
        
        papers_with_topic.sort(key=extract_year, reverse=True)
        most_recent = papers_with_topic[0]
        
        source_year = most_recent.get("pdf_stem", "Unknown")
        print(f"  📅 Most recent: {source_year}")
        
        # Extract sub-question structure
        subquestions = most_recent.get("subquestions", [])
        structure = []
        
        for sq in subquestions:
            label = sq.get("label", "?")
            marks = sq.get("marks")
            text_sample = sq.get("text", "")[:50]  # First 50 chars
            
            # Determine question type from text
            q_type = "General"
            text_lower = text_sample.lower()
            if any(word in text_lower for word in ["list", "name", "identify"]):
                q_type = "List"
            elif any(word in text_lower for word in ["define", "what is", "explain"]):
                q_type = "Define"
            elif any(word in text_lower for word in ["draw", "diagram", "sketch"]):
                q_type = "Draw"
            elif any(word in text_lower for word in ["calculate", "compute", "find"]):
                q_type = "Calculate"
            
            # Handle nested sub-questions (e.g., a.i, a.ii)
            nested = sq.get("subquestions", [])
            if nested:
                for nsq in nested:
                    nlabel = f"{label}.{nsq.get('label', '?')}"
                    nmarks = nsq.get("marks")
                    if nmarks:
                        structure.append({
                            "label": nlabel,
                            "marks": nmarks,
                            "type": q_type
                        })
            elif marks:
                structure.append({
                    "label": label,
                    "marks": marks,
                    "type": q_type
                })
        
        total_marks = sum(s["marks"] for s in structure)
        print(f"  📝 Structure: {len(structure)} sub-questions, {total_marks} marks")
        
        # Convert keywords to readable topic name
        keywords = most_recent.get("cluster_label_keywords", [])
        readable_topic = keywords_to_topic(keywords)
        print(f"  🏷️ Topic name: {readable_topic}")
        
        canonical[f"Q{q_id}"] = {
            "dominant_topic": readable_topic,
            "source_paper": source_year,
            "total_marks": total_marks,
            "subquestion_count": len(structure),
            "subquestion_structure": structure
        }
    
    # Save canonical templates
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(canonical, f, indent=2)
    
    print(f"\n✅ Canonical templates saved to: {output_path}")
    print(f"📊 Generated templates for {len(canonical)} question positions")

if __name__ == "__main__":
    analyze_templates()
