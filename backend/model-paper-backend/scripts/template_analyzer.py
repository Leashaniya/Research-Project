import json
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict
import re

# Add backend to path
sys.path.append(os.getcwd())

# Trend mining MUST use only the most recent K papers (deterministic year + semester)
NUM_RECENT_PAPERS_FOR_TRENDS = 6

# Helper function to map keywords to topic names
# Note: Using KeyBERT if available, otherwise fallback to heuristics
try:
    from keybert import KeyBERT
    kw_model = KeyBERT()
    print("KeyBERT loaded for advanced topic extraction.")
except ImportError:
    kw_model = None
    print("KeyBERT not found. Using simple keyword heuristics.")

def extract_topic_keybert(text, top_n=3):
    if not kw_model:
        return None
    keywords = kw_model.extract_keywords(text, keyphrase_ngram_range=(1, 2), stop_words='english', top_n=top_n)
    return " ".join([k[0] for k in keywords])

def keywords_to_topic(keywords, full_text=None):
    """Convert cluster keywords or text to a meaningful topic name using KeyBERT or Heuristics."""
    
    # 1. OPTION A: KeyBERT (Advanced)
    if kw_model and full_text and len(full_text) > 50:
        extracted = extract_topic_keybert(full_text)
        if extracted:
            # Map extracted keyphrases to standardized categories if possible
            # For now, return the rich KeyBERT phrases capitalized
            return extracted.title()

    # 2. OPTION B: Heuristics (Legacy/Fallback)
    kw_str = " ".join(keywords[:5]).lower()
    if full_text: kw_str += " " + full_text[:200].lower()
    
    if any(word in kw_str for word in ["functional dependencies", "functional", "normalization", "normal form"]):
        return "Functional Dependencies and Normalization"
    elif any(word in kw_str for word in ["security", "role", "login", "permission", "user", "grant", "dba", "authorization", "authentication"]):
        return "Database Security and Administration"
    elif any(word in kw_str for word in ["table", "sql", "query", "select", "insert", "update", "delete", "ddl", "dml"]):
        return "SQL Database Schema and Queries"
    elif any(word in kw_str for word in ["eer", "er model", "diagram", "entity", "attribute", "relationship"]):
        return "ER and EER Diagrams"
    elif any(word in kw_str for word in ["account", "customer", "branch", "bank", "library", "hotel"]):
        return "Database Design (Case Study)"
    elif any(word in kw_str for word in ["tree", "index", "b-tree", "hash", "search", "leaf", "cost"]):
        return "Database Indexing and B-Trees"
    elif any(word in kw_str for word in ["transaction", "concurrency", "acid", "lock", "serial", "2pl", "deadlock"]):
        return "Transaction Management and Concurrency"
    elif any(word in kw_str for word in ["relational algebra", "pi", "sigma", "join", "union"]):
        return "Relational Algebra Operations"
    else:
        return " ".join(keywords[:3]).title()  # Fallback to keywords

def _parse_year_and_semester(stem: str) -> tuple[int, int]:
    """
    Deterministic recency parsing from pdf_stem.
    Supports stems like: "2023", "2023 I", "2023 II", "2023-II", etc.
    Returns: (year, semester_rank) where semester_rank: II=2, I=1, else 0
    """
    s = (stem or "").strip()
    match = re.search(r"(20\d{2})", s)
    year = int(match.group(1)) if match else 0
    s_upper = s.upper()
    sem_rank = 0
    if re.search(r"\bII\b", s_upper) or re.search(r"[-_\s]II\b", s_upper):
        sem_rank = 2
    elif re.search(r"\bI\b", s_upper) or re.search(r"[-_\s]I\b", s_upper):
        sem_rank = 1
    return year, sem_rank

def select_recent_papers(all_papers: list[str], k: int = NUM_RECENT_PAPERS_FOR_TRENDS) -> list[str]:
    """
    Select most recent k pdf_stem strings using deterministic year+semester sorting.
    """
    stems_sorted = sorted(
        set(all_papers),
        key=lambda s: (_parse_year_and_semester(s)[0], _parse_year_and_semester(s)[1], s),
        reverse=True,
    )
    return stems_sorted[:k]

def analyze_templates():
    """
    Analyzes template_questions.json to find:
    1. Most frequent topic for each question position
    2. Most recent paper with that topic
    3. Exact sub-question structure from that paper
    """
    
    # Paths
    # Paths relative to project root
    def _find_project_root(start: Path) -> Path:
        start = start.resolve()
        for p in [start] + list(start.parents):
            if (p / "data").exists() and (p / "frontend").exists() and (p / "backend").exists():
                return p
        # scripts -> model-paper-backend -> backend -> project_root
        return start.parents[3]

    PROJECT_ROOT = _find_project_root(Path(__file__))
    template_path = PROJECT_ROOT / "data" / "artifacts" / "template_questions.json"
    output_path = PROJECT_ROOT / "data" / "artifacts" / "canonical_templates.json"
    trend_summary_path = PROJECT_ROOT / "data" / "artifacts" / "trend_summary.json"
    
    if not template_path.exists():
        print(f"❌ Error: Could not find {template_path}")
        return
    
    print("Loading templates...")
    with open(template_path, "r", encoding="utf-8") as f:
        templates = json.load(f)

    # Filter to recent papers ONLY (latest K) for canonical dominance
    recent_stems = None
    if trend_summary_path.exists():
        try:
            trend = json.loads(trend_summary_path.read_text(encoding="utf-8"))
            recent_stems = set(trend.get("recent_papers_used", []))
            print(f"Using recent papers from trend_summary.json: {len(recent_stems)} stems")
        except Exception as e:
            print(f"WARNING: Failed to read trend_summary.json: {e}")
            recent_stems = None

    if recent_stems is None:
        recent_stems = set(select_recent_papers([t.get("pdf_stem", "") for t in templates], k=NUM_RECENT_PAPERS_FOR_TRENDS))
        print(f"Derived recent stems from templates: {len(recent_stems)} stems")

    templates = [t for t in templates if t.get("pdf_stem") in recent_stems]
    print(f"Templates kept after recent-6 filter: {len(templates)}")
    
    # Group by question position
    by_position = defaultdict(list)
    for t in templates:
        q_id = t.get("question_id", "?")
        by_position[q_id].append(t)
    
    canonical = {}
    
    # ENSURE: Always include Q1-Q4 even if not in recent papers
    # If Q4 is missing from recent papers, use the most recent Q4 from all papers
    # LIMIT: Only process Q1-Q4 (canonical_num_questions = 4)
    required_positions = ["1", "2", "3", "4"]
    for req_pos in required_positions:
        if req_pos not in by_position:
            print(f"\nWARNING: Q{req_pos} not found in recent papers. Searching all papers...")
            # Load all templates again to find Q4
            with open(template_path, "r", encoding="utf-8") as f:
                all_templates = json.load(f)
            q_pos_templates = [t for t in all_templates if t.get("question_id") == req_pos]
            if q_pos_templates:
                # Sort by year and get most recent
                q_pos_templates.sort(
                    key=lambda p: (_parse_year_and_semester(p.get("pdf_stem", ""))[0], _parse_year_and_semester(p.get("pdf_stem", ""))[1], p.get("pdf_stem", "")),
                    reverse=True,
                )
                most_recent_q = q_pos_templates[0]
                by_position[req_pos] = [most_recent_q]
                print(f"  Found Q{req_pos} from {most_recent_q.get('pdf_stem')} (all papers)")
            else:
                print(f"  ERROR: No Q{req_pos} found in any papers!")
    
    # ENSURE: Only process Q1-Q4 (limit to 4 questions)
    for q_id, questions in sorted(by_position.items()):
        # Skip Q5+ - we only need Q1-Q4
        if q_id not in ["1", "2", "3", "4"]:
            continue
        print(f"\nAnalyzing Q{q_id}...")
        
        # Count topic frequency using stable pattern labels (canonical dominance)
        topic_counter = Counter()
        topic_to_papers = defaultdict(list)
        
        for q in questions:
            pattern_label = q.get("pattern_label") or "GENERAL_THEORY"
            
            topic_counter[pattern_label] += 1
            topic_to_papers[pattern_label].append(q)
        
        # Get most frequent topic
        if not topic_counter:
            print(f"  WARNING: No topics found for Q{q_id}")
            continue
            
        # Deterministic choice on ties: highest count then alphabetical
        topic_items = sorted(topic_counter.items(), key=lambda kv: (-kv[1], kv[0]))
        dominant_pattern_label, frequency = topic_items[0]
        print(f"  Dominant pattern_label: '{dominant_pattern_label}' ({frequency}/{len(questions)} papers)")
        
        # Get most recent paper with that topic
        papers_with_topic = topic_to_papers[dominant_pattern_label]

        papers_with_topic.sort(
            key=lambda p: (_parse_year_and_semester(p.get("pdf_stem", ""))[0], _parse_year_and_semester(p.get("pdf_stem", ""))[1], p.get("pdf_stem", "")),
            reverse=True,
        )
        most_recent = papers_with_topic[0]
        
        # IMPORTANT: Reclassify pattern_label based on actual content to fix bad labels
        # This ensures we get correct labels like "NORMALIZATION_FD_KEYS" instead of "frame bytes time"
        import sys
        sys.path.append(str(Path(__file__).parent.parent))
        from scripts.structure_topics_template import classify_pattern
        
        # Aggregate question text for reclassification
        full_text = most_recent.get("full_text", "")
        subq_texts = [sq.get("text", "") for sq in most_recent.get("subquestions", [])]
        most_recent_text = (full_text + " " + " ".join(subq_texts)).strip()
        reclassified_label = classify_pattern(most_recent_text)
        
        # Use reclassified label if original label is clearly wrong (non-DB keywords)
        # This fixes cases like "frame bytes time" → "NORMALIZATION_FD_KEYS"
        non_db_keywords = ["frame bytes", "frame bytes time", "network protocol", "tcp/ip", "routing", 
                          "switching", "operating system", "cpu scheduling", "compiler", "html", "css",
                          "javascript", "web development", "machine learning", "neural network"]
        
        original_label_lower = dominant_pattern_label.lower()
        is_bad_label = any(non_db_kw.lower() in original_label_lower for non_db_kw in non_db_keywords)
        
        if is_bad_label or (reclassified_label != "GENERAL_THEORY" and reclassified_label != dominant_pattern_label):
            print(f"  Reclassifying '{dominant_pattern_label}' -> '{reclassified_label}' (based on content analysis)")
            dominant_pattern_label = reclassified_label

        papers_with_topic.sort(
            key=lambda p: (_parse_year_and_semester(p.get("pdf_stem", ""))[0], _parse_year_and_semester(p.get("pdf_stem", ""))[1], p.get("pdf_stem", "")),
            reverse=True,
        )
        most_recent = papers_with_topic[0]
        
        source_year = most_recent.get("pdf_stem", "Unknown")
        print(f"  Most recent: {source_year}")
        
        # Extract sub-question structure
        subquestions = most_recent.get("subquestions", [])
        structure = []
        
        # Detect nested subquestions pattern: "a) Write SQL Queries..." followed by "ii.", "iii." without labels
        # This happens when the blueprint extraction flattens nested structures
        i = 0
        while i < len(subquestions):
            sq = subquestions[i]
            label = sq.get("label", "?")
            marks = sq.get("marks")
            full_text = sq.get("text", "").strip()  # Store FULL text for pattern preservation
            text_sample = full_text[:50] if full_text else ""  # First 50 chars for type detection
            
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
            
            # Check if this subquestion has nested subquestions in the structure
            nested = sq.get("subquestions", [])
            if nested:
                # Properly nested structure exists
                for nsq in nested:
                    nlabel = f"{label}.{nsq.get('label', '?')}"
                    nmarks = nsq.get("marks")
                    ntext = nsq.get("text", "").strip()  # Full text for nested sub-questions
                    if nmarks:
                        structure.append({
                            "label": nlabel,
                            "marks": nmarks,
                            "type": q_type,
                            "text": ntext  # Store full text for pattern preservation
                        })
            # Check if this is a parent subquestion that should have nested items
            # Pattern 1: "a) Write SQL Queries to perform the following:" (Q4 pattern)
            # Pattern 2: "e) [scenario] Write a T-SQL statement..." (Q3 part e pattern)
            is_q4_pattern = ("write sql queries to perform" in full_text.lower() or 
                            "write sql queries" in full_text.lower() and "following" in full_text.lower() or
                            ("perform the following" in full_text.lower() and "sql" in full_text.lower()))
            
            is_q3_e_pattern = (
                (label.lower() == "e" or full_text.lower().startswith("e)")) and
                ("financial institution" in full_text.lower() or "developing a robust database system" in full_text.lower()) and
                ("write a t-sql statement" in full_text.lower() or "write t-sql statement" in full_text.lower())
            )
            
            if full_text and (is_q4_pattern or is_q3_e_pattern):
                # This is likely a parent subquestion with nested items
                nested_items = []
                j = i + 1
                
                # For Q3 part (e), extract "i." from parent text if present
                if is_q3_e_pattern:
                    import re
                    # Extract "Write a T-SQL statement..." part as nested item i
                    t_sql_match = re.search(r'(write\s+(?:a\s+)?t-sql\s+statement[^.]*\.)', full_text, re.IGNORECASE)
                    if t_sql_match:
                        nested_items.append({
                            "label": "i",
                            "marks": marks,  # Use parent marks for first item
                            "text": f"i. {t_sql_match.group(1).strip()}",
                            "type": q_type
                        })
                        # Remove the T-SQL statement part from parent text, keep only scenario
                        full_text = re.sub(r'write\s+(?:a\s+)?t-sql\s+statement[^.]*\.', '', full_text, flags=re.IGNORECASE).strip()
                
                # Check if next items are "ii.", "iii.", "iv.", "v." without proper labels
                while j < len(subquestions):
                    next_sq = subquestions[j]
                    next_text = next_sq.get("text", "").strip()
                    next_label = next_sq.get("label", "?")
                    
                    # Check if next item starts with "ii.", "iii.", "iv.", "v." (nested pattern)
                    if (next_text.lower().startswith(("ii.", "iii.", "iv.", "v.")) or
                        next_text.lower().startswith(("ii ", "iii ", "iv ", "v "))):
                        # This is a nested subquestion
                        nested_items.append({
                            "label": next_text[:3].strip().rstrip("."),  # Extract "ii", "iii", etc.
                            "marks": next_sq.get("marks"),
                            "text": next_text,
                            "type": q_type
                        })
                        j += 1
                    # For Q3 part (e), also check for items that should be nested (ii, iii, iv, v)
                    # These are items that come after the scenario but don't have labels
                    elif is_q3_e_pattern and j < len(subquestions):
                        # Check if it's "Provide Sarah..." (should be ii)
                        if "provide sarah" in next_text.lower() or "provide" in next_text.lower() and "sarah" in next_text.lower():
                            nested_items.append({
                                "label": "ii",
                                "marks": next_sq.get("marks"),
                                "text": f"ii. {next_text}",
                                "type": q_type
                            })
                            j += 1
                        # Check if it's "Assuming Emily..." (should be iii)
                        elif "assuming emily" in next_text.lower():
                            nested_items.append({
                                "label": "iii",
                                "marks": next_sq.get("marks"),
                                "text": f"iii. {next_text}",
                                "type": q_type
                            })
                            j += 1
                        # Check if it's "Assuming Nathan..." (should be iv)
                        elif "assuming nathan" in next_text.lower():
                            nested_items.append({
                                "label": "iv",
                                "marks": next_sq.get("marks"),
                                "text": f"iv. {next_text}",
                                "type": q_type
                            })
                            j += 1
                        # Check if it's "Assuming Michael..." (should be v)
                        elif "assuming michael" in next_text.lower():
                            nested_items.append({
                                "label": "v",
                                "marks": next_sq.get("marks"),
                                "text": f"v. {next_text}",
                                "type": q_type
                            })
                            j += 1
                        else:
                            # Not a nested item, stop
                            break
                    elif next_text.lower().startswith(("i.", "i ")) and "find" in next_text.lower():
                        # First nested item might be in the parent text (Q4 pattern)
                        # Extract it from parent if present
                        if "i." in full_text or "i " in full_text:
                            # Extract the i. part from parent text
                            import re
                            i_match = re.search(r"i\.\s*(.+?)(?:\s*ii\.|$)", full_text, re.IGNORECASE)
                            if i_match:
                                nested_items.insert(0, {
                                    "label": "i",
                                    "marks": None,  # No marks for first item typically
                                    "text": f"i. {i_match.group(1).strip()}",
                                    "type": q_type
                                })
                        j += 1
                    else:
                        # Not a nested item, stop
                        break
                
                # If we found nested items, create proper structure
                if nested_items:
                    # Add parent subquestion with nested structure
                    structure.append({
                        "label": label,
                        "marks": None,  # Parent might not have marks
                        "type": q_type,
                        "text": full_text,
                        "nested": True,  # Flag to indicate nested structure
                        "nested_items": nested_items
                    })
                    # Skip the nested items we've processed
                    i = j
                    continue
            elif marks:
                # Regular subquestion with marks
                structure.append({
                    "label": label,
                    "marks": marks,
                    "type": q_type,
                    "text": full_text  # Store full text for pattern preservation
                })
        
            i += 1
        
        total_marks = sum(s.get("marks", 0) or 0 for s in structure)
        print(f"  Structure: {len(structure)} sub-questions, {total_marks} marks")
        
        # Keep a human-friendly topic name too (optional), but canonical dominance is pattern_label
        keywords = most_recent.get("cluster_label_keywords", [])
        full_text = most_recent.get("full_text", "")
        readable_topic = keywords_to_topic(keywords, full_text) if (keywords or full_text) else dominant_pattern_label
        print(f"  Topic name: {readable_topic}")
        
        canonical[f"Q{q_id}"] = {
            "dominant_topic": readable_topic,             # human-friendly topic name
            "pattern_label": dominant_pattern_label,      # stable intent label (used by orchestrator) - REclassified if needed
            "source_paper": source_year,
            "total_marks": total_marks,
            "subquestion_count": len(structure),
            "subquestion_structure": structure
        }
    
    # Save canonical templates
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(canonical, f, indent=2)
    
    print(f"\nCanonical templates saved to: {output_path}")
    print(f"Generated templates for {len(canonical)} question positions")

if __name__ == "__main__":
    analyze_templates()
