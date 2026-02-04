import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from app.agents import BlueprintAnalyst, ContentResearcher, QuestionWriter, QualityCritic
from app.services.pdf_service import PDFService
import random
from app.core.paths import OUTPUTS_DIR, ARTIFACTS_DIR
from app.core.config import settings

# Config
# Config
MAX_RETRIES = 3
MAX_PAPER_REPAIR_RETRIES = 3

from app.core.db import db
from sentence_transformers import SentenceTransformer, util


NUM_RECENT_PAPERS_FOR_TRENDS = 6  # single source of truth for trend artifacts


def enforce_top_topic_constraint(slots: List[dict], top_topic: str) -> List[dict]:
    """
    Ensure at least one slot is forced to use top_topic.

    This function is intentionally simple and deterministic: if no slot has
    'forced_pattern_label' set already, force the first slot.
    """
    if not slots or not top_topic:
        return slots

    if any(s.get("forced_pattern_label") == top_topic for s in slots):
        return slots

    # Deterministic: force Q1 slot
    slots[0]["forced_pattern_label"] = top_topic
    return slots


def validate_model_paper(paper_json: dict, *, top_topic: Optional[str] = None, expected_q_count: int = 4) -> List[str]:
    """
    Strict validator for final model paper constraints.

    Returns a list of error codes/strings. Empty list means valid.
    """
    errors: List[str] = []

    questions = paper_json.get("questions") or []
    if len(questions) != expected_q_count:
        errors.append(f"QUESTION_COUNT_ERROR: expected={expected_q_count} got={len(questions)}")

    # Numbering must be Q1..Q4
    expected_qnos = [f"Q{i+1}" for i in range(expected_q_count)]
    got_qnos = [str(q.get("question_no", "")).strip() for q in questions]
    if got_qnos != expected_qnos:
        errors.append(f"NUMBERING_ERROR: expected={expected_qnos} got={got_qnos}")

    # Topic uniqueness + top topic inclusion
    topics = []
    for q in questions:
        t = q.get("pattern_label") or q.get("main_topic")
        topics.append(t)

    if any(t is None or str(t).strip() == "" for t in topics):
        errors.append("TOPIC_MISSING_ERROR: one or more questions missing pattern_label/main_topic")
    else:
        uniq = set(topics)
        if len(uniq) != expected_q_count:
            errors.append(f"TOPIC_DUPLICATE_ERROR: unique={len(uniq)} expected={expected_q_count} topics={topics}")
        if top_topic and top_topic not in uniq:
            errors.append(f"TOP_TOPIC_MISSING_ERROR: top_topic={top_topic} topics={topics}")

    # Marks validation (basic safety)
    total_marks = 0
    for q in questions:
        q_marks = int(q.get("marks") or 0)
        if q_marks <= 0:
            errors.append(f"MARKS_ERROR: {q.get('question_no')} has marks<=0")
        sub = q.get("subquestions") or []
        if sub:
            sub_sum = sum(int(sq.get("marks") or 0) for sq in sub)
            if sub_sum != q_marks:
                errors.append(f"MATH_ERROR: {q.get('question_no')} sub_sum={sub_sum} expected={q_marks}")
        total_marks += q_marks

    paper_total = int(paper_json.get("total_marks") or 0)
    if paper_total != total_marks:
        errors.append(f"PAPER_TOTAL_MISMATCH: paper_total={paper_total} computed_total={total_marks}")

    # Most projects assume 100; enforce unless explicitly changed elsewhere
    if total_marks != 100:
        errors.append(f"TOTAL_MARKS_ERROR: expected=100 got={total_marks}")

    return errors

class SyllabusClassifier:
    """Classifies text into Database Modules."""
    def __init__(self):
        # We use a lightweight model for speed
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        self.modules = {
            "Introduction & ER Modeling": [
                "ER diagram", "EER diagram", "entities", "relationships", "attributes", 
                "cardinality", "weak entity", "specialization", "generalization"
            ],
            "Relational Model & Normalization": [
                "relational schema", "normalization", "1NF", "2NF", "3NF", "BCNF", 
                "functional dependency", "candidate key", "primary key", "foreign key"
            ],
            "SQL & Queries": [
                "SQL", "SELECT", "INSERT", "UPDATE", "DELETE", "JOIN", "GROUP BY", 
                "HAVING", "subquery", "DDL", "DML", "CREATE TABLE"
            ],
            "Transactions & Concurrency": [
                "transaction", "ACID", "concurrency control", "serializability", "lock", 
                "two-phase locking", "deadlock", "isolation level", "schedule"
            ],
            "Indexing & Storage": [
                "index", "B-tree", "B+ tree", "hashing", "primary index", "secondary index", 
                "RAID", "disk storage", "file organization"
            ],
            "Advanced & Other": [
                "NoSQL", "distributed database", "security", "authorization", "recovery", 
                "logging", "checkpoint"
            ]
        }
        
        # Pre-compute embeddings for module keywords
        self.module_embeddings = {}
        for mod, keywords in self.modules.items():
            self.module_embeddings[mod] = self.model.encode(" ".join(keywords), convert_to_tensor=True)

    def classify(self, text):
        if not text: return "General"
        embedding = self.model.encode(text, convert_to_tensor=True)
        
        best_mod = None
        best_score = -1
        
        for mod, mod_emb in self.module_embeddings.items():
            score = util.cos_sim(embedding, mod_emb).item()
            if score > best_score:
                best_score = score
                best_mod = mod
        
        return best_mod if best_score > 0.2 else "General"

class AgentOrchestrator:
    """
    The Board of Examiners (Orchestrator).
    Manages the workflow between:
    - Analyst (Planner)
    - Researcher (Librarian)
    - Writer (Setter)
    - Critic (Reviewer)
    """

    def __init__(self):
        self.analyst = BlueprintAnalyst()
        self.researcher = ContentResearcher()
        self.writer = QuestionWriter()
        self.critic = QualityCritic()
        
        self.out_dir = OUTPUTS_DIR / "model_papers"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.out_dir / "generation_checkpoint.json"
        
        # MongoDB Connection
        self.db = db.get_db()
        
        # Initialize Syllabus Classifier
        try:
            self.classifier = SyllabusClassifier()
            print("🧠 Syllabus Classifier initialized found.")
        except Exception as e:
            print(f"⚠️ Syllabus Classifier failed to load: {e}")
            self.classifier = None

        # Load Reconstructed Diagrams (for Fallback/Injection)
        self.diagrams = []
        # ... (diagram loading code remains)

    async def _get_canonical_template(self, q_no):
        """Get the canonical template for a question position."""
        # Query MongoDB
        # q_no might be "Q1" or "1"
        q_str = str(q_no).replace("Q", "")
        
        canonical = await self.db.canonical_templates.find_one({"position_id": f"Q{q_str}"})
        if canonical:
             return canonical
             
        # Try raw ID match
        canonical = await self.db.canonical_templates.find_one({"position_id": q_str})
        if canonical:
            return canonical

        print(f"⚠️ No canonical template for {q_no}, using fallback")
        return None
        self.diagrams = []
        # ... (diagram loading code remains)

    async def _select_template(
        self,
        q_no,
        marks,
        used_modules=None,
        used_intents=None,
        used_template_ids=None,
        *,
        required_pattern_label: Optional[str] = None,
        banned_pattern_labels: Optional[Set[str]] = None,
    ):
        """
        Smart Syllabus-Aware Template Selection with Diversity Enforcement.
        1. Filter by Structure (Marks)
        2. Exclude already-used template IDs
        3. Prefer unused intents (pattern_label)
        4. Balance Syllabus Modules (avoid used_modules)
        5. Rank by Quality/Freq
        """
        # Default fallback
        fallback = {
             "pattern_label": "General Theory",
             "full_text": "(Reference style only) Explain the concept.",
             "marks": marks
        }
        
        if used_intents is None:
            used_intents = set()
        if used_template_ids is None:
            used_template_ids = set()
        
        pipeline = [
            { "$match": { "full_text": { "$exists": True, "$ne": "" } } }
        ]

        # 0. Hard filter: required/banned pattern labels (topics)
        if required_pattern_label:
            pipeline[0]["$match"]["pattern_label"] = required_pattern_label
        elif banned_pattern_labels:
            pipeline[0]["$match"]["pattern_label"] = { "$nin": list(banned_pattern_labels) }
        
        # 1. Broad Filtering by Marks (within +/- 5 range)
        if marks:
            pipeline[0]["$match"]["marks"] = { "$gte": int(marks)-5, "$lte": int(marks)+5 }
        
        # 2. Exclude already-used template IDs
        if used_template_ids:
            pipeline[0]["$match"]["_id"] = { "$nin": list(used_template_ids) }

        # Get candidates
        cursor = self.db.templates.aggregate(pipeline + [{ "$sample": { "size": 30 } }]) # Fetch larger pool for diversity
        candidates = await cursor.to_list(length=30)
        
        # If no candidates after excluding used IDs, try again without exclusion (last resort)
        if not candidates and used_template_ids:
            pipeline[0]["$match"].pop("_id", None)
            cursor = self.db.templates.aggregate(pipeline + [{ "$sample": { "size": 20 } }])
        candidates = await cursor.to_list(length=20)
        
        if not candidates:
            # If a specific topic was required, preserve it even when templates are missing.
            # This ensures top_topic enforcement can still succeed without "blind regeneration".
            if required_pattern_label:
                forced_fallback = fallback.copy()
                forced_fallback["pattern_label"] = required_pattern_label
                forced_fallback["full_text"] = f"(Fallback) No templates found for required topic: {required_pattern_label}."
                return forced_fallback
            return fallback

        # 3. Score candidates with diversity bonuses/penalties
        scored_candidates = []
        for cand in candidates:
            template_id = str(cand.get("_id", ""))
            intent = cand.get("pattern_label", "General")
            
            # Base score
            score = 100
            
            # Penalty: Same template ID already used (shouldn't happen after filter, but double-check)
            if template_id in used_template_ids:
                score -= 1000  # Heavy penalty
            
            # Penalty: Same intent already used
            if intent in used_intents:
                score -= 50
            
            # Bonus: Unused intent
            if intent not in used_intents:
                score += 30
            
            # Syllabus Classification & Balancing
            if self.classifier:
                module = self.classifier.classify(cand.get("full_text", ""))
                cand["module"] = module
                
                # Penalty for reusing modules
                if used_modules and module in used_modules:
                    score -= 50 
                
                # Boost for "Core" topics if under-represented
                if module in ["Relational Model & Normalization", "ER Modeling", "SQL"]:
                    score += 10
            else:
                cand["module"] = "General"
                    
            scored_candidates.append((score, cand, template_id, intent))
        
        # Sort by score desc
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_template, best_template_id, best_intent = scored_candidates[0]
        
        # Log selection with diversity info
        diversity_override = best_intent in used_intents if used_intents else False
        print(f"    🎯 Selected Template for {q_no}:")
        print(f"       Template ID: {best_template_id}")
        print(f"       Intent/Pattern: {best_intent}")
        print(f"       Module: {best_template.get('module', 'General')}")
        if diversity_override:
            print(f"       ⚠️  Diversity Override: Intent '{best_intent}' already used, but no better candidates")
        else:
            print(f"       ✅ Diversity: New intent selected")
        
        if used_modules is not None:
            used_modules.add(best_template.get('module', 'General'))
                
            return best_template
            
    def _is_placeholder(self, text: str) -> bool:
        """Check if text is a placeholder."""
        if not text:
            return True
        text_lower = text.lower().strip()
        placeholders = ["...", "tbd", "to be added", "[insert", "[placeholder", "n/a", "na", "tba"]
        return any(p in text_lower for p in placeholders) or len(text_lower) < 5
    
    def _build_template_copy_draft(self, q_no: str, target_marks: int, template: dict, needs_diagram: bool, diagram_type: str) -> dict:
        """
        Build a draft directly from template (template-copy safe mode).
        Used when LLM fails due to API/config errors.
        
        - stem = template.full_text (or join template parts)
        - subquestions = template subquestions/structure (keep same wording as template)
        - marks = target_marks (scale subquestion marks only if template total != target)
        - add needs_diagram + diagram_placeholder_text if intent indicates ER/EER/diagram
        """
        import string
        
        # Get stem from template
        stem = template.get("full_text", "")
        pattern_label = template.get("pattern_label", "Database Systems")
        intent_lower = pattern_label.lower()
        
        # If stem is missing, too short, or placeholder, build from intent
        if not stem or self._is_placeholder(stem) or len(stem.strip()) < 20:
            if "er" in intent_lower or "eer" in intent_lower:
                stem = "Consider a university database system with students, courses, and enrollments. Each student has student ID, name, and email. Each course has course code, title, and credits. Students enroll in courses, and each enrollment has a grade."
            elif "normalization" in intent_lower:
                stem = "Given a relation schema R(A, B, C, D) with functional dependencies: A → B, B → C, C → D."
            elif "sql" in intent_lower:
                stem = "Given a database with tables: Customers (id, name, email), Orders (id, customer_id, date), Products (id, name, price)."

        # If stem exists but is too short for ER/Normalization, ensure required content is present
        elif len(stem.strip()) < 50:
            if ("er" in intent_lower or "eer" in intent_lower) and ("entity" not in stem.lower() and "student" not in stem.lower()):
                stem = "Consider a university database system with students, courses, and enrollments. Each student has student ID, name, and email. Each course has course code, title, and credits. Students enroll in courses, and each enrollment has a grade. " + stem
            elif "normalization" in intent_lower and ("schema" not in stem.lower() and "relation" not in stem.lower()):
                stem = "Given a relation schema R(A, B, C, D) with functional dependencies: A → B, B → C, C → D. " + stem
        
        # Get subquestions from template structure
        struct_source = template.get("required_structure") or template.get("subquestions", [])
        if not struct_source:
            # Fallback: create simple structure
            num_subqs = max(2, min(5, target_marks // 5))
            marks_per_subq = target_marks // num_subqs
            remainder = target_marks % num_subqs
            struct_source = []
            for idx in range(num_subqs):
                struct_source.append({
                    "label": string.ascii_lowercase[idx],
                    "marks": marks_per_subq + (1 if idx < remainder else 0),
                    "text": f"Explain the key concepts related to {template.get('pattern_label', 'Database Systems')}."
                })
        
        # Build subquestions from template structure (ensure distinct wording)
        subquestions = []
        template_total = sum(int(item.get("marks", 0)) for item in struct_source)
        
        # Track used texts to prevent duplicates
        used_texts = set()
        
        for idx, item in enumerate(struct_source):
            label = string.ascii_lowercase[idx % 26]
            raw_marks = int(item.get("marks", 0))
            
            # Scale marks if template total differs from target
            if template_total > 0 and template_total != target_marks:
                ratio = target_marks / template_total
                marks = int(round(raw_marks * ratio))
                if raw_marks > 0 and marks == 0:
                    marks = 1
            else:
                marks = raw_marks if raw_marks > 0 else target_marks // len(struct_source)
            
            # Get text from template, but ensure it's distinct
            text = item.get("text", "")
            text_normalized = text.lower().strip() if text else ""
            
            # If text is missing, placeholder, or duplicate, generate distinct text
            if not text or self._is_placeholder(text) or text_normalized in used_texts:
                # Generate distinct subquestion text based on intent and index
                if "er" in intent_lower or "eer" in intent_lower:
                    er_texts = [
                        "Identify the main entities and their attributes.",
                        "Draw the ER/EER diagram showing relationships and cardinalities.",
                        "Map the ER diagram to a relational schema.",
                        "Explain the relationships between entities.",
                        "Describe the attributes of each entity.",
                        "Define the cardinality constraints.",
                        "List the primary and foreign keys."
                    ]
                    text = er_texts[idx % len(er_texts)]
                elif "normalization" in intent_lower:
                    norm_texts = [
                        "Identify the functional dependencies.",
                        "Determine the normal form of the relation.",
                        "Normalize the relation to 3NF.",
                        "Perform decomposition to achieve BCNF.",
                        "Explain the normalization steps.",
                        "Find the candidate keys.",
                        "Analyze the anomalies in the relation."
                    ]
                    text = norm_texts[idx % len(norm_texts)]
                elif "sql" in intent_lower:
                    sql_texts = [
                        "Write a SQL query to retrieve the requested data.",
                        "Create a SQL query with appropriate joins.",
                        "Write a SQL query with aggregation functions.",
                        "Design a SQL query with subqueries.",
                        "Explain the SQL query execution plan.",
                        "Write a SQL query with GROUP BY clause.",
                        "Create a SQL query with window functions."
                    ]
                    text = sql_texts[idx % len(sql_texts)]
                else:
                    # Generic distinct texts
                    generic_texts = [
                        "Define and explain the key concepts.",
                        "Describe the main components and their relationships.",
                        "Analyze the given scenario and provide solutions.",
                        "Compare and contrast different approaches.",
                        "Evaluate the effectiveness of the proposed solution.",
                        "List the advantages and disadvantages.",
                        "Explain the implementation details."
                    ]
                    text = generic_texts[idx % len(generic_texts)]
            
            # Track used text to prevent duplicates
            used_texts.add(text.lower().strip())
            
            subquestions.append({
                "label": label,
                "marks": marks,
                "text": text
            })
        
        # Normalize marks proportionally to ensure sum equals target_marks
        subquestions = self._normalize_subquestion_marks(subquestions, target_marks)
        
        draft = {
            "question_no": q_no,
            "marks": target_marks,
            "text": stem,
            "subquestions": subquestions
        }
        
        # Add diagram placeholder if needed
        if needs_diagram:
            draft["needs_diagram"] = True
            draft["diagram_type"] = diagram_type
            draft["diagram_placeholder_text"] = f"[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]"
        
        return draft
    
    def _normalize_subquestion_marks(self, subquestions: list, target_marks: int) -> list:
        """
        Normalize subquestion marks to ensure they sum exactly to target_marks.
        Uses proportional distribution based on relative weightage.
        
        Args:
            subquestions: List of subquestion dicts with 'marks' field
            target_marks: Target total marks for all subquestions
            
        Returns:
            List of subquestions with normalized marks that sum to target_marks
        """
        if not subquestions or target_marks <= 0:
            return subquestions
        
        # Get current marks (default to 0 if missing)
        current_marks = [int(sq.get("marks", 0)) for sq in subquestions]
        current_sum = sum(current_marks)
        
        # If sum is already correct, return as-is
        if current_sum == target_marks:
            return subquestions
        
        # If all marks are 0 or invalid, distribute evenly
        if current_sum == 0 or all(m == 0 for m in current_marks):
            marks_per_subq = target_marks // len(subquestions)
            remainder = target_marks % len(subquestions)
            normalized = []
            for idx, sq in enumerate(subquestions):
                marks = marks_per_subq + (1 if idx < remainder else 0)
                normalized.append({**sq, "marks": marks})
            return normalized
        
        # Proportional distribution: scale each mark by the ratio
        ratio = target_marks / current_sum
        normalized_marks = [int(round(m * ratio)) for m in current_marks]
        
        # Fix rounding errors: ensure sum equals target_marks exactly
        normalized_sum = sum(normalized_marks)
        diff = target_marks - normalized_sum
        
        if diff != 0:
            # Distribute the difference to the largest subquestions first
            # This preserves the relative weightage better
            sorted_indices = sorted(
                range(len(normalized_marks)), 
                key=lambda i: normalized_marks[i], 
                reverse=True
            )
            
            # Add/subtract the difference
            for i in sorted_indices:
                if diff == 0:
                    break
                if diff > 0:
                    normalized_marks[i] += 1
                    diff -= 1
                else:
                    if normalized_marks[i] > 1:  # Don't go below 1
                        normalized_marks[i] -= 1
                        diff += 1
        
        # Update subquestions with normalized marks
        normalized = []
        for idx, sq in enumerate(subquestions):
            normalized.append({**sq, "marks": normalized_marks[idx]})
        
        # Final verification
        final_sum = sum(sq["marks"] for sq in normalized)
        if final_sum != target_marks:
            # Last resort: adjust the last subquestion
            if normalized:
                normalized[-1]["marks"] = target_marks - sum(sq["marks"] for sq in normalized[:-1])
                # Ensure it's at least 1
                if normalized[-1]["marks"] < 1:
                    normalized[-1]["marks"] = 1
                    # Adjust another subquestion
                    for sq in normalized[:-1]:
                        if sq["marks"] > 1:
                            sq["marks"] -= 1
                            break
        
        return normalized

    def _sanitize_template_copy_draft(self, draft: dict, template: dict) -> dict:
        """
        Sanitize template-copy draft by:
        - Removing "described above/as shown above" references
        - Inserting minimal scenario/schema block ONLY if required by intent (ER => scenario, Normalization => schema+FDs)
        """
        import re
        
        # Get intent from template
        pattern_label = template.get("pattern_label", "").lower()
        is_er = "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label
        is_norm = "normalization" in pattern_label or "normal form" in pattern_label
        
        # Sanitize stem
        stem = draft.get("text", "")
        if stem:
            # Remove "described above" references
            stem = re.sub(r'\b(described|shown|mentioned|stated)\s+above\b', '', stem, flags=re.IGNORECASE)
            stem = re.sub(r'\bas\s+shown\s+above\b', '', stem, flags=re.IGNORECASE)
            stem = re.sub(r'\brefer\s+to\s+above\b', '', stem, flags=re.IGNORECASE)
            stem = re.sub(r'\s+', ' ', stem).strip()  # Clean up extra spaces
            
            # If stem is too short or missing required content, add it
            if is_er and ("entity" not in stem.lower() and "student" not in stem.lower()):
                # Add minimal ER scenario
                stem = "Consider a university database system with students, courses, and enrollments. Each student has student ID, name, and email. Each course has course code, title, and credits. Students enroll in courses, and each enrollment has a grade. " + stem
            elif is_norm and ("schema" not in stem.lower() and "relation" not in stem.lower()):
                # Add minimal Normalization schema
                stem = "Given a relation schema R(A, B, C, D) with functional dependencies: A → B, B → C, C → D. " + stem
        
        # Sanitize subquestions
        for sq in draft.get("subquestions", []):
            text = sq.get("text", "")
            if text:
                # Remove "described above" references
                text = re.sub(r'\b(described|shown|mentioned|stated)\s+above\b', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\bas\s+shown\s+above\b', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\brefer\s+to\s+above\b', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\s+', ' ', text).strip()
                sq["text"] = text
        
        draft["text"] = stem
        return draft

    def _generate_minimal_valid_draft(self, q_no: str, target_marks: int, intent: str, struct_source: list, needs_diagram: bool, diagram_type: str) -> dict:
        """
        Generate a minimal valid draft guaranteed to pass deterministic validation.
        Preserves template intent (ER, Normalization, SQL, etc.) and ensures:
        - Non-empty stem
        - Scenario/schema if required by type
        - Distinct subquestions (unique verbs)
        - Marks sum exactly
        """
        import string
        
        # Determine question type from intent
        intent_lower = intent.lower()
        is_er = "er" in intent_lower or "eer" in intent_lower or "diagram" in intent_lower
        is_norm = "normalization" in intent_lower or "normal form" in intent_lower
        is_sql = "sql" in intent_lower or "query" in intent_lower
        
        # Build stem with required content based on intent
        stem_parts = []
        if is_er:
            stem_parts.append("Consider a university database system with students, courses, and enrollments.")
            stem_parts.append("Each student has student ID, name, and email.")
            stem_parts.append("Each course has course code, title, and credits.")
            stem_parts.append("Students enroll in courses, and each enrollment has a grade.")
        elif is_norm:
            stem_parts.append("Given a relation schema R(A, B, C, D) with functional dependencies:")
            stem_parts.append("A → B, B → C, C → D.")
        elif is_sql:
            stem_parts.append("Given a database with tables: Customers (id, name, email), Orders (id, customer_id, date), Products (id, name, price).")
        else:
            stem_parts.append("Consider a database management system scenario.")
        
        stem = " ".join(stem_parts)
        
        # Generate distinct subquestions with unique verbs
        verbs = ["Identify", "Explain", "Describe", "Analyze", "Design", "Calculate", "List", "Compare"]
        if not struct_source:
            # No structure available, create simple structure
            num_subqs = max(2, min(5, target_marks // 5))
            marks_per_subq = target_marks // num_subqs
            remainder = target_marks % num_subqs
            
            subquestions = []
            for idx in range(num_subqs):
                label = string.ascii_lowercase[idx]
                marks = marks_per_subq + (1 if idx < remainder else 0)
                verb = verbs[idx % len(verbs)]
                
                if is_er and idx == 0:
                    text = f"{verb} the main entities and their attributes."
                elif is_er and idx == 1:
                    text = f"{verb} the relationships between entities."
                elif is_norm and idx == 0:
                    text = f"{verb} the normal form of the given relation."
                elif is_norm and idx == 1:
                    text = f"{verb} the decomposition steps to achieve 3NF."
                elif is_sql and idx == 0:
                    text = f"{verb} the SQL query to retrieve customer orders."
                else:
                    text = f"{verb} the key concepts related to {intent}."
                
                subquestions.append({"label": label, "marks": marks, "text": text})
        else:
            # Use structure source but ensure distinct verbs
            subquestions = []
            for idx, item in enumerate(struct_source):
                label = string.ascii_lowercase[idx % 26]
                raw_marks = int(item.get("marks", 0))
                
                # Scale marks
                template_total = sum(int(i.get("marks", 0)) for i in struct_source)
                if template_total > 0:
                    ratio = target_marks / template_total
                    marks = int(round(raw_marks * ratio))
                    if raw_marks > 0 and marks == 0:
                        marks = 1
                else:
                    marks = target_marks // len(struct_source)
                
                # PRIORITY: Use template text pattern if available (preserves exact instruction patterns)
                template_text = item.get("text", "").strip()
                
                # Use template text if it exists and is valid (even if long - long scenarios are OK)
                if template_text and not self._is_placeholder(template_text) and len(template_text) > 5:
                    # Use template text pattern - preserve exact instruction wording
                    # This includes long scenarios (100+ words) which are valid for Q3 parts like 'e'
                    text = template_text
                    # Remove label prefix if present (e.g., "a) " or "? " from template)
                    # But be careful - some templates start with ") " (missing label)
                    if text and len(text) > 2:
                        # Check for label prefix patterns: "a) ", "b) ", "? ", ") "
                        if text[1] in [')', '.', '?']:
                            text = text[2:].strip()
                        elif text[0] in [')', '.', '?']:
                            text = text[1:].strip()
                    
                    # Ensure we have valid text after cleaning
                    if not text or len(text) < 5:
                        # If cleaning removed too much, use original
                        text = template_text
                else:
                    # Fallback: Generate intent-aware text with distinct content for each subquestion
                    # Use different verbs AND different tasks to ensure maximum distinctness
                    verb = verbs[idx % len(verbs)]
                    
                    if is_er:
                        er_combinations = [
                            ("Identify", "the main entities and their attributes"),
                            ("Draw", "the ER/EER diagram showing relationships and cardinalities"),
                            ("Map", "the ER diagram to a relational schema with primary and foreign keys"),
                            ("Explain", "the relationships between entities and their cardinality constraints"),
                            ("Describe", "the attributes of each entity and their data types"),
                            ("List", "the primary keys, foreign keys, and integrity constraints"),
                            ("Design", "the complete relational schema based on the ER diagram")
                        ]
                        verb, task = er_combinations[idx % len(er_combinations)]
                        text = f"{verb} {task}."
                    elif is_norm:
                        norm_combinations = [
                            ("Identify", "the functional dependencies in the given relation"),
                            ("Determine", "the normal form of the relation and justify your answer"),
                            ("Normalize", "the relation to 3NF showing all decomposition steps"),
                            ("Find", "the candidate keys and superkeys in the relation"),
                            ("Perform", "decomposition to achieve BCNF with lossless join"),
                            ("Explain", "the normalization process and why each step is necessary"),
                            ("Analyze", "the anomalies in the original relation")
                        ]
                        verb, task = norm_combinations[idx % len(norm_combinations)]
                        text = f"{verb} {task}."
                    elif is_sql:
                        sql_combinations = [
                            ("Write", "a SQL query to retrieve customer orders with order details"),
                            ("Create", "a SQL query with appropriate joins between multiple tables"),
                            ("Write", "a SQL query with aggregation functions (COUNT, SUM, AVG)"),
                            ("Design", "a SQL query with subqueries for complex data retrieval"),
                            ("Briefly explain", "the SQL query execution plan and optimization strategies"),
                            ("Write", "a SQL query with GROUP BY and HAVING clauses"),
                            ("Create", "a SQL query with window functions for analytical operations")
                        ]
                        verb, task = sql_combinations[idx % len(sql_combinations)]
                        text = f"{verb} {task}."
                    else:
                        generic_combinations = [
                            ("Define", "the key concepts and their importance"),
                            ("Describe", "the main components and how they interact"),
                            ("Analyze", "the advantages and disadvantages of different approaches"),
                            ("Compare", "different implementation strategies and their trade-offs"),
                            ("Evaluate", "the effectiveness of the proposed solution"),
                            ("Briefly explain", "the real-world applications and use cases"),
                            ("List", "the key features and their benefits")
                        ]
                        verb, task = generic_combinations[idx % len(generic_combinations)]
                        text = f"{verb} {task} related to {intent}."
                
                subquestions.append({"label": label, "marks": marks, "text": text})
            
            # Normalize marks proportionally to ensure sum equals target_marks
            subquestions = self._normalize_subquestion_marks(subquestions, target_marks)
        
        draft = {
            "question_no": q_no,
            "marks": target_marks,
            "text": stem,
            "subquestions": subquestions
        }
        
        # Add diagram placeholder if needed
        if needs_diagram:
            draft["needs_diagram"] = True
            draft["diagram_type"] = diagram_type
            draft["diagram_placeholder_text"] = f"[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]"
            
            # INJECT FALLBACK MERMAID CODE (V2)
            if diagram_type == "ER" or diagram_type == "EER":
                draft["mermaid_code"] = "erDiagram\n    ENTITY1 ||--o{ ENTITY2 : relates_to\n    ENTITY2 ||--|{ ENTITY3 : contains"
            else:
                draft["mermaid_code"] = "graph TD\n    Error[Diagram Missing] -->|Fallback Draft| Generated\n    Generated[Check Logs]"
        
        return draft

    def _simplify_template(self, template, target_marks):
        """
        Force-reduce templates with >7 sub-questions to exactly 7.
        Merges small questions to maintain mark total.
        Real-world papers can have up to 7 sub-questions if needed.
        """
        structure = template.get("required_structure") or template.get("subquestions", [])
        if not structure or len(structure) <= 7:
            return template

        print(f"    ✂️  Template too long ({len(structure)} parts). Simplifying to 7 parts...")
        
        # Sort by marks (preserve high-value questions)
        # Strategy: Keep top 6 biggest questions, merge the rest into a "Concepts" question
        # OR simple accumulation. Let's do simple accumulation to preserve order.
        
        new_structure = []
        current_part = {"label": "x", "marks": 0, "text": "Combined part"}
        
        # Calculate target per part (approx)
        total_marks = sum(int(s.get("marks",0)) for s in structure)
        
        # Create exactly 7 buckets (increased from 5 for realism)
        bucket_size = len(structure) / 7.0 
        
        # Group indices: 0,1 -> 0; 2,3 -> 1; etc.
        import math
        
        buckets = [[] for _ in range(7)]
        for i, item in enumerate(structure):
            bucket_idx = min(int(i // bucket_size), 6)
            buckets[bucket_idx].append(item)
            
        final_qs = []
        import string
        for idx, bucket in enumerate(buckets):
            if not bucket: continue
            
            # Sum marks
            m = sum(int(item.get("marks", 0)) for item in bucket)
            
            # Combine text descriptions (if any) or types
            # Heuristic: Use the type/label of the first item
            first = bucket[0]
            
            final_qs.append({
                "label": string.ascii_lowercase[idx],
                "marks": m,
                "type": first.get("type", "General"),
                "text": first.get("text", "...") # Preserve hint from first item
            })
            
        # Update template
        new_template = template.copy()
        new_template["required_structure"] = final_qs
        new_template["subquestions"] = final_qs
        
        return new_template

    def _render_question(self, draft):
        """Convert structured subquestions into a beautiful string."""
        main_q_no = draft.get("question_no", "?")
        sub_qs = draft.get("subquestions", [])
        
        if not sub_qs:
            return draft.get("text", "...")
            
        lines = []
        # Use sequential alphabetic labeling (a, b, c...) for total consistency
        import string
        for idx, sq in enumerate(sub_qs):
            # Determine label: use existing if it's a simple character, otherwise use index
            raw_label = str(sq.get("label", "")).strip().rstrip(").")
            if not raw_label or len(raw_label) > 1:
                label = string.ascii_lowercase[idx % 26]
            else:
                label = raw_label
                
            text = sq.get("text", "...")
            marks = sq.get("marks", 0)
            lines.append(f"{label}) {text} ({marks} marks)")
            
        return "\n".join(lines)

    def _validate_topic_coverage(self, questions):
        """
        Validates that the paper covers diverse topics and no single topic dominates.
        Real-world papers should have balanced topic distribution.
        """
        topic_marks = {}
        total_marks = 0
        
        for q in questions:
            # Extract main topic from pattern_label or main_topic
            topic = q.get("main_topic") or q.get("pattern_label", "General")
            marks = int(q.get("marks", 0))
            topic_marks[topic] = topic_marks.get(topic, 0) + marks
            total_marks += marks
        
        if total_marks == 0:
            return
        
        # Check if any single topic dominates (>40% of marks)
        max_topic_ratio = max((marks / total_marks) * 100 for marks in topic_marks.values())
        if max_topic_ratio > 40:
            print(f"⚠️  WARNING: Topic '{max(topic_marks.items(), key=lambda x: x[1])[0]}' dominates with {max_topic_ratio:.1f}% of marks")
            print(f"   Recommendation: Ensure better topic diversity (no topic should exceed 40%)")
        
        # Check topic diversity (should have at least 3 distinct topics for 5 questions)
        unique_topics = len(topic_marks)
        if unique_topics < 3 and len(questions) >= 5:
            print(f"⚠️  WARNING: Only {unique_topics} unique topics detected for {len(questions)} questions")
            print(f"   Recommendation: Ensure broader syllabus coverage")
        else:
            print(f"✅ Topic Coverage: {unique_topics} distinct topics covered")

    def _load_trend_summary(self) -> dict:
        """
        Loads the trend summary produced by preprocessing (latest 6 papers only).
        """
        path = ARTIFACTS_DIR / "trend_summary.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ Failed to read trend_summary.json: {e}")
            return {}

    async def _count_templates_for_topic(self, marks: int, pattern_label: str) -> int:
        """
        Count MongoDB templates matching a topic and approximate marks.
        Used to choose the best slot to force top_topic into.
        """
        if not pattern_label or not marks:
            return 0
        match = {
            "full_text": { "$exists": True, "$ne": "" },
            "pattern_label": pattern_label,
            "marks": { "$gte": int(marks) - 5, "$lte": int(marks) + 5 },
        }
        cursor = self.db.templates.aggregate([{ "$match": match }, { "$count": "n" }])
        rows = await cursor.to_list(length=1)
        return int(rows[0]["n"]) if rows else 0

    async def _preview_slot_intents(self, slots: List[dict]) -> Dict[str, str]:
        """
        Preview canonical intent/pattern_label per slot (Q1..Q4) for top-topic enforcement planning.
        """
        out: Dict[str, str] = {}
        for slot in slots:
            q_no = slot.get("question_no") or slot.get("slot_id")
            if not q_no:
                continue
            canonical = await self._get_canonical_template(q_no)
            if isinstance(canonical, dict):
                out[str(q_no)] = canonical.get("pattern_label") or canonical.get("dominant_topic") or "GENERAL_THEORY"
        return out

    async def repair_model_paper(self, paper_json: dict, errors: List[str], *, top_topic: Optional[str] = None) -> dict:
        """
        Repair ONLY what violates constraints.
        Uses existing Researcher/Writer/Critic (no new agents).
        """
        # Structural repairs are deterministic
        expected_q_count = int(getattr(settings, "MODEL_PAPER_QUESTION_COUNT", 4))
        questions = paper_json.get("questions") or []

        # Trim if too many (shouldn't happen, but safe)
        if len(questions) > expected_q_count:
            questions = questions[:expected_q_count]

        # Enforce numbering Q1..Q4 deterministically
        for i, q in enumerate(questions[:expected_q_count]):
            q["question_no"] = f"Q{i+1}"

        # Build current topic sets
        topics = [q.get("pattern_label") or q.get("main_topic") for q in questions]
        used = [t for t in topics if t]
        used_set = set(used)

        # Helper: regenerate a single question with required/banned topics
        async def regenerate_question(idx: int, *, required: Optional[str] = None, banned: Optional[Set[str]] = None):
            q = questions[idx]
            q_no = q.get("question_no") or f"Q{idx+1}"
            target_marks = int(q.get("marks") or 0) or 25

            template = await self._select_template(
                q_no,
                target_marks,
                used_modules=set(),
                used_intents=set(),
                used_template_ids=set(),
                required_pattern_label=required,
                banned_pattern_labels=banned,
            )
            # Context
            query = f"Model Paper {template.get('pattern_label','')}"
            context = await self.researcher.run({"query": query})

            # Draft/review loop (reuse the same constraints; no diagram generation)
            feedback = None
            draft = None
            for attempt in range(MAX_RETRIES):
                writer_input = {
                    "slot": {"question_no": q_no, "target_marks": target_marks, "topics": [template.get("pattern_label", "General")]},
                    "template": template,
                    "context": context,
                    "feedback": feedback,
                    "mode": "generate" if attempt == 0 else "paraphrase",
                    "global_context": {
                        "used_topics": list(banned or set()),
                        "used_scenarios": [],
                        "used_question_types": [],
                        "exam_title": "Model Paper",
                        "banned_topics": list(banned or set()),
                    },
                    "needs_diagram": False,
                    "diagram_type": None,
                }
                draft = await self.writer.run(writer_input)
                draft["question_no"] = q_no
                draft["marks"] = target_marks
                draft["pattern_label"] = template.get("pattern_label")
                draft["main_topic"] = template.get("pattern_label")

                review = await self.critic.run(
                    {"draft": draft, "slot": writer_input["slot"], "context": context, "template": template, "global_context": writer_input["global_context"]}
                )
                if review.get("approved"):
                    return draft
                feedback = review.get("feedback")

            # Fallback: deterministic minimal draft (keeps constraints best-effort)
            fallback = self._generate_minimal_valid_draft(
                q_no,
                target_marks,
                template.get("pattern_label", "GENERAL_THEORY"),
                template.get("required_structure", []),
                False,
                None,
            )
            fallback["pattern_label"] = template.get("pattern_label")
            fallback["main_topic"] = template.get("pattern_label")
            return fallback

        # If top topic missing, repair one slot to be top_topic
        if top_topic and any("TOP_TOPIC_MISSING_ERROR" in e for e in errors):
            # Prefer repairing a duplicate-topic slot (if any), otherwise last question
            counts = {}
            for t in used:
                counts[t] = counts.get(t, 0) + 1
            dup_topics = {t for t, c in counts.items() if c > 1}
            repair_idx = next((i for i, t in enumerate(used) if t in dup_topics), len(questions) - 1)
            banned = set(used_set) - {top_topic}
            questions[repair_idx] = await regenerate_question(repair_idx, required=top_topic, banned=banned)

        # If duplicates exist, repair duplicates (keep first occurrence)
        if any("TOPIC_DUPLICATE_ERROR" in e for e in errors):
            seen: Set[str] = set()
            for i, q in enumerate(questions):
                t = q.get("pattern_label") or q.get("main_topic")
                if not t:
                    continue
                if t in seen:
                    banned = set(seen)
                    if top_topic:
                        banned.discard(top_topic)
                    questions[i] = await regenerate_question(i, required=None, banned=banned)
                    t2 = questions[i].get("pattern_label") or questions[i].get("main_topic")
                    if t2:
                        seen.add(t2)
                else:
                    seen.add(t)

        # Recompute total marks field
        paper_json["questions"] = questions[:expected_q_count]
        paper_json["total_marks"] = sum(int(q.get("marks") or 0) for q in paper_json["questions"])
        return paper_json

    async def run_pipeline(self):
        print("\n--- AGENTIC PIPELINE STARTED ---\n")
        
        # 1. ANALYST: Get the blueprint
        blueprint = await self.analyst.run()
        exam_title = blueprint.get("exam_title", "Model Paper")
        slots = blueprint.get("question_slots", [])

        # HARD CONSTRAINT: Model paper ALWAYS has exactly 4 questions.
        target_q_count = int(getattr(settings, "MODEL_PAPER_QUESTION_COUNT", 4))
        if len(slots) > target_q_count:
            print(f"🧱 Hard constraint: trimming blueprint slots {len(slots)} → {target_q_count}")
        slots = slots[:target_q_count]

        # Load trends (computed ONLY from latest 6 papers in preprocessing)
        trend = self._load_trend_summary()
        top_topic = trend.get("top_topic") or "GENERAL_THEORY"
        recent_used = trend.get("recent_papers_used") or []
        print(f"📈 Trend summary: top_topic={top_topic} recent_papers={len(recent_used)}")

        # Plan top-topic enforcement BEFORE generation
        slot_previews = await self._preview_slot_intents(slots)
        if any(intent == top_topic for intent in slot_previews.values()):
            print("✅ Top-topic already covered by canonical intents (no forcing needed).")
        else:
            # Choose slot with the most available templates for top_topic (deterministic)
            best_idx = 0
            best_count = -1
            for i, s in enumerate(slots):
                c = await self._count_templates_for_topic(int(s.get("target_marks") or 0), top_topic)
                if c > best_count:
                    best_idx = i
                    best_count = c
            slots[best_idx]["forced_pattern_label"] = top_topic
            print(f"🧱 Enforcing top_topic={top_topic} on slot {slots[best_idx].get('question_no')} (candidates={best_count})")

        # Required function hook (ensures at least one forced slot exists)
        slots = enforce_top_topic_constraint(slots, top_topic)
        
        # 1.5 CHECKPOINT: Load existing progress if any
        checkpoint_data = {}
        if self.checkpoint_path.exists():
            try:
                checkpoint_data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                print(f"🔄 Resuming from checkpoint: {len(checkpoint_data.get('questions', []))} questions already finished.")
            except Exception:
                pass
        
        final_questions = checkpoint_data.get("questions", [])
        total_marks = sum(int(q.get("marks") or 0) for q in final_questions)
        
        # Track already used content for uniqueness
        used_topics = set()
        banned_topics = set()  # NEW: Track topics that must not be repeated
        used_scenarios = set()
        used_question_types = set()
        used_modules = set() # NEW: Track syllabus modules
        used_intents = set() # Track used pattern_label/intent to avoid duplicates
        used_template_ids = set() # Track used template _id to never reuse exact same template
        
        # ENFORCE: Only process exactly 4 slots (Q1-Q4)
        slots = slots[:4]  # Hard limit to 4 questions
        if len(slots) > 4:
            print(f"⚠️  WARNING: Blueprint has {len(slots)} slots, limiting to 4 (Q1-Q4)")
            slots = slots[:4]
        elif len(slots) < 4:
            print(f"⚠️  WARNING: Blueprint has only {len(slots)} slots, expected 4")
        
        # Pre-populate based on checkpoint
        for q in final_questions:
            topic = q.get("main_topic")
            if topic: used_topics.add(topic)
            # Track template_id and intent from checkpoint if available
            template_id = q.get("template_id")
            if template_id:
                used_template_ids.add(str(template_id))
            intent = q.get("intent") or q.get("pattern_label")
            if intent:
                used_intents.add(intent)
            # Scenario tracking might be trickier from saved text, but we can try simple extraction
            # Or just rely on fresh generation for the rest
        
        # 2. LOOP through slots
        # 2. LOOP through slots
        for slot in slots:
            q_no = slot.get("question_no") or slot.get("slot_id") or f"Q{slot.get('position', '?')}"
            target_marks = slot.get("target_marks")

            # Check if already in checkpoint
            # Robust check: handle "Q1" vs "1" or "None"
            checkpoint_match = False
            for q in final_questions:
                saved_no = str(q.get("question_no", "")).replace("Q", "")
                current_no = str(q_no).replace("Q", "")
                if saved_no == current_no:
                    checkpoint_match = True
                    break
            
            if checkpoint_match:
                print(f"⏩ Skipping {q_no} (Already in checkpoint)")
                continue

            print(f"\n>>> Processing {q_no} ({target_marks} marks)...")
            
            # 2a. Get Canonical Template (Frequency-based)
            # GOLDEN RULE: Question number never decides topic. Topic emerges from data analysis.
            # The canonical template contains the most frequent topic for this position from past papers.
            # If Q1 appears as ER in 60% of papers, it becomes ER. If SQL in 60%, it becomes SQL.
            canonical = await self._get_canonical_template(q_no)

            # Hard topic constraints for this slot
            forced_topic = slot.get("forced_pattern_label")
            banned_topics: Set[str] = set(used_intents)  # No repeats across the 4 generated questions
            
            # Build template dict for backward compatibility
            if isinstance(canonical, dict) and "subquestion_structure" in canonical:
                # It's a canonical template (topic and structure from data analysis)
                canonical_intent = canonical.get("pattern_label") or canonical.get("dominant_topic") or "GENERAL_THEORY"
                canonical_id = str(canonical.get("_id", ""))
                
                # Check if canonical template is already used
                if canonical_intent in used_intents and canonical_id in used_template_ids:
                    print(f"    ⚠️  Canonical template for {q_no} already used (intent: {canonical_intent}, id: {canonical_id})")
                    print(f"       Searching for alternative template with different intent...")
                    # Try to find alternative template with different intent
                    template = await self._select_template(
                        q_no,
                        target_marks,
                        used_modules,
                        used_intents,
                        used_template_ids,
                        required_pattern_label=forced_topic if (forced_topic and forced_topic not in used_intents) else None,
                        banned_pattern_labels=banned_topics,
                    )
                else:
                    template = {
                        "pattern_label": canonical_intent,  # ← TOPIC FROM DATA
                        "full_text": f"Reference: {canonical.get('source_paper', 'Unknown')}",
                        "marks": canonical.get("total_marks", target_marks),
                        "required_structure": canonical.get("subquestion_structure", []),  # ← STRUCTURE FROM DATA
                        "_id": canonical.get("_id")  # Preserve template ID
                    }
                    # Don't track canonical template here - will be tracked after logging
            else:
                # Fallback to smart selection (still data-driven, not position-based)
                # Pass used_modules, used_intents, and used_template_ids to ensure diversity
                template = canonical if canonical else await self._select_template(
                    q_no,
                    target_marks,
                    used_modules,
                    used_intents,
                    used_template_ids,
                    required_pattern_label=forced_topic if (forced_topic and forced_topic not in used_intents) else None,
                    banned_pattern_labels=banned_topics,
                )
            
            # Record the module choice
            current_module = self.classifier.classify(template.get("full_text", "")) if self.classifier else "General"
            used_modules.add(current_module)
            
            # Log template selection for verification (BEFORE tracking)
            template_id = str(template.get("_id", ""))
            template_intent = template.get("pattern_label", "General")
            was_intent_used = template_intent in used_intents
            was_template_id_used = template_id in used_template_ids if template_id else False
            
            print(f"    📋 Template Selection Log:")
            print(f"       Slot ID: {q_no}")
            print(f"       Template ID: {template_id if template_id else 'N/A (canonical)'}")
            print(f"       Pattern Label/Intent: {template_intent}")
            print(f"       Already Used Intent: {'Yes [WARN]' if was_intent_used else 'No [OK]'}")
            print(f"       Already Used Template ID: {'Yes [WARN]' if was_template_id_used else 'No [OK]'}")
            
            # Track template ID and intent for diversity (AFTER logging)
            if template_id and template_id not in used_template_ids:
                used_template_ids.add(template_id)
            if template_intent and template_intent not in used_intents:
                used_intents.add(template_intent)
            
            # 2a.2 TEMPLATE STRUCTURE ENFORCEMENT
            # CRITICAL: Do NOT simplify templates - use exact structure from template
            # If template has 9 parts, generate exactly 9 sub-questions
            # If template has 7 parts, generate exactly 7 sub-questions
            # No simplification or deviation allowed
            # template = self._simplify_template(template, target_marks)  # DISABLED: Must match template exactly

            # 2b. RESEARCHER: Get context
            # E.g. if template is "SQL_DDL_DML", we might want to research "SQL DDL scenarios"
            # For now, we combine Exam Title + Topic + Template Label
            topic = slot.get('topics', ['General'])[0]
            query = f"{exam_title} {topic} {template.get('pattern_label', '')}"
            
            context = await self.researcher.run({"query": query})

            # 2b. WRITE - REVIEW LOOP
            approved = False
            feedback = None
            draft = None
            
            # 2c. WRITER: Set global context for anti-repetition
            global_context = {
                "used_topics": list(used_topics),
                "banned_topics": list(banned_topics),  # NEW: Pass banned topics for uniqueness
                "used_scenarios": list(used_scenarios),
                "used_question_types": list(used_question_types),  # NEW: Pass used types
                "exam_title": exam_title
            }
            
            # --- STRICT ANTI-REPETITION LOGIC ---
            forbidden_topics = []
            if "er_diagram" in used_question_types:
                forbidden_topics.append("Draw an ER diagram")
                forbidden_topics.append("Draw an EER diagram")
            if "normalization" in used_question_types:
                forbidden_topics.append("Normalize the relation")
            
            # --- DETECT IF DIAGRAM NEEDS TO BE SHOWN (not drawn by student) ---
            # Check if question references an existing diagram that should be displayed
            needs_diagram = False
            diagram_type = None
            
            # Get draft preview to check if it references diagrams
            draft_preview = None
            if template.get("full_text"):
                draft_preview = template.get("full_text", "")
            elif template.get("required_structure"):
                # Check subquestions for diagram references
                struct = template.get("required_structure", [])
                if struct:
                    draft_preview = " ".join([s.get("text", "") for s in struct[:3]])
            
            # Check if question should SHOW a diagram (not ask student to draw)
            if draft_preview:
                preview_lower = draft_preview.lower()
                # Pattern: "Convert the following EER model" - needs diagram shown
                # Pattern: "Based on the diagram" - needs diagram shown
                # Pattern: "The following diagram" - needs diagram shown
                if any(phrase in preview_lower for phrase in [
                    "convert the following",
                    "following eer model",
                    "following er model",
                    "following diagram",
                    "based on the diagram",
                    "the diagram shows",
                    "shown in the diagram",
                    "referring to the diagram"
                ]):
                    # Determine diagram type from pattern_label
                    pattern_lower = template_intent.lower()
                    if "eer" in pattern_lower:
                        needs_diagram = True
                        diagram_type = "EER"
                    elif "er" in pattern_lower:
                        needs_diagram = True
                        diagram_type = "ER"
                    elif "normalization" in pattern_lower or "fd" in pattern_lower:
                        needs_diagram = True
                        diagram_type = "FD"  # Functional Dependency
                    
                    if needs_diagram:
                        print(f"    [INFO] Question references existing diagram - will generate {diagram_type} diagram")
                
                # Double check if we already used this diagram type
                # if diagram_type == "ER" and "er_diagram" in used_question_types:
                #    print("    ⚠️  Skipping diagram generation (ER diagram already used)")
                #    needs_diagram = False
                #    diagram_type = None

            print(f"    ✍️  Writer drafting question... (Anti-repetition: {len(used_question_types)} types used)")
            
            # Attempt loop (Writer + Critic)
            for attempt in range(MAX_RETRIES):
                try:
                    writer_input = {
                        "slot": slot,
                        "template": template,
                        "context": context,
                        "feedback": feedback,
                        "mode": "generate" if attempt == 0 else "paraphrase", # Switch mode on retry for variety
                        "global_context": global_context,
                        "banned_topics": list(banned_topics),
                        "needs_diagram": needs_diagram,
                        "diagram_type": diagram_type
                    }
                    
                    draft = await self.writer.run(writer_input)
                    # Force stable topic label onto draft (single source of truth for validators)
                    draft["pattern_label"] = template_intent
                    draft["main_topic"] = template_intent
                    draft["intent"] = template_intent
                    if template_id:
                        draft["template_id"] = template_id
                    
                    # 2d. CRITIC: Review
                    critic_input = {
                        "draft": draft,
                        "slot": slot,
                        "context": context,
                        "template": template,
                        "global_context": global_context
                    }
                    
                    review = await self.critic.run(critic_input)
                    
                    if review["approved"]:
                        approved = True
                        print(f"    ✅ Critic Approved (Attempt {attempt+1})")
                        break
                    else:
                        feedback = review["feedback"]
                        print(f"    ❌ Critic Rejected (Attempt {attempt+1}): {feedback}")
                        time.sleep(1) # Backoff
                        
                except Exception as e:
                    print(f"    ⚠️  Error in generation loop: {e}")
                    feedback = f"System Error: {str(e)}. Please retry."
                    time.sleep(1)

            if not approved:
                print("    ⚠️  Max Retries reached. Using safest fallback.")
                # Fallback: Use template structure EXACTLY (preserves instruction patterns)
                struct_source = template.get("required_structure") or []
                if not struct_source or len(struct_source) == 0:
                    # Try to get from canonical template if available
                    canonical = await self._get_canonical_template(q_no)
                    if canonical:
                        struct_source = canonical.get("subquestion_structure", [])
                
                if struct_source and len(struct_source) > 0:
                    print(f"    📋 Fallback using template structure with {len(struct_source)} parts")
                    # Use exact structure from template
                    draft = self._generate_minimal_valid_draft(q_no, target_marks, template.get("pattern_label", "General"), struct_source, needs_diagram, diagram_type)
                else:
                    print("    ⚠️  No template structure available, using generic fallback")
                    # No structure available, use generic fallback
                    draft = self._generate_minimal_valid_draft(q_no, target_marks, template.get("pattern_label", "General"), [], needs_diagram, diagram_type)
            
            # --- AUTOMATIC DIAGRAM GENERATION (after approval) ---
            # Only generate if question needs to SHOW a diagram (not ask student to draw)
            # Check generated draft for diagram references (AFTER generation, more accurate)
            if approved:
                try:
                    from app.services.semantic_diagram_service import SemanticDiagramService
                    from app.core.paths import OUTPUTS_DIR
                    import re
                    
                    # Check if question asks student to draw (don't generate in that case)
                    all_text = draft.get("text", "") + " " + " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])])
                    all_text_lower = all_text.lower()
                    
                    # Check if any subquestion references "the following diagram/model" (needs diagram shown)
                    subquestion_references_diagram = any(
                        re.search(r"(?:convert|based on|referring to|using|the following)\s+(?:the\s+)?(?:eer|er|entity[\s-]?relationship|diagram|model)", 
                                 sq.get("text", "").lower()) 
                        for sq in draft.get("subquestions", [])
                    )
                    
                    # Also check main question for diagram references
                    main_references_diagram = bool(re.search(
                        r"(?:convert|based on|referring to|using|the following)\s+(?:the\s+)?(?:eer|er|entity[\s-]?relationship|diagram|model)",
                        draft.get("text", "").lower()
                    ))
                    
                    # Determine if we need a diagram based on ACTUAL generated text
                    if subquestion_references_diagram or main_references_diagram:
                        # Determine diagram type from pattern_label or text
                        pattern_lower = template_intent.lower()
                        if not diagram_type:
                            if "eer" in pattern_lower or "eer" in all_text_lower:
                                diagram_type = "EER"
                            elif "er" in pattern_lower or ("er" in all_text_lower and "eer" not in all_text_lower):
                                diagram_type = "ER"
                            elif "normalization" in pattern_lower or "fd" in pattern_lower or "functional dependency" in all_text_lower:
                                diagram_type = "Functional Dependency"
                        
                        if diagram_type:
                            needs_diagram = True
                            print(f"    [INFO] Detected diagram reference in generated text - will generate {diagram_type} diagram")
                    
                    # Skip if main question asks student to draw AND no subquestion references a diagram
                    main_q_draws = bool(re.search(r"draw\s+(?:an?\s+)?(?:eer|er|entity[\s-]?relationship|diagram)", draft.get("text", "").lower()))
                    if main_q_draws and not subquestion_references_diagram and not main_references_diagram:
                        print(f"    [INFO] Question asks student to draw diagram - skipping image generation")
                        needs_diagram = False
                    elif main_q_draws and (subquestion_references_diagram or main_references_diagram):
                        # Main asks to draw, but subquestion references "following diagram" - generate it
                        print(f"    [INFO] Main question asks to draw, but references 'following diagram' - will generate diagram")
                        needs_diagram = True
                    
                    if needs_diagram:
                        # Prepare image output directory
                        images_dir = OUTPUTS_DIR / "model_papers" / "images"
                        images_dir.mkdir(parents=True, exist_ok=True)
                        
                        q_no = slot.get("question_no") or slot.get("slot_id") or "Q?"
                        
                        # Extract semantic description from question text
                        semantic_description = draft.get("text", "")
                        
                        # Check if any subquestion asks about ISA hierarchies
                        requires_isa = False
                        for sq in draft.get("subquestions", []):
                            sq_text = sq.get("text", "").lower()
                            if any(phrase in sq_text for phrase in [
                                "isa hierarchy", "isa hierarchies", "mapping the isa",
                                "isa relationship", "generalization", "specialization",
                                "subtype", "supertype", "inheritance"
                            ]):
                                requires_isa = True
                                print(f"    [INFO] Subquestion requires ISA hierarchies - will enforce in diagram")
                                break
                        
                        # If ISA hierarchies are required but not mentioned in description, enhance it
                        if requires_isa and diagram_type == "EER":
                            if not any(phrase in semantic_description.lower() for phrase in [
                                "isa", "subtype", "supertype", "graduate", "undergraduate",
                                "generalization", "specialization", "inheritance"
                            ]):
                                # Enhance description to include ISA hierarchies
                                # Add a common ISA pattern (e.g., Student -> GraduateStudent, UndergraduateStudent)
                                enhancement = " The system includes ISA hierarchies: Student has subtypes GraduateStudent and UndergraduateStudent. GraduateStudent has specific attributes like ThesisTitle and AdvisorName. UndergraduateStudent has specific attributes like YearOfStudy and Major."
                                semantic_description = semantic_description + enhancement
                                print(f"    [INFO] Enhanced semantic description to include ISA hierarchies")
                        
                        # If question references "following diagram" but doesn't describe it,
                        # use the main question text as semantic description
                        if "following" in all_text_lower and len(semantic_description) < 100:
                            # Try to get description from context or use question text
                            semantic_description = draft.get("text", "")
                        
                        # Generate diagram using Graphviz from semantic description
                        print(f"    [INFO] Generating {diagram_type} diagram from semantic description for {q_no}...")
                        print(f"    [INFO] Semantic description: {semantic_description[:100]}...")
                        
                        service = SemanticDiagramService()
                        output_path = images_dir / f"{q_no}_{diagram_type.lower()}_diagram.png"
                        
                        result = service.generate_diagram_from_semantic_description(
                            description=semantic_description,
                            output_path=output_path,
                            diagram_type=diagram_type,
                            format="png"
                        )
                        
                        if result.get("success"):
                            # Add image reference to draft
                            draft["diagram_image_path"] = str(output_path)
                            draft["diagram_generated"] = True
                            draft["diagram_type"] = diagram_type
                            draft["needs_diagram"] = True
                            draft["diagram_source"] = "semantic_description"
                            print(f"    [OK] Graphviz diagram generated successfully: {output_path}")
                            
                            # Replace semantic description in question text with diagram reference
                            # Remove the detailed entity/relationship description and replace with simple reference
                            original_text = draft.get("text", "")
                            
                            # Pattern: If text contains detailed entity descriptions, replace with diagram reference
                            # Look for patterns like "has attributes", "includes", "with attributes", etc.
                            if any(phrase in original_text.lower() for phrase in [
                                "has attributes", "includes attributes", "with attributes",
                                "has entities", "entities include", "entities are",
                                "the main entities", "entities involved", "entities such as"
                            ]):
                                # Replace with simple diagram reference
                                if diagram_type == "EER":
                                    replacement_text = f"Consider the following Enhanced Entity-Relationship (EER) diagram:"
                                elif diagram_type == "ER":
                                    replacement_text = f"Consider the following Entity-Relationship (ER) diagram:"
                                elif diagram_type == "Functional Dependency":
                                    replacement_text = f"Consider the following functional dependency diagram:"
                                else:
                                    replacement_text = f"Consider the following {diagram_type} diagram:"
                                
                                draft["text"] = replacement_text
                                draft["original_semantic_description"] = original_text  # Keep original for reference
                                print(f"    [INFO] Replaced semantic description with diagram reference: '{replacement_text}'")
                        else:
                            # Fallback to text placeholder
                            error_msg = result.get("error", "Unknown error")
                            print(f"    [WARN] Graphviz diagram generation failed: {error_msg}")
                            draft["diagram_image_path"] = None
                            draft["diagram_generated"] = False
                            draft["needs_diagram"] = True
                            draft["diagram_placeholder"] = f"[DIAGRAM PLACEHOLDER: {diagram_type} diagram should be shown here based on the description]"
                            
                except Exception as e:
                    print(f"    [ERROR] Diagram generation error: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fallback to placeholder
                    draft["diagram_image_path"] = None
                    draft["diagram_generated"] = False
                    draft["needs_diagram"] = True
                    draft["diagram_placeholder"] = f"[DIAGRAM PLACEHOLDER: {diagram_type or 'diagram'} should be shown here]"
            # -----------------------------------------
            
            # 3. SAVE Question
            # Add topic label to draft for output
            topic_label = template.get("pattern_label") or slot.get("topics", ["General"])[0]
            draft["main_topic"] = topic_label
            draft["topic_label"] = topic_label  # For output clarity
            
            final_questions.append(draft)
            
            # 4. UPDATE MEMORY (Anti-Repetition)
            # Track topic and add to banned list for uniqueness
            topic = draft.get("main_topic") or template.get("pattern_label") or slot.get("topics", ["General"])[0]
            if topic: 
                used_topics.add(topic)
                banned_topics.add(topic)  # Ban this topic for remaining questions
                print(f"    📌 Topic '{topic}' added to banned list (ensuring uniqueness)")
            
            # Track derived type/task (heuristics from text)
            q_text = draft.get("text", "").lower()
            # Include subquestions in heuristic check
            for sq in draft.get("subquestions", []):
                q_text += " " + sq.get("text", "").lower()
            if "er diagram" in q_text or "eer diagram" in q_text:
                used_question_types.add("er_diagram")
            if "normalization" in q_text or "normal form" in q_text:
                used_question_types.add("normalization")
            if "sql" in q_text or "query" in q_text:
                used_question_types.add("sql_coding")
            
            # Track Scenario (hash or snippet)
            # We track the first 50 chars of the scenario to catch direct duplicates
            scenario_snippet = q_text[:50].strip()
            if scenario_snippet:
                used_scenarios.add(scenario_snippet)
                
            # Update checkpoint
            checkpoint_data = {
                "questions": final_questions,
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.checkpoint_path.write_text(json.dumps(checkpoint_data, indent=2), encoding="utf-8")
        
        # 3. VALIDATE TOPIC COVERAGE
        self._validate_topic_coverage(final_questions)

        # Ensure deterministic ordering: Q1..Q4
        def _qno_key(q: dict) -> int:
            s = str(q.get("question_no", "")).replace("Q", "").strip()
            try:
                return int(s)
            except Exception:
                return 999

        final_questions = sorted(final_questions, key=_qno_key)

        # 4. SAVE
        # Add topic summary to paper
        topic_summary = {}
        for q in final_questions:
            q_no = q.get("question_no", "?")
            topic = q.get("topic_label") or q.get("main_topic") or "Unknown"
            marks = q.get("marks", 0)
            topic_summary[q_no] = {
                "topic": topic,
                "marks": marks
            }
        
        # Recalculate total_marks from final questions (in case of updates)
        total_marks = sum(int(q.get("marks") or 0) for q in final_questions)
        
        paper = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "AGENTIC_V1",
            "total_marks": total_marks,
            "num_questions": len(final_questions),
            "topic_distribution": topic_summary,  # NEW: Topic labels and marks for each slot
            "questions": final_questions
        }

        # STRICT VALIDATOR → REPAIR LOOP (max 3)
        expected_q_count = int(getattr(settings, "MODEL_PAPER_QUESTION_COUNT", 4))
        for attempt in range(MAX_PAPER_REPAIR_RETRIES + 1):
            errors = validate_model_paper(paper, top_topic=top_topic, expected_q_count=expected_q_count)
            if not errors:
                break
            print(f"🛠️ Validation failed (attempt {attempt+1}/{MAX_PAPER_REPAIR_RETRIES+1}):")
            for e in errors:
                print(f"   - {e}")
            if attempt >= MAX_PAPER_REPAIR_RETRIES:
                raise RuntimeError(f"Model paper invalid after {MAX_PAPER_REPAIR_RETRIES} repairs: {errors}")
            paper = await self.repair_model_paper(paper, errors, top_topic=top_topic)

        # Required sanity checks (assert/log)
        final_topics = [q.get("pattern_label") or q.get("main_topic") for q in paper.get("questions", [])]
        print(f"✅ Sanity: questions={len(paper.get('questions', []))} unique_topics={len(set(final_topics))} top_topic_included={top_topic in set(final_topics)}")
        assert len(paper.get("questions", [])) == expected_q_count, "Sanity check failed: not exactly 4 questions"
        assert len(set(final_topics)) == expected_q_count, "Sanity check failed: repeated topics"
        assert top_topic in set(final_topics), "Sanity check failed: top_topic missing"

        # Save to MongoDB
        try:
            await self.db.papers.insert_one(paper.copy()) # Copy because _id is added
            print("✅ Paper saved to MongoDB.")
        except Exception as e:
            print(f"⚠️ MongoDB Save failed: {e}")

        out_path = self.out_dir / "agentic_model_paper.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(paper, f, indent=2, default=str) # default=str for ObjectId
            
        print(f"\n✅ JSON Paper generated: {out_path}")

        # 4. PDF EXPORT
        pdf_path = str(out_path).replace(".json", ".pdf")
        try:
            PDFService.generate_pdf(paper, pdf_path)
            print(f"✅ PDF Paper generated: {pdf_path}")
        except Exception as e:
            print(f"⚠️ PDF Export failed: {e}")

        # CLEANUP: Delete checkpoint
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

        return paper

# Entry point for pipeline_service
async def main():
    orchestrator = AgentOrchestrator()
    return await orchestrator.run_pipeline()
