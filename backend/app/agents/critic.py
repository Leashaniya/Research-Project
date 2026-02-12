import json
import re
from typing import Tuple
from difflib import SequenceMatcher
from app.core.config import settings
from app.core.llm_factory import get_llm_client
from .base import BaseAgent  # Ensure BaseAgent is imported or mock it for script run

class QualityCritic(BaseAgent):
    """
    The Quality Critic Agent (Reviewer).
    Role: Review draft questions for quality, relevance, and hallucination.
    Using OpenAI GPT-4o-mini.
    """

    def __init__(self, config=None):
        super().__init__(name="Quality Critic", config=config)
        self.api_key = settings.OPENAI_API_KEY
        # Always use OpenAI (Azure is not used)
        self.model_name = settings.OPENAI_MODEL or "gpt-4o-mini"
        provider_name = "openai"
        
        try:
             self.client = get_llm_client()
             self.log(f"Initialized LLM ({provider_name}): {self.model_name}")
        except Exception as e:
             self.log(f"Failed to initialize LLM: {e}")
             self.client = None

    def _normalize_text(self, text: str) -> str:
        """Normalize text for similarity comparison: lowercase, strip punctuation, collapse whitespace."""
        if not text:
            return ""
        # Lowercase
        text = text.lower()
        # Remove punctuation, keep alphanumeric and spaces
        text = re.sub(r'[^\w\s]', '', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _check_duplicate_subquestions(self, sub_qs: list) -> Tuple[bool, str]:
        """Check for duplicate/near-duplicate subquestions using similarity matching."""
        normalized_texts = []
        for sq in sub_qs:
            text = sq.get("text", "").strip()
            if text:
                normalized = self._normalize_text(text)
                normalized_texts.append((normalized, text))
        
        # Check for exact duplicates (after normalization)
        seen = set()
        for norm_text, orig_text in normalized_texts:
            if norm_text in seen:
                return True, f"DUPLICATE_SUBQUESTIONS: Found duplicate subquestion text: '{orig_text[:50]}...'"
            seen.add(norm_text)
        
        # Check for high similarity (SequenceMatcher ratio >= 0.85)
        for i in range(len(normalized_texts)):
            for j in range(i + 1, len(normalized_texts)):
                norm1, orig1 = normalized_texts[i]
                norm2, orig2 = normalized_texts[j]
                similarity = SequenceMatcher(None, norm1, norm2).ratio()
                if similarity >= 0.85:
                    return True, f"DUPLICATE_SUBQUESTIONS: Subquestions have {similarity:.2%} similarity: '{orig1[:50]}...' vs '{orig2[:50]}...'"
                
                # Check if one is contained in another
                if norm1 in norm2 or norm2 in norm1:
                    if len(norm1) > 20 and len(norm2) > 20:  # Only flag if both are substantial
                        return True, f"DUPLICATE_SUBQUESTIONS: One subquestion is contained in another: '{orig1[:50]}...' vs '{orig2[:50]}...'"
        
        return False, ""

    def _check_placeholder_content(self, text: str) -> bool:
        """Check if text contains placeholders or is empty/punctuation only."""
        if not text or not text.strip():
            return True
        
        text_lower = text.lower().strip()
        
        # Check for placeholder patterns
        # Use word boundaries for short patterns to avoid false positives (e.g., "na" in "name")
        placeholder_patterns_word_boundary = [
            r'\btbd\b', r'\bna\b', r'\btba\b',  # Standalone words only
            r'\bn/a\b', r'\bfill in\b', r'\badd here\b'
        ]
        
        placeholder_patterns_substring = [
            "...", "to be added", "[insert", "[placeholder", 
            "to be determined"
        ]
        
        # Check word-boundary patterns (standalone words)
        for pattern in placeholder_patterns_word_boundary:
            if re.search(pattern, text_lower):
                return True
        
        # Check substring patterns (exact matches)
        for pattern in placeholder_patterns_substring:
            if pattern in text_lower:
                return True
        
        # Check if text is only punctuation/whitespace
        if not re.search(r'[a-zA-Z0-9]', text):
            return True
        
        return False

    def _check_er_scenario_required(self, draft: dict, template: dict) -> Tuple[bool, str]:
        """
        Check if ER/EER question has required scenario block.
        
        GOLDEN RULE: Structure decides validation. This check only applies if the topic
        (pattern_label) indicates ER/EER. The topic comes from data analysis, not question number.
        
        Uses robust deterministic rules (not strict sentence count):
        - Minimum length (chars or tokens)
        - Entity-like terms (2+ distinct)
        - Relationship indicators (1+)
        Accepts bullet scenarios and short paragraphs if informative.
        """
        from app.core.config import settings
        
        pattern_label = template.get("pattern_label", "").lower()
        draft_text = draft.get("text", "").lower()
        sub_qs_text = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])]).lower()
        combined_text = (draft_text + " " + sub_qs_text)
        combined_text_lower = combined_text.lower()
        
        # Check if this is an ER/EER/diagram question
        is_er_question = (
            "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label or
            "er diagram" in combined_text_lower or "eer diagram" in combined_text_lower or
            ("draw" in combined_text_lower and ("er" in combined_text_lower or "entity" in combined_text_lower))
        )
        
        if not is_er_question:
            return True, ""  # Not an ER question, skip check
        
        # Check minimum length (chars or approximate tokens)
        char_count = len(combined_text.strip())
        # Approximate tokens: split by whitespace and punctuation
        token_count = len(re.findall(r'\b\w+\b', combined_text))
        
        if char_count < settings.MIN_SCENARIO_CHARS and token_count < settings.MIN_SCENARIO_TOKENS:
            return False, f"SCENARIO_MISSING: ER/EER question scenario is too short ({char_count} chars, {token_count} tokens). Minimum: {settings.MIN_SCENARIO_CHARS} chars or {settings.MIN_SCENARIO_TOKENS} tokens."
        
        # Check for entity-like terms (2+ distinct)
        # Look for capitalized words (likely entity names) or common entity keywords
        entity_keywords = [
            "entity", "entities", "student", "course", "book", "member", "customer",
            "employee", "department", "product", "order", "invoice", "account",
            "branch", "loan", "author", "publisher", "library", "hospital", "bank",
            "university", "company", "organization", "system"
        ]
        
        # Find capitalized words (potential entity names)
        capitalized_words = set(re.findall(r'\b[A-Z][a-z]+\b', combined_text))
        # Find entity keywords
        found_entity_keywords = [kw for kw in entity_keywords if kw in combined_text_lower]
        
        # Count distinct entity-like terms
        entity_terms = capitalized_words | set(found_entity_keywords)
        entity_count = len(entity_terms)
        
        # Check for relationship indicators
        relationship_indicators = [
            "has", "contains", "enrolls", "belongs", "assigned", "manages", "relates",
            "borrows", "lends", "purchases", "sells", "works", "studies", "teaches",
            "owns", "rents", "reserves", "issues", "receives", "sends"
        ]
        
        relationship_count = sum(1 for indicator in relationship_indicators if indicator in combined_text_lower)
        
        # Validation: Require at least 2 entity-like terms and 1 relationship indicator
        if entity_count < 2:
            return False, f"SCENARIO_MISSING: ER/EER question must include at least 2 distinct entity-like terms. Found: {entity_count} ({list(entity_terms)[:5]})."
        
        if relationship_count < 1:
            return False, f"SCENARIO_MISSING: ER/EER question must include at least 1 relationship indicator (e.g., 'has', 'contains', 'enrolls'). Found: {relationship_count}."
        
        return True, ""

    def _check_normalization_schema_required(self, draft: dict, template: dict) -> Tuple[bool, str]:
        """Check if Normalization question has required schema and functional dependencies."""
        pattern_label = template.get("pattern_label", "").lower()
        draft_text = draft.get("text", "").lower()
        sub_qs_text = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])]).lower()
        combined_text = (draft_text + " " + sub_qs_text).lower()
        
        # Check if this is a normalization question
        is_norm_question = (
            "normalization" in pattern_label or "normal form" in pattern_label or
            "normalization" in combined_text or "normal form" in combined_text or
            ("normalize" in combined_text and ("relation" in combined_text or "schema" in combined_text))
        )
        
        if not is_norm_question:
            return True, ""  # Not a normalization question, skip check
        
        # Check for relation schema (R(A,B,C) or explicit attributes)
        schema_patterns = [
            r'R\s*\([A-Za-z,\s]+\)',  # R(A, B, C)
            r'relation\s+[A-Za-z]+\s*\(',  # relation R(
            r'attributes?\s*[:=]\s*[A-Za-z,\s]+',  # attributes: A, B, C
            r'schema\s*[:=]\s*[A-Za-z,\s]+',  # schema: A, B, C
        ]
        
        has_schema = any(re.search(pattern, combined_text) for pattern in schema_patterns)
        
        # Check for functional dependencies
        fd_patterns = [
            r'functional\s+dependenc',  # functional dependency
            r'fd\s*[:=]',  # FD:
            r'[A-Za-z]+\s*→\s*[A-Za-z]+',  # A -> B
            r'[A-Za-z]+\s*->\s*[A-Za-z]+',  # A -> B
        ]
        
        has_fd = any(re.search(pattern, combined_text) for pattern in fd_patterns)
        
        if not has_schema:
            return False, "SCHEMA_MISSING: Normalization question must include a relation schema (e.g., R(A,B,C) or explicit attributes). Current text lacks schema definition."
        
        if not has_fd:
            return False, "SCHEMA_MISSING: Normalization question must include functional dependencies (FDs). Current text lacks functional dependency definitions."
        
        return True, ""

    def _check_relational_algebra_schema_required(self, draft: dict, template: dict) -> Tuple[bool, str]:
        """Check if Relational Algebra question has required schema with relations and attributes."""
        pattern_label = template.get("pattern_label", "").lower()
        draft_text = draft.get("text", "")
        sub_qs_text = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])])
        combined_text = (draft_text + " " + sub_qs_text).lower()
        
        # Check if this is a relational algebra question
        # Fix: Add parentheses to ensure correct operator precedence
        is_rel_algebra_question = (
            "relational algebra" in pattern_label or "relational_algebra" in pattern_label or
            "tuple calculus" in pattern_label or
            (("relational algebra" in combined_text or "tuple calculus" in combined_text) and
             ("express" in combined_text or "query" in combined_text or "find" in combined_text))
        )
        
        if not is_rel_algebra_question:
            return True, ""  # Not a relational algebra question, skip check
        
        # Check for relation schemas in the format: relation_name (attr1, attr2, attr3)
        # Look for patterns like: "passenger (pid, pname, pgender, pcity)"
        relation_patterns = [
            r'[a-z_]+\s*\([a-z0-9_,\s]+\)',  # relation_name (attr1, attr2, attr3)
            r'[A-Z][a-z]+\s*\([a-z0-9_,\s]+\)',  # RelationName (attr1, attr2)
        ]
        
        # Count how many relations are defined
        relation_count = 0
        for pattern in relation_patterns:
            matches = re.findall(pattern, draft_text)
            relation_count += len(matches)
        
        # Also check for explicit relation definitions in text
        if "relation" in combined_text and "(" in draft_text:
            # Count lines that look like relation definitions
            lines = draft_text.split('\n')
            for line in lines:
                line_lower = line.lower().strip()
                if '(' in line and ')' in line and any(keyword in line_lower for keyword in ['relation', 'table', 'schema']):
                    relation_count += 1
        
        # Relational algebra questions should have at least 2-3 relations
        if relation_count < 2:
            return False, "SCHEMA_MISSING: Relational algebra question must include a complete relational schema with at least 2-3 relations and their attributes listed explicitly (e.g., 'passenger (pid, pname, pgender, pcity)', 'booking (pid, aid, fid, fdate)'). Current text lacks sufficient relation definitions."
        
        return True, ""

    def _check_reference_above(self, draft: dict) -> Tuple[bool, str]:
        """Check if 'described above' / 'as shown above' references exist without actual content."""
        draft_text = draft.get("text", "").lower()
        sub_qs = draft.get("subquestions", [])
        
        # Collect all text
        all_text = draft_text
        for sq in sub_qs:
            all_text += " " + sq.get("text", "").lower()
        
        # Check for reference phrases
        reference_phrases = [
            "described above", "as shown above", "diagram above", "refer to above",
            "shown above", "mentioned above", "as above", "above scenario", "above diagram"
        ]
        
        for phrase in reference_phrases:
            if phrase in all_text:
                # Check if stem contains substantial content (scenario/schema/diagram)
                stem_has_content = (
                    len(draft_text) > 100 or  # Substantial stem text
                    "scenario" in draft_text or
                    "schema" in draft_text or
                    "relation" in draft_text or
                    "diagram" in draft_text or
                    "entity" in draft_text
                )
                
                if not stem_has_content:
                    return False, f"REFERENCE_ERROR: Question references '{phrase}' but stem does not contain the referenced content (scenario/schema/diagram)."
        
        return True, ""

    async def run(self, input_data: dict) -> dict:
        """
        Input: {
            "draft": {...},
            "context": "...",
            "template": {...}
        }
        
        Returns: {"approved": bool, "feedback": str, "feedback_code": str}
        """
        draft = input_data.get("draft", {})
        context = input_data.get("context", "")
        template = input_data.get("template", {})
        
        # --- DETERMINISTIC HARD-FAIL RULES (Run BEFORE LLM review) ---
        
        # 0. Check question stem for empty/placeholder
        question_stem = draft.get("text", "").strip()
        if self._check_placeholder_content(question_stem):
            err_msg = "EMPTY_STEM: Question stem is empty, contains placeholders, or is punctuation only."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg, "feedback_code": "EMPTY_STEM"}
        
        # 1. Marks Check
        total_q_marks = int(draft.get("marks") or 0)
        if total_q_marks <= 0:
            err_msg = "MARKS_ERROR: Question must have marks > 0."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg, "feedback_code": "MARKS_ERROR"}
        
        sub_qs = draft.get("subquestions", [])
        
        # 2. Math Check (Sub-question marks sum)
        if sub_qs:
            status_sum = sum(int(sq.get("marks") or 0) for sq in sub_qs)
            if status_sum != total_q_marks:
                err_msg = f"MATH_ERROR: Sub-question marks sum to {status_sum}, but expected {total_q_marks}. Please adjust weighting."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg, "feedback_code": "MATH_ERROR"}
            
            # Check individual subquestion marks
            for sq in sub_qs:
                sq_marks = int(sq.get("marks") or 0)
                if sq_marks <= 0:
                    err_msg = f"MARKS_ERROR: Sub-question '{sq.get('label', '?')}' has marks <= 0."
                    self.log(f"❌ Deterministic Reject: {err_msg}")
                    return {"approved": False, "feedback": err_msg, "feedback_code": "MARKS_ERROR"}
        
        # 3. Structure Count Check (If template exists)
        required_struct = template.get("required_structure") or template.get("subquestions", [])
        if required_struct and len(sub_qs) != len(required_struct):
            err_msg = f"STRUCTURE_ERROR: Generated {len(sub_qs)} sub-questions, but template requires EXACTLY {len(required_struct)}. Please follow the required structure."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
        
        # 4. Check for empty/placeholder subquestions
        for sq in sub_qs:
            text = sq.get("text", "").strip()
            if self._check_placeholder_content(text):
                err_msg = f"EMPTY_SUBQUESTION: Sub-question '{sq.get('label', '?')}' is empty, contains placeholders (e.g., '...', 'TBD'), or is punctuation only."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg, "feedback_code": "EMPTY_SUBQUESTION"}
            
            # Check for minimum length
            if len(text) < 10:
                err_msg = f"EMPTY_SUBQUESTION: Sub-question '{sq.get('label', '?')}' text is too short (minimum 10 characters)."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg, "feedback_code": "EMPTY_SUBQUESTION"}
        
        # 5. Check for duplicate/near-duplicate subquestions
        if len(sub_qs) > 1:
            is_duplicate, dup_msg = self._check_duplicate_subquestions(sub_qs)
            if is_duplicate:
                self.log(f"❌ Deterministic Reject: {dup_msg}")
                return {"approved": False, "feedback": dup_msg, "feedback_code": "DUPLICATE_SUBQUESTIONS"}
        
        # 6. Check for "described above" / "as shown above" without content
        ref_check, ref_msg = self._check_reference_above(draft)
        if not ref_check:
            self.log(f"❌ Deterministic Reject: {ref_msg}")
            return {"approved": False, "feedback": ref_msg, "feedback_code": "REFERENCE_ERROR"}
        
        # 7. ER/EER Scenario Check
        er_check, er_msg = self._check_er_scenario_required(draft, template)
        if not er_check:
            self.log(f"❌ Deterministic Reject: {er_msg}")
            return {"approved": False, "feedback": er_msg, "feedback_code": "SCENARIO_MISSING"}
        
        # 8. Normalization Schema Check
        norm_check, norm_msg = self._check_normalization_schema_required(draft, template)
        if not norm_check:
            self.log(f"❌ Deterministic Reject: {norm_msg}")
            return {"approved": False, "feedback": norm_msg, "feedback_code": "SCHEMA_MISSING"}
        
        # 9. Relational Algebra Schema Check
        rel_algebra_check, rel_algebra_msg = self._check_relational_algebra_schema_required(draft, template)
        if not rel_algebra_check:
            self.log(f"❌ Deterministic Reject: {rel_algebra_msg}")
            return {"approved": False, "feedback": rel_algebra_msg, "feedback_code": "SCHEMA_MISSING"}

        # 9. Figure Placeholders & Hallucinations Check
        draft_str = json.dumps(draft).lower()
        # EXCEPTION: We explicitly ALLOW "[DIAGRAM PLACEHOLDER]" as per new rule.
        clean_draft_str = draft_str.replace("[diagram placeholder]", "").replace("[placeholder figure]", "")

        # Diagrams/tooling are disabled by updated rules (text-only model).
        # Reject any Mermaid/Graphviz/Kroki output or mermaid_code fields.
        diagram_tooling_markers = [
            "```mermaid",
            "mermaid_code",
            "erdiagram",
            "graph td",
            "graphviz",
            "kroki.io",
        ]
        if any(m in clean_draft_str for m in diagram_tooling_markers):
            err_msg = "DIAGRAM_TOOLING_DISABLED: Mermaid/Graphviz/Kroki/diagram code is not allowed. Use plain text only."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg, "feedback_code": "DIAGRAM_TOOLING_DISABLED"}
        
        hallucination_keywords = ["[figure:", "slide ", "slide_", "fig_", "page ", "page_", "refer to figure", "shown in figure"]
        
        if any(kw in clean_draft_str for kw in hallucination_keywords):
            err_msg = "HALLUCINATION_ERROR: Hallucinated figure placeholder (other than '[DIAGRAM PLACEHOLDER]'), slide reference, or diagram reference found. You MUST describe the content in text or create a scenario."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg, "feedback_code": "HALLUCINATION_ERROR"}
        
        # 10. Additional Content Quality Checks
        for sq in sub_qs:
            text = sq.get("text", "").strip()
            marks = int(sq.get("marks", 0))
            
            # 10.1 NO Vague/Subjective questions
            if any(v in text.lower() for v in ["think of", "what do you think", "your opinion", "personally"]):
                err_msg = "QUALITY_ERROR: Question is subjective or vague (e.g. 'Can you think of...'). Must be a technical, objective exam question."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg, "feedback_code": "QUALITY_ERROR"}
            
            # 10.2 Mark-to-effort mismatch (e.g. 1 mark for huge explanation)
            # NOTE: Allow "Briefly explain" even with 2 marks, as this is a valid pattern from templates
            # Only reject if it's "explain" without "briefly" AND the question is long AND marks are low
            # BUT: Check if template has "Briefly explain" pattern - if so, this is a critical error
            if marks <= 2 and ("explain" in text.lower() and "briefly" not in text.lower()) and len(text) > 100:
                # Check if this might be a template pattern violation (should be "Briefly explain")
                err_msg = f"QUALITY_ERROR: Mark mismatch. You have {marks} marks for a potentially complex question. This appears to be missing 'Briefly' qualifier - if the template pattern says 'Briefly explain', you MUST use 'Briefly explain' exactly. Simplify or increase marks."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg, "feedback_code": "QUALITY_ERROR"}
            
            # 10.3 DATABASE SYSTEMS RELEVANCE CHECK (CRITICAL)
            # NOTE: "deadlock" is a VALID database systems topic (transaction management/concurrency control)
            # NOTE: "semaphore" and "mutex" are OS concepts but can appear in DB concurrency discussions
            # NOTE: "process" is REMOVED - can legitimately appear in DB contexts (e.g., "transaction processing", "database processes")
            non_db_keywords = [
                "frame bytes", "frame bytes time", "network protocol", "tcp/ip", "http", "https",
                "routing", "switching", "packet", "datagram", "osi model", "network layer",
                "transport layer", "application layer", "socket", "port number", "dns",
                "dhcp", "subnet", "gateway", "router", "switch", "firewall", "vpn",
                "operating system", "process scheduling", "memory management", "file system",
                "cpu scheduling", "semaphore", "mutex", "thread",
                "compiler", "interpreter", "syntax", "parsing", "lexical analysis",
                "software engineering", "agile", "scrum", "waterfall", "sdlc",
                "web development", "html", "css", "javascript", "frontend", "backend",
                "machine learning", "neural network", "deep learning", "ai algorithm"
            ]
            
            text_lower = text.lower()
            for non_db_term in non_db_keywords:
                if non_db_term in text_lower:
                    err_msg = f"RELEVANCE_ERROR: Question contains non-database systems topic '{non_db_term}'. This is a Database Systems exam."
                    self.log(f"❌ Deterministic Reject: {err_msg}")
                    return {"approved": False, "feedback": err_msg, "feedback_code": "RELEVANCE_ERROR"}

        # --- LLM AUDIT (Only if deterministic checks pass) ---
        # All hard-fail conditions have been checked above.
        # LLM review is for semantic quality, not structural validation.
        
        # Extract template context to inform the reviewer about expected patterns
        template_info = ""
        if template:
            template_pattern = template.get("pattern_label", "")
            template_structure = template.get("required_structure", [])
            if template_structure:
                # Check if template contains JDBC or T-SQL patterns
                template_text = json.dumps(template_structure, indent=2).lower()
                has_jdbc = "jdbc" in template_text or "java" in template_text
                has_tsql = "t-sql" in template_text or "tsql" in template_text
                
                template_info = f"""
        TEMPLATE CONTEXT (IMPORTANT):
        - This question follows a template pattern: {template_pattern}
        - The template structure includes {len(template_structure)} sub-questions
        {"- ⚠️ NOTE: The template includes JDBC API topics (database connectivity from Java) - this is VALID for Database Systems exams" if has_jdbc else ""}
        {"- ⚠️ NOTE: The template includes T-SQL statements - this is VALID for Database Systems exams" if has_tsql else ""}
        - If the question follows the template structure, it should be APPROVED even if it contains JDBC API or T-SQL topics
        """
        
        prompt = f"""
        You are a strict Exam Quality Reviewer for a Database Systems exam.
        Review this Draft Question: {json.dumps(draft, indent=2)}
        Reference Material: {context}
        {template_info}
        
        ⚠️ CRITICAL REVIEW CRITERIA ⚠️
        
        1. SYLLABUS ALIGNMENT (MANDATORY):
           - Is the question STRICTLY based on historical exam patterns?
           - Does it align with past exam content and curriculum requirements?
           - Does it reflect ONLY core Database Management Systems syllabus content?
           - REJECT if it introduces topics unrelated to core syllabus or past paper patterns
           - REJECT if it deviates from historical exam question styles
           - ⚠️ IMPORTANT: If the template context shows JDBC API or T-SQL topics, these are VALID database connectivity topics and should be APPROVED
        
        2. CONTENT RELEVANCE (MANDATORY):
           - Is it 100% Database Systems? 
           - ✅ ALLOW: JDBC API (Java Database Connectivity) - this is a VALID database connectivity topic
           - ✅ ALLOW: T-SQL (Transact-SQL) statements - this is a VALID database language topic
           - ✅ ALLOW: Database connectivity APIs, SQL statements, database administration tasks
           - REJECT if it contains networking topics (TCP/IP, routing, packets, OSI model, etc.)
           - REJECT if it contains OS topics (CPU scheduling, process scheduling, memory management, etc.)
           - REJECT if it contains web development (HTML, CSS, JavaScript, etc.)
           - REJECT if it contains compiler design (parsing, lexical analysis, etc.)
           - REJECT if it contains software engineering methodologies (Agile, Scrum, etc.)
           - REJECT if it contains ML/AI topics (neural networks, deep learning, etc.)
           - REJECT if it contains ANY topic NOT in Database Management Systems curriculum
        
        3. HISTORICAL PATTERN ALIGNMENT:
           - Does it follow the structure and style of past exam questions?
           - Does it match the difficulty level of historical questions?
           - REJECT if it introduces concepts or approaches not found in past papers
        
        4. NO HALLUCINATIONS:
           - REJECT phantom slide references
           - REJECT references to non-existent figures or content
        
        5. SCENARIO COMPLETENESS:
           - REJECT if missing scenario text for "Design" tasks
           - Ensure all required context is provided
        
        6. SEMANTIC QUALITY:
           - Ensure questions are clear, unambiguous, and academically appropriate
           - Ensure questions match the academic level of past papers
        
        Output JSON:
        {{
            "approved": true/false,
            "feedback": "Detailed explanation of approval/rejection reason, focusing on syllabus alignment and historical pattern compliance"
        }}
        """
        
        try:
            if not self.client:
                # If LLM unavailable, approve if deterministic checks passed
                self.log("⚠️ LLM unavailable, approving based on deterministic checks only.")
                return {"approved": True, "feedback": "Approved (deterministic checks passed, LLM unavailable)", "feedback_code": "LLM_UNAVAILABLE"}
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            # Ensure feedback_code is present
            if "feedback_code" not in data:
                data["feedback_code"] = "LLM_REVIEW"
            return data
        except Exception as e:
            self.log(f"Error reviewing question with OpenAI: {e}")
            # Do NOT auto-approve on LLM failure - deterministic checks already passed
            # Return approved=True but with warning
            return {"approved": True, "feedback": f"Approved (deterministic checks passed, LLM review failed: {e})", "feedback_code": "LLM_ERROR"}
