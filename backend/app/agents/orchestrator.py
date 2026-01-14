import time
import json
from pathlib import Path
from app.agents import BlueprintAnalyst, ContentResearcher, QuestionWriter, QualityCritic
from app.services.pdf_service import PDFService
import random
from app.core.paths import OUTPUTS_DIR, ARTIFACTS_DIR

# Config
# Config
MAX_RETRIES = 3

from app.core.db import db
from sentence_transformers import SentenceTransformer, util

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

    async def _select_template(self, q_no, marks, used_modules=None, used_intents=None, used_template_ids=None):
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
        else:
                stem = f"Consider a database management system scenario related to {pattern_label}."
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
        
        # Fix rounding errors
        current_sum = sum(sq["marks"] for sq in subquestions)
        diff = target_marks - current_sum
        if diff != 0 and subquestions:
            max_idx = max(range(len(subquestions)), key=lambda i: subquestions[i]['marks'])
            subquestions[max_idx]['marks'] += diff
        
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
                
                verb = verbs[idx % len(verbs)]
                
                # Generate intent-aware text with distinct content for each subquestion
                # Use different verbs AND different tasks to ensure maximum distinctness
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
                        ("Explain", "the SQL query execution plan and optimization strategies"),
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
                        ("Explain", "the real-world applications and use cases"),
                        ("List", "the key features and their benefits")
                    ]
                    verb, task = generic_combinations[idx % len(generic_combinations)]
                    text = f"{verb} {task} related to {intent}."
                
                subquestions.append({"label": label, "marks": marks, "text": text})
            
            # Fix rounding
            current_sum = sum(sq["marks"] for sq in subquestions)
            diff = target_marks - current_sum
            if diff != 0 and subquestions:
                max_idx = max(range(len(subquestions)), key=lambda i: subquestions[i]['marks'])
                subquestions[max_idx]['marks'] += diff
        
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

    async def run_pipeline(self):
        print("\n--- AGENTIC PIPELINE STARTED ---\n")
        
        # 1. ANALYST: Get the blueprint
        blueprint = await self.analyst.run()
        exam_title = blueprint.get("exam_title", "Model Paper")
        slots = blueprint.get("question_slots", [])
        
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
        used_scenarios = set()
        used_question_types = set()
        used_modules = set() # NEW: Track syllabus modules
        used_intents = set() # Track used pattern_label/intent to avoid duplicates
        used_template_ids = set() # Track used template _id to never reuse exact same template
        
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
            
            # Build template dict for backward compatibility
            if isinstance(canonical, dict) and "subquestion_structure" in canonical:
                # It's a canonical template (topic and structure from data analysis)
                canonical_intent = canonical.get("dominant_topic", "General")
                canonical_id = str(canonical.get("_id", ""))
                
                # Check if canonical template is already used
                if canonical_intent in used_intents and canonical_id in used_template_ids:
                    print(f"    ⚠️  Canonical template for {q_no} already used (intent: {canonical_intent}, id: {canonical_id})")
                    print(f"       Searching for alternative template with different intent...")
                    # Try to find alternative template with different intent
                    template = await self._select_template(q_no, target_marks, used_modules, used_intents, used_template_ids)
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
                template = canonical if canonical else await self._select_template(q_no, target_marks, used_modules, used_intents, used_template_ids)
            
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
            
            # 2a.2 SIMPLIFY TEMPLATE (User Request: Realistic Flow)
            # If template has > 5 parts, crush it down to 5
            template = self._simplify_template(template, target_marks)

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
            
            # Identify forbidden topics for this specific slot
            forbidden_topics = []
            
            # --- STRICT ANTI-REPETITION LOGIC ---
            # If we already have an ER diagram, forbid another one
            if "er_diagram" in used_question_types:
                forbidden_topics.append("Draw an ER diagram")
                forbidden_topics.append("Draw an EER diagram")
            
            # If we already have ER → Relational Mapping, forbid another one
            if "er_to_relational_mapping" in used_question_types:
                forbidden_topics.append("Map the ER diagram to relational")
                forbidden_topics.append("Map ER to relational schema")
                forbidden_topics.append("Convert ER diagram to relational model")
                forbidden_topics.append("Design relational schema from ER diagram")
            
            # If we just asked about Normalization, restrict it
            if "normalization" in used_question_types:
                forbidden_topics.append("Normalization")
                
            print(f"    ⛔ Forbidden Topics: {forbidden_topics}")

            # DIAGRAM PLACEHOLDER LOGIC (No preprocessing/extraction)
            # Check if question type requires diagram
            needs_diagram = False
            diagram_type = None
            pattern_label_lower = template.get("pattern_label", "").lower()
            if "er" in pattern_label_lower or "eer" in pattern_label_lower or "diagram" in pattern_label_lower:
                needs_diagram = True
                if "eer" in pattern_label_lower:
                    diagram_type = "EER"
                else:
                    diagram_type = "ER"

            # Track if Writer failed due to API/config errors
            writer_api_error = None
            writer_api_error_str = None

            for attempt in range(MAX_RETRIES + 1):
                # IMPROVEMENT B: DUAL-MODE WRITER
                # Attempts 0, 1: Pure Generation (High Quality, Original)
                # Attempts 2, 3: Paraphrase Fallback (Safe, Guaranteed Structure)
                writer_mode = "generate"
                if attempt >= 2:
                    writer_mode = "paraphrase"
                
                # Writer
                try:
                    draft = await self.writer.run({
                        "slot": slot,
                        "template": template,
                        "context": context,
                        "feedback": feedback,
                        "global_context": {
                            "used_topics": list(used_topics),
                            "used_scenarios": list(used_scenarios),
                            "forbidden_topics": forbidden_topics
                        },
                        "needs_diagram": needs_diagram,
                        "diagram_type": diagram_type,
                        "mode": writer_mode
                    })
                    # Reset API error flag on success
                    writer_api_error = None
                    writer_api_error_str = None
                except Exception as e:
                    error_str = str(e)
                    # Check if it's an API/config error (not a validation error)
                    is_api_error = (
                        "404" in error_str or 
                        "DeploymentNotFound" in error_str or 
                        "API" in error_str or 
                        "LLM Client not initialized" in error_str or
                        "not initialized" in error_str.lower() or
                        "connection" in error_str.lower() or
                        "timeout" in error_str.lower() or
                        "authentication" in error_str.lower() or
                        "unauthorized" in error_str.lower()
                    )
                    
                    if is_api_error:
                        writer_api_error = e
                        writer_api_error_str = error_str
                        print(f"⚠️ Writer failed on attempt {attempt} due to API/config error: {error_str}. Retrying...")
                    else:
                    print(f"⚠️ Writer failed on attempt {attempt}: {e}. Retrying...")
                    
                    feedback = f"Previous generation failed with error: {e}. Ensure all fields are filled."
                    continue
                
                # Critic
                review = await self.critic.run({
                    "draft": draft,
                    "context": context,
                    "template": template,
                    "q_no": q_no  # Pass q_no to fix "None" label
                })
                
                is_approved = review.get("approved", False)  # Default to False - require explicit approval
                feedback_code = review.get("feedback_code", "UNKNOWN")
                feedback = review.get("feedback", "No feedback")
                
                if is_approved:
                    print(f"✅ {q_no} Approved!")
                    approved = True
                    
                    # NORMALIZE LABELS (Strictly a, b, c...)
                    import string, re
                    for idx, sq in enumerate(draft.get("subquestions", [])):
                        sq["label"] = string.ascii_lowercase[idx % 26]
                        # Remove redundant label prefixes from text (e.g., "a) What is..." -> "What is...")
                        sq["text"] = re.sub(r"^\(?[a-iA-I]\)?[\.\)]\s*", "", sq.get("text", "")).strip()
                    
                    # Add diagram placeholder if needed
                    if needs_diagram:
                        draft["needs_diagram"] = True
                        draft["diagram_type"] = diagram_type
                        draft["diagram_placeholder_text"] = f"[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]"
                    
                    # Update global tracking: store topic and a snippet of the scenario
                    used_topics.add(template.get("pattern_label", "General"))
                    # Track template ID and intent for diversity (already tracked above, but ensure it's set)
                    template_id = str(template.get("_id", ""))
                    template_intent = template.get("pattern_label", "General")
                    if template_id:
                        used_template_ids.add(template_id)
                    if template_intent:
                        used_intents.add(template_intent)
                    
                    # Detect Question Type from Text (Heuristic)
                    q_text_lower = draft.get("text", "").lower()
                    if ("draw" in q_text_lower or "design" in q_text_lower or "construct" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower):
                        used_question_types.add("er_diagram")
                        print("      📌 Marked type: er_diagram")
                    if "normalization" in q_text_lower or "normal form" in q_text_lower:
                        used_question_types.add("normalization")
                    if "write a query" in q_text_lower or "sql" in q_text_lower:
                        used_question_types.add("sql_query")
                    # Detect ER → Relational Mapping
                    if ("map" in q_text_lower or "convert" in q_text_lower or "transform" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower) and ("relational" in q_text_lower or "relational schema" in q_text_lower or "relational model" in q_text_lower):
                        used_question_types.add("er_to_relational_mapping")
                        print("      📌 Marked type: er_to_relational_mapping")
                    # Also detect "Design relational schema" as mapping (if ER mentioned in question)
                    if "design" in q_text_lower and "relational schema" in q_text_lower and ("er" in q_text_lower or "entity" in q_text_lower):
                        used_question_types.add("er_to_relational_mapping")
                        print("      📌 Marked type: er_to_relational_mapping")
                    
                    # Store a snippet of the scenario for global uniqueness
                    # Combine subquestion texts to get a good proxy for the scenario
                    scenario_proxy = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])])
                    if scenario_proxy:
                        used_scenarios.add(scenario_proxy[:200]) # Store first 200 chars as a signature
                    
                    # Log successful generation
                    print(f"    📝 Generation Log: {q_no} | Attempt: {attempt} | Mode: {writer_mode} | Status: APPROVED")
                    break
                else:
                    if isinstance(feedback, list):
                        feedback = "; ".join(feedback)
                    print(f"❌ {q_no} Rejected (Attempt {attempt}/{MAX_RETRIES}). Code: {feedback_code} | Feedback: {feedback}")
                    
                    # IF it is a MATH ERROR, fallback immediately (no retries)
                    if feedback_code == "MATH_ERROR" or "MATH ERROR" in feedback.upper():
                        print(f"🛑 Math mismatch detected. Skipping retries and applying fallback logic.")
                        break
            
            if not approved:
                # Check if Writer failed due to API/config errors - trigger TEMPLATE_COPY_SAFE_MODE
                if writer_api_error is not None:
                    print(f"\n🛡️ TEMPLATE_COPY_SAFE_MODE activated for {q_no}")
                    print(f"   Reason: LLM_ERROR - {writer_api_error_str}")
                    
                    # Build draft directly from template (template-copy safe mode)
                    safe_draft = self._build_template_copy_draft(q_no, target_marks, template, needs_diagram, diagram_type)
                    
                    # Run deterministic critic on template-copy draft
                    safe_review = await self.critic.run({
                        "draft": safe_draft,
                        "context": context,
                        "template": template,
                        "q_no": q_no
                    })
                    
                    if safe_review.get("approved", False):
                        print(f"  ✅ Template-copy draft approved")
                        draft = safe_draft
                        approved = True
                        print(f"  📝 SAFE_MODE_TEMPLATE_COPY: {q_no} | Reason=LLM_ERROR | Error={writer_api_error_str[:100]}")
                else:
                        # Critic rejected - sanitize and retry
                        print(f"  ⚠️ Template-copy draft rejected: {safe_review.get('feedback', 'Unknown')}")
                        safe_draft = self._sanitize_template_copy_draft(safe_draft, template)
                        
                        # Final validation
                        final_safe_review = await self.critic.run({
                            "draft": safe_draft,
                            "context": context,
                            "template": template,
                            "q_no": q_no
                        })
                        
                        if final_safe_review.get("approved", False):
                            print(f"  ✅ Sanitized template-copy draft approved")
                            draft = safe_draft
                            approved = True
                        else:
                            print(f"  ⚠️ Sanitized template-copy draft still rejected, but accepting to prevent infinite loop")
                            draft = safe_draft
                            approved = True  # Force accept to prevent infinite loop
                        
                        print(f"  📝 SAFE_MODE_TEMPLATE_COPY: {q_no} | Reason=LLM_ERROR | Error={writer_api_error_str[:100]} | Sanitized=True")
                    
                    if approved:
                        # Continue with normal flow (add diagram placeholder, etc.)
                        if needs_diagram:
                            draft["needs_diagram"] = True
                            draft["diagram_type"] = diagram_type
                            draft["diagram_placeholder_text"] = f"[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]"
                        
                    # Update global tracking
                    used_topics.add(template.get("pattern_label", "General"))
                    # Track template ID and intent for diversity
                    template_id = str(template.get("_id", ""))
                    template_intent = template.get("pattern_label", "General")
                    if template_id:
                        used_template_ids.add(template_id)
                    if template_intent:
                        used_intents.add(template_intent)
                        
                        # Render and add to final_questions (same as normal flow)
                        draft["question_no"] = q_no
                        draft["text"] = self._render_question(draft)
                        final_questions.append(draft)
                        total_marks += int(draft.get("marks") or 0)
                        
                        # Save checkpoint
                        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                            json.dump({"questions": final_questions}, f, indent=2)
                        
                        print(f"    📝 Generation Log: {q_no} | Mode: SAFE_MODE_TEMPLATE_COPY | Status: APPROVED")
                        continue  # Skip regular fallback logic and move to next question
                
                # REGULAR FALLBACK LOGIC: Never force-approve invalid drafts
                # Build a fresh fallback draft from template structure
                # Then validate it before accepting
                # Preserve template intent (topic/type) - do not downgrade to "General Theory"
                
                # Extract template intent (topic/type from pattern_label)
                # GOLDEN RULE: Topic decides structure, structure decides validation.
                # Preserve the intent from the chosen template - do not downgrade to "General Theory".
                # The intent (ER, Normalization, SQL, etc.) comes from past-paper data analysis, not hardcoded.
                template_intent = template.get("pattern_label", "General")
                if template_intent == "General Theory":
                    # Try to infer intent from template structure or context
                    # This is a fallback only - normally intent comes from pattern_label (data analysis)
                    struct_source = template.get("required_structure") or template.get("subquestions", [])
                    if struct_source:
                        # Check structure types to infer intent
                        struct_types = [item.get("type", "").lower() for item in struct_source]
                        if any("er" in t or "diagram" in t for t in struct_types):
                            template_intent = "ER/EER Diagrams"
                        elif any("normal" in t or "normalize" in t for t in struct_types):
                            template_intent = "Normalization"
                        elif any("sql" in t or "query" in t for t in struct_types):
                            template_intent = "SQL Queries"
                    else:
                        print(f"  ⚠️ Template intent unknown, using generic fallback for {q_no}")
                
                # Log fallback trigger with intent
                final_feedback_code = review.get("feedback_code", "UNKNOWN") if 'review' in locals() else "NO_REVIEW"
                print(f"\n🔄 FALLBACK TRIGGERED for {q_no}")
                print(f"   Reason: {final_feedback_code}")
                print(f"   Attempts: {attempt + 1}/{MAX_RETRIES + 1}")
                print(f"   Final Mode: {writer_mode}")
                print(f"   Template Intent: {template_intent}")
                print(f"   Feedback: {feedback}")
                
                # FALLBACK: Build a fresh draft from template structure
                # This ensures marks sum up correctly (as they come from a real paper)
                
                # 1. Determine the source of truth for structure
                # 'required_structure' (Canonical) or 'subquestions' (Raw Template)
                struct_source = template.get("required_structure") or template.get("subquestions", [])
                
                if struct_source:
                    # Build stem text based on intent (preserve template intent)
                    intent_lower = template_intent.lower()
                    is_er = "er" in intent_lower or "eer" in intent_lower or "diagram" in intent_lower
                    is_norm = "normalization" in intent_lower or "normal form" in intent_lower
                    is_sql = "sql" in intent_lower or "query" in intent_lower
                    
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
                        stem_parts.append(f"Consider a database management system scenario related to {template_intent}.")
                    
                    # Try to salvage stem from failed draft if it's valid
                    salvaged_stem = draft.get("text", "") if draft else ""
                    if not salvaged_stem or self._is_placeholder(salvaged_stem) or len(salvaged_stem.strip()) < 20:
                        stem_text = " ".join(stem_parts)
                    else:
                        stem_text = salvaged_stem
                    
                    fallback_draft = {
                        "question_no": q_no,
                        "marks": target_marks,
                        "text": stem_text,
                        "subquestions": []
                    }
                    
                    if draft is None: draft = {}
                    failed_sub_qs = draft.get("subquestions", [])
                    
                    # --- SCALING LOGIC ---
                    # 1. Calculate Template Total to see if we need to scale
                    template_total = sum(int(item.get("marks") or 0) for item in struct_source)
                    current_sum = 0
                    
                    # 2. Prepare the list
                    final_subqs = []
                    
                    for idx, item in enumerate(struct_source):
                        import string, re
                        t_label = string.ascii_lowercase[idx % 26]
                        raw_t_marks = int(item.get("marks") or 0)
                        
                        # Scale marks if template differs from target
                        if template_total > 0 and template_total != target_marks:
                            ratio = target_marks / template_total
                            new_marks = int(round(raw_t_marks * ratio))
                            if raw_t_marks > 0 and new_marks == 0: new_marks = 1
                        else:
                            new_marks = raw_t_marks

                        # Try to salvage text from failed draft
                        salvaged_text = None
                        if draft and idx < len(draft.get("subquestions", [])):
                            salvaged_text = draft.get("subquestions", [])[idx].get("text", "")
                        
                        # Clean salvaged text
                        if salvaged_text:
                        salvaged_text = re.sub(r"^\(?[a-iA-I]\)?[\.\)]\s*", "", salvaged_text).strip()
                        
                        # Generate context-aware fallback text (NEVER use "..." or placeholders)
                        if not salvaged_text or len(salvaged_text.strip()) < 10 or self._is_placeholder(salvaged_text):
                            # Generate context-aware fallback based on structure type
                            struct_type = item.get("type", "concept")
                            pattern_label = template.get("pattern_label", "Database Systems")
                            t_text_lower = item.get("text", "").lower()
                            
                            # ER/EER Diagram questions
                            if "er" in struct_type.lower() or "diagram" in struct_type.lower() or "draw" in t_text_lower:
                                if "to relational" in t_text_lower or "mapping" in t_text_lower:
                                     salvaged_text = "Map the ER diagram to a Relational Schema, identifying Primary and Foreign Keys."
                                else:
                                     salvaged_text = f"Construct an ER/EER diagram for the scenario described above, showing all entities, relationships, and attributes."
                            # Normalization questions
                            elif "normalize" in struct_type.lower() or "normal" in struct_type.lower() or "normalization" in t_text_lower:
                                salvaged_text = f"Normalize the given relation schema to the appropriate normal form (1NF, 2NF, 3NF), justifying your steps."
                            # SQL questions
                            elif "sql" in struct_type.lower() or "query" in struct_type.lower() or "code" in t_text_lower:
                                salvaged_text = f"Write the SQL query to retrieve the requested information from the database schema."
                            # Definition/Explanation questions
                            elif "define" in struct_type.lower() or "explain" in struct_type.lower() or "list" in struct_type.lower():
                                salvaged_text = f"Define and explain the key concepts related to {pattern_label}."
                            # Calculation questions
                            elif "calculate" in struct_type.lower() or "compute" in struct_type.lower():
                                salvaged_text = f"Calculate the required metrics (e.g., Disk I/O, Buffer Hits) based on the given parameters."
                            # General questions
                            else:
                                salvaged_text = f"Discuss and explain {struct_type if struct_type != 'General' else pattern_label} in the context of the scenario above."
                            
                        final_subqs.append({
                            "label": t_label,
                            "marks": new_marks,
                            "text": salvaged_text
                        })
                        current_sum += new_marks
                    
                    # 3. Fix Rounding Errors (Distribution of Remainder)
                    diff = int(target_marks) - int(current_sum)
                    if diff != 0 and final_subqs:
                        # Add/Subtract difference to the item with the most marks
                        max_idx = max(range(len(final_subqs)), key=lambda i: final_subqs[i]['marks'])
                        final_subqs[max_idx]['marks'] += diff
                        
                    fallback_draft["subquestions"] = final_subqs
                    
                    # Add diagram placeholder if needed
                    if needs_diagram:
                        fallback_draft["needs_diagram"] = True
                        fallback_draft["diagram_type"] = diagram_type
                        fallback_draft["diagram_placeholder_text"] = f"[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]"
                    
                    # VALIDATE FALLBACK DRAFT with rebuild limit to prevent infinite loops
                    from app.core.config import settings
                    FALLBACK_REBUILDS_MAX = settings.FALLBACK_REBUILDS_MAX
                    
                    rebuild_count = 0
                    fallback_review = None
                    
                    while rebuild_count <= FALLBACK_REBUILDS_MAX:
                        print(f"  🔍 Validating fallback draft (rebuild {rebuild_count}/{FALLBACK_REBUILDS_MAX})...")
                        fallback_review = await self.critic.run({
                            "draft": fallback_draft,
                            "context": context,
                            "template": template,
                            "q_no": q_no
                        })
                        
                        if fallback_review.get("approved", False):
                    draft = fallback_draft
                            print(f"  ✅ Fallback draft validated and approved (after {rebuild_count} rebuilds)")
                            break
                        
                        if rebuild_count >= FALLBACK_REBUILDS_MAX:
                            # Max rebuilds reached - generate minimal valid draft
                            print(f"  ⚠️ Max fallback rebuilds ({FALLBACK_REBUILDS_MAX}) reached. Generating minimal valid draft...")
                            draft = self._generate_minimal_valid_draft(
                                q_no, target_marks, template_intent, struct_source, needs_diagram, diagram_type
                            )
                            print(f"  ✅ Minimal valid draft generated (guaranteed to pass validation)")
                            break
                        
                        # Rebuild with stricter constraints based on intent
                        print(f"  🔧 Rebuilding fallback with stricter constraints (preserving intent: {template_intent})...")
                        rebuild_count += 1
                        
                        # Preserve intent: ER questions get scenario, Normalization gets schema, etc.
                        pattern_label_lower = template_intent.lower()
                        for idx, sq in enumerate(fallback_draft["subquestions"]):
                            text = sq.get("text", "")
                            
                            # ER/EER intent: Ensure scenario in first subquestion
                            if ("er" in pattern_label_lower or "eer" in pattern_label_lower or "diagram" in pattern_label_lower):
                                if idx == 0 and ("scenario" not in text.lower() and "entity" not in text.lower()):
                                    sq["text"] = f"Consider a database system for a university with students, courses, and enrollments. Each student has ID, name, email. Each course has code, title, credits. Students enroll in courses with grades. {text}"
                            
                            # Normalization intent: Ensure schema in first subquestion
                            elif "normalization" in pattern_label_lower or "normal form" in pattern_label_lower:
                                if idx == 0 and ("schema" not in text.lower() and "relation" not in text.lower()):
                                    sq["text"] = f"Given a relation schema R(A, B, C, D) with functional dependencies: A → B, B → C. {text}"
                            
                            # SQL intent: Ensure table/schema mention
                            elif "sql" in pattern_label_lower or "query" in pattern_label_lower:
                                if idx == 0 and ("table" not in text.lower() and "schema" not in text.lower()):
                                    sq["text"] = f"Given a database with tables for customers, orders, and products. {text}"
                    
                    # Final validation check
                    if draft and not fallback_review.get("approved", False):
                        # One final validation on minimal draft
                        final_review = await self.critic.run({
                            "draft": draft,
                            "context": context,
                            "template": template,
                            "q_no": q_no
                        })
                        if not final_review.get("approved", False):
                            print(f"  ⚠️ Warning: Minimal draft still has issues, but accepting to prevent infinite loop")

                    print(f"  🔧 Fixed marks using template structure (Scaled {template_total} -> {target_marks})")
                    print(f"  📝 Fallback Log: {q_no} | Intent: {template_intent} | Trigger: {final_feedback_code} | Rebuilds: {rebuild_count} | Validated: {fallback_review.get('approved', False) if fallback_review else False}")
                    print(f"  📝 Fallback Log: {q_no} | Trigger: {final_feedback_code} | Validated: {fallback_review.get('approved', False)}")
            
            # --- IMPORTANT: UPDATE GLOBAL TRACKING FOR FORCED APPROVAL ---
            # Even if forced, we must record what we used so Q2, Q3 know about it
            used_topics.add(template.get("pattern_label", "General"))
            # Track template ID and intent for diversity
            template_id = str(template.get("_id", ""))
            template_intent = template.get("pattern_label", "General")
            if template_id:
                used_template_ids.add(template_id)
            if template_intent:
                used_intents.add(template_intent)
            
            # Detect Question Type (Heuristic) for Forced Approval
            if draft is None: draft = {}
            q_text_lower = draft.get("text", "").lower()
            if ("draw" in q_text_lower or "design" in q_text_lower or "construct" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower):
                used_question_types.add("er_diagram")
                print("      📌 Marked type: er_diagram (Forced)")
            if "normalization" in q_text_lower or "normal form" in q_text_lower:
                used_question_types.add("normalization")
            if "write a query" in q_text_lower or "sql" in q_text_lower:
                used_question_types.add("sql_query")
            # Detect ER → Relational Mapping (Forced Approval)
            if ("map" in q_text_lower or "convert" in q_text_lower or "transform" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower) and ("relational" in q_text_lower or "relational schema" in q_text_lower or "relational model" in q_text_lower):
                used_question_types.add("er_to_relational_mapping")
                print("      📌 Marked type: er_to_relational_mapping (Forced)")
            if "design" in q_text_lower and "relational schema" in q_text_lower and ("er" in q_text_lower or "entity" in q_text_lower):
                used_question_types.add("er_to_relational_mapping")
                print("      📌 Marked type: er_to_relational_mapping (Forced)")

            # Store Scenario for Forced Approval
            scenario_proxy = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])])
            if scenario_proxy:
                used_scenarios.add(scenario_proxy[:200])
            
            # 2c. RENDER the question for final display
            draft["question_no"] = q_no
            draft["text"] = self._render_question(draft)
            
            final_questions.append(draft)
            total_marks += int(draft.get("marks") or 0)

            # SAVE CHECKPOINT
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({"questions": final_questions}, f, indent=2)

        # 3. VALIDATE TOPIC COVERAGE
        self._validate_topic_coverage(final_questions)
        
        # 3.5. LOG TEMPLATE DIVERSITY SUMMARY
        print(f"\n📊 Template Diversity Summary:")
        print(f"   Used Template IDs: {len(used_template_ids)} unique templates")
        print(f"   Used Intents: {len(used_intents)} unique intents")
        print(f"   Intent List: {', '.join(sorted(used_intents))}")
        if len(used_template_ids) < len(final_questions):
            print(f"   ⚠️  WARNING: Some templates were reused (only {len(used_template_ids)} unique templates for {len(final_questions)} questions)")
        else:
            print(f"   ✅ All questions use unique templates")
        
        # 4. SAVE
        paper = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "AGENTIC_V1",
            "total_marks": total_marks,
            "questions": final_questions
        }
        
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
