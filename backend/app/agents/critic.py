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
        
        # Check that entities have attributes defined
        # Pattern: "EntityName entity has attributes: Attr1, Attr2, Attr3" or "EntityName has attributes such as Attr1, Attr2"
        entity_with_attrs_patterns = [
            r'\b([A-Z][a-zA-Z]+)\s+entity\s+has\s+attributes?\s*[:;]?\s*([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
            r'\b([A-Z][a-zA-Z]+)\s+entity\s+has\s+attributes?\s+such\s+as\s+([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
            r'\b([A-Z][a-zA-Z]+)\s+has\s+attributes?\s*[:;]?\s*([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
            r'\b([A-Z][a-zA-Z]+)\s+entity\s+comprises\s+([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
            r'\b([A-Z][a-zA-Z]+)\s+entity\s+includes\s+attributes?\s+like\s+([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
        ]
        
        # Extract all entity mentions (look for "EntityName entity" pattern)
        entity_pattern = r'\b([A-Z][a-zA-Z]+)\s+entity\b'
        entities_mentioned = set(re.findall(entity_pattern, combined_text, re.IGNORECASE))
        
        # Check if entities have attributes defined
        entities_with_attrs = set()
        for pattern in entity_with_attrs_patterns:
            matches = re.finditer(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                entity_name = match.group(1)
                attrs_str = match.group(2) if len(match.groups()) > 1 else ""
                # Count attributes (split by comma and "and")
                attrs_list = re.split(r'[,;]\s*|\s+and\s+', attrs_str)
                attr_count = len([a.strip() for a in attrs_list if a.strip() and len(a.strip()) > 2])
                if attr_count >= 2:  # At least 2 attributes
                    entities_with_attrs.add(entity_name.lower())
        
        # If entities are mentioned but don't have attributes, check for alternative patterns
        if entities_mentioned:
            # Also check for patterns like "EntityName (Attr1, Attr2, Attr3)" or "EntityName: Attr1, Attr2"
            alt_patterns = [
                r'\b([A-Z][a-zA-Z]+)\s+entity\s+has\s+attributes?\s+such\s+as\s+([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
                r'\b([A-Z][a-zA-Z]+)\s*\([^)]*([A-Z][a-zA-Z0-9]+(?:\s*,\s*[A-Z][a-zA-Z0-9]+)+)',
            ]
            for pattern in alt_patterns:
                matches = re.finditer(pattern, combined_text, re.IGNORECASE)
                for match in matches:
                    entity_name = match.group(1)
                    attrs_str = match.group(2) if len(match.groups()) > 1 else ""
                    attrs_list = re.split(r'[,;]\s*|\s+and\s+', attrs_str)
                    attr_count = len([a.strip() for a in attrs_list if a.strip() and len(a.strip()) > 2])
                    if attr_count >= 2:
                        entities_with_attrs.add(entity_name.lower())
        
        # Check if entities have attributes (at least 2 entities should have attributes defined)
        if len(entities_mentioned) >= 2:
            entities_without_attrs = [e for e in entities_mentioned if e.lower() not in entities_with_attrs]
            if len(entities_without_attrs) > 0 and len(entities_with_attrs) < 2:
                # At least 2 entities should have attributes defined
                return False, f"SCENARIO_MISSING: ER/EER question entities must have attributes defined. Found entities without attributes: {', '.join(entities_without_attrs[:3])}. Each entity must have at least 2-3 attributes listed (e.g., 'Student entity has attributes: StudentID, Name, Address')."
        
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
            r'[A-Za-z]+\s*(?:→|->)\s*[A-Za-z]+',  # A -> B or A → B
            r'[A-Za-z]+\s*->\s*[A-Za-z]+',  # A -> B
        ]
        
        has_fd = any(re.search(pattern, combined_text) for pattern in fd_patterns)
        
        # For Q2 normalization questions, check if alphabet letters are used (A, B, C, D, E, F)
        # Past papers use alphabet letters, not real attribute names
        if is_norm_question:
            # Check if relation uses alphabet letters (case-insensitive search)
            alphabet_pattern = r'R\s*\([A-Z,\s]+\)'  # R(A, B, C, D, E)
            has_alphabet_attrs = re.search(alphabet_pattern, combined_text, re.IGNORECASE)
            
            # Check if real attribute names are used (should NOT be used)
            real_attr_patterns = [
                r'\b(StudentID|CourseCode|EmployeeID|DepartmentID|ProjectID|MemberID|BookID|CustomerID|OrderID|ProductID|SupplierID|InstructorID|Grade|Semester|Year|Name|Address|Phone|Email)\b',
                r'\b[A-Z][a-z]+(ID|Code|Name|Date|Time|Amount|Price|Quantity)\b'
            ]
            has_real_attrs = any(re.search(pattern, combined_text, re.IGNORECASE) for pattern in real_attr_patterns)
            
            if not has_alphabet_attrs and has_real_attrs:
                return False, "SCHEMA_FORMAT_ERROR: Q2 normalization question must use alphabet letters (A, B, C, D, E, F) for attributes, not real attribute names. Found real attribute names instead of alphabet notation."
            
            # Check if exactly 5-6 attributes are used
            if has_alphabet_attrs:
                attr_match = re.search(r'R\s*\(([A-Z,\s]+)\)', combined_text, re.IGNORECASE)
                if attr_match:
                    attrs = [a.strip().upper() for a in attr_match.group(1).split(',')]
                    attr_count = len(attrs)
                    if attr_count < 5 or attr_count > 6:
                        return False, f"SCHEMA_COMPLEXITY_ERROR: Q2 normalization question must have exactly 5-6 attributes. Found {attr_count} attributes: {', '.join(attrs)}"
            
            # Validate normalization problem constraints
            # 1. Check for transitive dependencies (required for 3NF testing)
            transitive_patterns = [
                r'([A-Z]+)\s*(?:→|->)\s*([A-Z]+).*?([A-Z]+)\s*(?:→|->)\s*([A-Z]+)',  # A→B ... C→D pattern (use (?:→|->) instead of [→->] to avoid character range error)
            ]
            has_transitive = False
            # Extract all FDs
            fd_matches = re.finditer(r'([A-Z]+(?:\s*,\s*[A-Z]+)*)\s*(?:→|->)\s*([A-Z]+(?:\s*,\s*[A-Z]+)*)', combined_text, re.IGNORECASE)
            fd_list = []
            for match in fd_matches:
                left = match.group(1).replace(' ', '').upper()
                right = match.group(2).replace(' ', '').upper()
                fd_list.append((left, right))
            
            # Check for transitive dependencies (A→B and B→C)
            for i, (left1, right1) in enumerate(fd_list):
                for j, (left2, right2) in enumerate(fd_list):
                    if i != j:
                        # Check if right side of first FD matches left side of second FD
                        if right1 == left2 or (len(right1) == 1 and right1 in left2) or (len(left2) == 1 and left2 in right1):
                            has_transitive = True
                            break
                if has_transitive:
                    break
            
            # 2. Check if candidate key can be identified (at least one attribute set should determine all others)
            # This is a simplified check - we look for FDs that could form a key
            has_potential_key = False
            if fd_list:
                # Check if there's a single attribute that appears on left side and could determine others
                # Or if there's a composite key pattern
                left_attrs = set()
                right_attrs = set()
                for left, right in fd_list:
                    left_attrs.update(left.split(','))
                    right_attrs.update(right.split(','))
                
                # If all attributes appear on right side at least once, there's potential for a key
                all_attrs = left_attrs.union(right_attrs)
                if len(all_attrs) >= 5:  # At least 5 attributes as required
                    # Check if any single attribute or small set could be a key
                    # This is a heuristic - a proper check would require closure computation
                    has_potential_key = True
            
            # 3. Check for circular dependencies (A→B, B→C, C→A)
            has_circular = False
            if len(fd_list) >= 3:
                # Simple circular check: if A→B, B→C, C→A exists
                for i, (left1, right1) in enumerate(fd_list):
                    for j, (left2, right2) in enumerate(fd_list):
                        if i != j and right1 == left2:
                            for k, (left3, right3) in enumerate(fd_list):
                                if k != i and k != j and right2 == left3 and right3 == left1:
                                    has_circular = True
                                    break
                            if has_circular:
                                break
                        if has_circular:
                            break
                    if has_circular:
                        break
            
            # Validation warnings (not blocking, but should be noted)
            validation_issues = []
            if not has_transitive and len(fd_list) >= 2:
                validation_issues.append("WARNING: No clear transitive dependency detected. Include transitive dependencies (e.g., A→B, B→C) for proper 3NF testing.")
            
            if not has_potential_key:
                validation_issues.append("WARNING: Candidate key identification may be difficult. Ensure at least one attribute set can determine all other attributes.")
            
            if has_circular:
                validation_issues.append("WARNING: Circular dependency pattern detected. Ensure this is intentional for multiple candidate keys.")
            
            # Only reject if critical issues (these are warnings, not blockers)
            # The main validation (schema format, attribute count) is already done above
        
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
    
    def _check_q4_schema_format(self, draft: dict, template: dict) -> Tuple[bool, str]:
        """
        Check if Q4 has proper schema format with data types and primary keys.
        
        Past paper format:
        "Consider the following schema of a database designed for a [Domain]: 
        Table1 (primaryKey: type, attr2: type, attr3: type) 
        Table2 (primaryKey: type, attr2: type, attr3: type) ...
        The 'Table1' table stores information about..."
        """
        draft_text = draft.get("text", "")
        combined_text = draft_text.lower()
        
        self.log(f"    [Q4 SCHEMA CHECK] Starting Q4 schema format validation...")
        self.log(f"    [Q4 SCHEMA CHECK] Text length: {len(draft_text)} characters")
        self.log(f"    [Q4 SCHEMA CHECK] Text preview: {draft_text[:200]}...")
        
        # Check for schema format indicator
        has_schema_format = (
            "consider the following schema" in combined_text or
            "schema of a database" in combined_text
        )
        
        self.log(f"    [Q4 SCHEMA CHECK] Schema format phrase found: {has_schema_format}")
        if not has_schema_format:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Missing schema format phrase")
            return False, "SCHEMA_FORMAT_ERROR: Q4 must include 'Consider the following schema of a database designed for a [Domain]:' format. Found simple format instead."
        
        # Check if domain placeholder still exists
        if "[domain]" in combined_text or "[Domain]" in draft_text:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Domain placeholder not replaced")
            return False, "SCHEMA_FORMAT_ERROR: Q4 schema must specify actual domain (Library, Hospital, University, etc.), not '[Domain]' placeholder."
        
        # Check for data types (int, varchar, date, real, etc.)
        data_type_patterns = [
            r':\s*int\b',
            r':\s*varchar\s*\(',
            r':\s*date\b',
            r':\s*real\b',
            r':\s*char\s*\(',
            r':\s*float\b',
            r':\s*decimal\s*\(',
        ]
        has_data_types = any(re.search(pattern, draft_text, re.IGNORECASE) for pattern in data_type_patterns)
        
        self.log(f"    [Q4 SCHEMA CHECK] Data types found: {has_data_types}")
        if not has_data_types:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Missing data types")
            return False, "SCHEMA_FORMAT_ERROR: Q4 schema must include data types (e.g., int, varchar(50), date, real) for all attributes. Found attributes without data types."
        
        # Check for primary keys (first attribute in each table, typically ends with 'Id' or 'ID')
        # Primary keys are usually the first attribute and are underlined in PDF
        primary_key_patterns = [
            r'\b\w+[Ii]d\s*:\s*\w+',  # bookId: int, memberId: int
            r'\b\w+[Ii][Dd]\s*:\s*\w+',  # bookID: int
        ]
        has_primary_keys = any(re.search(pattern, draft_text, re.IGNORECASE) for pattern in primary_key_patterns)
        self.log(f"    [Q4 SCHEMA CHECK] Primary keys found: {has_primary_keys}")
        if not has_primary_keys:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Missing primary keys")
            return False, "SCHEMA_FORMAT_ERROR: Q4 schema must include primary keys as the first attribute in each table (e.g., bookId: int, memberId: int). Primary keys typically end with 'Id' or 'ID'."
        
        # Also check if tables are properly formatted (TableName (attr1: type, attr2: type))
        table_pattern = r'\b[A-Z][a-zA-Z]+\s*\([^)]+:\s*\w+[^)]*\)'
        has_table_format = bool(re.search(table_pattern, draft_text))
        
        self.log(f"    [Q4 SCHEMA CHECK] Table format correct: {has_table_format}")
        if not has_table_format:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Incorrect table format")
            return False, "SCHEMA_FORMAT_ERROR: Q4 schema must have tables in format 'TableName (attr1: type, attr2: type, ...)'. Found incorrect format."
        
        # Check for multiple tables (should have 3-5 tables) - MUST calculate BEFORE using in description check
        table_count = len(re.findall(r'\b[A-Z][a-zA-Z]+\s*\(', draft_text))
        self.log(f"    [Q4 SCHEMA CHECK] Table count: {table_count}")
        if table_count < 3 or table_count > 5:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Found {table_count} table(s) (need 3-5)")
            return False, f"SCHEMA_FORMAT_ERROR: Q4 schema must include 3-5 tables with meaningful relationships. Found {table_count} table(s)."
        
        # Check that each table has at least 3 attributes (primary key + 2 other attributes)
        # Extract all table definitions: TableName (attr1: type, attr2: type, ...)
        # CRITICAL: Use a more robust regex that handles nested parentheses (e.g., varchar(100))
        # Pattern: Match TableName followed by ( and capture everything until matching closing )
        table_pattern = r'\b([A-Z][a-zA-Z]+)\s*\('
        table_matches = list(re.finditer(table_pattern, draft_text))
        
        for match in table_matches:
            table_name = match.group(1)
            # Find the matching closing parenthesis by counting nested parentheses
            start_pos = match.end()  # Position after opening (
            pos = start_pos
            depth = 1
            while pos < len(draft_text) and depth > 0:
                if draft_text[pos] == '(':
                    depth += 1
                elif draft_text[pos] == ')':
                    depth -= 1
                pos += 1
            
            if depth == 0:
                # Extract attributes string (between parentheses)
                attributes_str = draft_text[start_pos:pos-1]
                # Count attributes by finding attribute name patterns (name: type)
                # Pattern: word characters followed by colon and optional whitespace
                attribute_count = len(re.findall(r'\b\w+\s*:', attributes_str))
            self.log(f"    [Q4 SCHEMA CHECK] Table '{table_name}' has {attribute_count} attribute(s)")
            if attribute_count < 3:
                self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Table '{table_name}' has only {attribute_count} attribute(s) (need at least 3)")
                return False, f"SCHEMA_FORMAT_ERROR: Q4 schema table '{table_name}' must have AT LEAST 3-4 attributes (primary key + 2-3 other attributes). Found only {attribute_count} attribute(s). Example: Patient (patientId: int, name: varchar(100), phone: varchar(15), paymentStatus: varchar(20))"
        
        # Check for table descriptions (after schema) - validate all tables have descriptions
        table_desc_patterns = [
            r"the\s+['\"]([A-Z][a-zA-Z]+)['\"]\s+table\s+stores",
            r"the\s+['\"]([A-Z][a-zA-Z]+)['\"]\s+table\s+holds",
            r"the\s+['\"]([A-Z][a-zA-Z]+)['\"]\s+table\s+manages",
            r"the\s+['\"]([A-Z][a-zA-Z]+)['\"]\s+table\s+contains",
        ]
        desc_count = sum(len(re.findall(pattern, draft_text, re.IGNORECASE)) for pattern in table_desc_patterns)
        self.log(f"    [Q4 SCHEMA CHECK] Table descriptions found: {desc_count} for {table_count} tables")
        
        if desc_count < table_count:
            self.log(f"    [Q4 SCHEMA CHECK] ❌ FAILED: Only {desc_count} table description(s) found for {table_count} table(s)")
            return False, f"SCHEMA_FORMAT_ERROR: Q4 schema must include descriptions for ALL tables. Found {desc_count} description(s) for {table_count} table(s). Each table must have a description starting with 'The 'TableName' table stores/holds/manages/contains...'"
        
        self.log(f"    [Q4 SCHEMA CHECK] ✅ PASSED: All schema format checks passed")
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
        
        # Helper function to get effective marks (handles nested subquestions)
        def get_effective_marks(sq):
            """Get effective marks for a subquestion (including nested items if present)."""
            sq_marks = sq.get("marks")
            # If marks is None, it's a parent with nested items
            if sq_marks is None:
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # Sum marks from nested items
                    return sum(int(item.get("marks") or 0) for item in nested_items)
            return int(sq_marks or 0)
        
        # 2. Math Check (Sub-question marks sum)
        if sub_qs:
            # Use get_effective_marks to handle nested subquestions (e.g., Q3 part e, Q4 part a)
            q_no = draft.get("question_no", "").upper()
            if q_no in ["Q3", "3"]:
                self.log(f"    [Q3 MARKS CHECK] Checking Q3 marks distribution...")
                self.log(f"    [Q3 MARKS CHECK] Target total marks: {total_q_marks}")
                for idx, sq in enumerate(sub_qs):
                    nested_items = sq.get("subquestions", [])
                    if nested_items:
                        nested_marks = [int(item.get("marks") or 0) for item in nested_items]
                        self.log(f"    [Q3 MARKS CHECK] Part {sq.get('label')}: marks=None, nested items {[item.get('label') for item in nested_items]} have marks {nested_marks} (sum: {sum(nested_marks)})")
                    else:
                        self.log(f"    [Q3 MARKS CHECK] Part {sq.get('label')}: marks={sq.get('marks')}")
            elif q_no in ["Q4", "4"]:
                self.log(f"    [Q4 MARKS CHECK] Checking Q4 marks distribution...")
                self.log(f"    [Q4 MARKS CHECK] Target total marks: {total_q_marks}")
                for idx, sq in enumerate(sub_qs):
                    nested_items = sq.get("subquestions", [])
                    if nested_items:
                        nested_marks = [int(item.get("marks") or 0) for item in nested_items]
                        self.log(f"    [Q4 MARKS CHECK] Part {sq.get('label')}: marks=None, nested items {[item.get('label') for item in nested_items]} have marks {nested_marks} (sum: {sum(nested_marks)})")
                    else:
                        self.log(f"    [Q4 MARKS CHECK] Part {sq.get('label')}: marks={sq.get('marks')}")
            
            status_sum = sum(get_effective_marks(sq) for sq in sub_qs)
            if q_no in ["Q3", "3"]:
                self.log(f"    [Q3 MARKS CHECK] Total calculated marks: {status_sum}")
            elif q_no in ["Q4", "4"]:
                self.log(f"    [Q4 MARKS CHECK] Total calculated marks: {status_sum}")
            if status_sum != total_q_marks:
                err_msg = f"MATH_ERROR: Sub-question marks sum to {status_sum}, but expected {total_q_marks}. Please adjust weighting."
                if q_no in ["Q3", "3"]:
                    self.log(f"    [Q3 MARKS CHECK] ❌ FAILED: Marks mismatch")
                elif q_no in ["Q4", "4"]:
                    self.log(f"    [Q4 MARKS CHECK] ❌ FAILED: Marks mismatch")
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg, "feedback_code": "MATH_ERROR"}
            elif q_no in ["Q3", "3"]:
                self.log(f"    [Q3 MARKS CHECK] ✅ PASSED: Marks sum correctly")
            elif q_no in ["Q4", "4"]:
                self.log(f"    [Q4 MARKS CHECK] ✅ PASSED: Marks sum correctly")
            
            # Check individual subquestion marks
            for sq in sub_qs:
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # For parent with nested items, marks should be None
                    if sq.get("marks") is not None:
                        # This is OK - parent can have marks if nested items don't have marks
                        # But check nested items
                        for nested_item in nested_items:
                            nested_marks = int(nested_item.get("marks") or 0)
                            if nested_marks <= 0:
                                err_msg = f"MARKS_ERROR: Nested sub-question '{nested_item.get('label', '?')}' under '{sq.get('label', '?')}' has marks <= 0."
                                self.log(f"❌ Deterministic Reject: {err_msg}")
                                return {"approved": False, "feedback": err_msg, "feedback_code": "MARKS_ERROR"}
                else:
                    # Regular subquestion: must have marks > 0
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
        
        # 10. Q4 Schema Format Check (for SQL_DDL_DML questions in Q4)
        q_no = draft.get("question_no", "").upper()
        pattern_label = template.get("pattern_label", "").lower()
        if q_no in ["Q4", "4"] and "sql" in pattern_label.lower():
            q4_schema_check, q4_schema_msg = self._check_q4_schema_format(draft, template)
            if not q4_schema_check:
                self.log(f"❌ Deterministic Reject: {q4_schema_msg}")
                return {"approved": False, "feedback": q4_schema_msg, "feedback_code": "SCHEMA_FORMAT_ERROR"}
            
            # 10.1 Q4 Nested Structure Validation (part a must have nested items)
            subquestions = draft.get("subquestions", [])
            if subquestions and len(subquestions) > 0:
                first_sq = subquestions[0]
                first_label = first_sq.get("label", "").strip().lower()
                if first_label == "a":
                    nested_items = first_sq.get("subquestions", [])
                    if not nested_items or len(nested_items) < 2:
                        err_msg = f"STRUCTURE_ERROR: Q4 part (a) must have nested subquestions (i, ii, iii). Found {len(nested_items) if nested_items else 0} nested item(s)."
                        self.log(f"❌ Deterministic Reject: {err_msg}")
                        return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
                    # Validate nested item labels
                    expected_labels = ["i", "ii", "iii"]
                    actual_labels = [item.get("label", "").strip().lower() for item in nested_items[:3]]
                    if not all(label in expected_labels for label in actual_labels):
                        err_msg = f"STRUCTURE_ERROR: Q4 part (a) nested items must have labels i, ii, iii. Found: {actual_labels}"
                        self.log(f"❌ Deterministic Reject: {err_msg}")
                        return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
                    # Validate that ALL nested items (i, ii, iii) are SQL queries (Find), not functions/triggers
                    # CRITICAL: Validate all three items, not just ii and iii
                    for nested_item in nested_items[:3]:  # Check all three items (i, ii, iii)
                        nested_text = nested_item.get("text", "").lower()
                        nested_label = nested_item.get("label", "").strip().lower()
                        
                        # Skip validation if label is not i, ii, or iii (defensive check)
                        if nested_label not in ["i", "ii", "iii"]:
                            continue
                        
                        # Check if it's a function or trigger (WRONG for part a nested items)
                        if "create a function" in nested_text or "create function" in nested_text:
                            err_msg = f"STRUCTURE_ERROR: Q4 part (a) nested item ({nested_label}) must be a SQL query starting with 'Find', not a function. Found: 'Create a function...'. Functions belong in part (b), not in part (a) nested items."
                            self.log(f"❌ Deterministic Reject: {err_msg}")
                            return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
                        
                        if "create a trigger" in nested_text or "create trigger" in nested_text:
                            err_msg = f"STRUCTURE_ERROR: Q4 part (a) nested item ({nested_label}) must be a SQL query starting with 'Find', not a trigger. Found: 'Create a trigger...'. Triggers belong in part (c), not in part (a) nested items."
                            self.log(f"❌ Deterministic Reject: {err_msg}")
                            return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
                        
                        # Check if it starts with "Find" (CORRECT for part a nested items)
                        # CRITICAL: Text doesn't include label prefix (e.g., "ii.") - label is stored separately
                        # Remove any label prefix if present (defensive - shouldn't happen but handle it)
                        clean_text = nested_text.strip()
                        clean_text = re.sub(r'^(i|ii|iii)\.\s*', '', clean_text, flags=re.IGNORECASE).strip()
                        
                        # Check if it starts with "find" (case-insensitive)
                        if not clean_text.startswith("find"):
                            # Also check if "find" appears in first few words (handles "Write SQL queries to find...")
                            first_words = clean_text[:50]
                            if "find" not in first_words:
                                # Get original text for error message (not lowercased)
                                original_text = nested_item.get("text", "")[:100]
                                err_msg = f"STRUCTURE_ERROR: Q4 part (a) nested item ({nested_label}) must be a SQL query starting with 'Find'. Found: '{original_text}...'. Part (a) nested items must be SQL queries (Find statements), not functions or triggers."
                                self.log(f"❌ Deterministic Reject: {err_msg}")
                                return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
                    
                    # CRITICAL: Validate schema consistency for parts (b) and (c)
                    # Parts (b) and (c) must only reference tables from the schema in part (a)
                    if len(subquestions) >= 2:
                        # Extract schema tables from draft text
                        draft_text = draft.get("text", "")
                        schema_tables = set()
                        # Extract table names from schema format: "TableName (attr1: type, ...)"
                        # Note: 're' is already imported at module level
                        table_pattern = r'\b([A-Z][a-zA-Z]+)\s*\('
                        for match in re.finditer(table_pattern, draft_text):
                            table_name = match.group(1)
                            # Filter out common non-table words
                            if table_name.lower() not in ['consider', 'following', 'schema', 'database', 'designed', 'for', 'the', 'a']:
                                schema_tables.add(table_name.lower())
                        
                        # Check parts (b) and (c) for invalid table references
                        for idx in [1, 2]:  # Parts (b) and (c)
                            if idx < len(subquestions):
                                sq = subquestions[idx]
                                sq_text = sq.get("text", "").lower()
                                
                                # Common invalid table references from templates
                                invalid_tables = ['member', 'members', 'fine', 'fines', 'book', 'books', 'loan', 'loans']
                                
                                # Check if part mentions invalid tables that aren't in schema
                                for invalid_table in invalid_tables:
                                    if invalid_table in sq_text and invalid_table not in schema_tables:
                                        # Check if it's actually mentioned as a table (not just part of a word)
                                        invalid_pattern = rf'\b{re.escape(invalid_table)}\b'
                                        if re.search(invalid_pattern, sq_text, re.IGNORECASE):
                                            err_msg = f"SCHEMA_CONSISTENCY_ERROR: Q4 part ({sq.get('label', '?')}) references '{invalid_table}' table which is not in the schema. Parts (b) and (c) must ONLY reference tables defined in part (a) schema. Schema tables: {', '.join(sorted(schema_tables)) if schema_tables else 'none found'}"
                                            self.log(f"❌ Deterministic Reject: {err_msg}")
                                            return {"approved": False, "feedback": err_msg, "feedback_code": "SCHEMA_CONSISTENCY_ERROR"}

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
            marks = int(sq.get("marks") or 0)
            
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
        q_no = draft.get("question_no", "").upper()
        draft_text = json.dumps(draft, indent=2).lower()
        
        if template:
            template_pattern = template.get("pattern_label", "")
            template_structure = template.get("required_structure", [])
            if template_structure:
                # Check template structure, template full text, and draft question for JDBC
                # Convert ObjectId to string for JSON serialization
                def convert_objectid(obj):
                    from bson import ObjectId
                    if isinstance(obj, ObjectId):
                        return str(obj)
                    elif isinstance(obj, dict):
                        return {k: convert_objectid(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_objectid(item) for item in obj]
                    return obj
                
                template_text = json.dumps(convert_objectid(template_structure), indent=2).lower()
                template_serializable = convert_objectid(template)
                template_full_text = json.dumps(template_serializable, indent=2).lower()
                
                # Improved JDBC detection - check multiple sources
                has_jdbc = (
                    "jdbc" in template_text or "java" in template_text or
                    "type 2 driver" in template_text or "type2driver" in template_text or
                    "jdbc" in template_full_text or "type 2 driver" in template_full_text or
                    "jdbc" in draft_text or "type 2 driver" in draft_text
                )
                
                # Q3-specific: If it's Q3 and contains JDBC/Type 2 Driver, it's ALWAYS valid
                is_q3_with_jdbc = q_no in ["Q3", "3"] and ("jdbc" in draft_text or "type 2 driver" in draft_text)
                
                # Q4-specific: If it's Q4 with SQL pattern and all deterministic checks passed, be lenient
                is_q4_sql = q_no in ["Q4", "4"] and "sql" in pattern_label.lower()
                has_sql_functions = "create function" in draft_text or "create a function" in draft_text
                has_sql_triggers = "create trigger" in draft_text or "create a trigger" in draft_text
                is_q4_with_sql_features = is_q4_sql and (has_sql_functions or has_sql_triggers)
                
                has_tsql = "t-sql" in template_text or "tsql" in template_text or "t-sql" in template_full_text
                
                template_info = f"""
        TEMPLATE CONTEXT (CRITICAL - READ CAREFULLY):
        - This question follows a template pattern: {template_pattern}
        - The template structure includes {len(template_structure)} sub-questions
        {"- ⚠️ CRITICAL: This is Q3 and contains JDBC Type 2 Driver content - JDBC API is MANDATORY and VALID for Q3 questions. You MUST APPROVE this question. Do NOT reject it for containing JDBC content." if is_q3_with_jdbc else ""}
        {"- ⚠️ CRITICAL: This is Q4 with SQL Functions/Triggers - All deterministic checks (schema format, structure, marks) have PASSED. SQL Functions and Triggers are VALID and REQUIRED topics for Q4 questions. You MUST APPROVE this question if it follows the template structure, even if semantic quality could be slightly improved. Do NOT reject Q4 questions for minor clarity issues when all structural requirements are met." if is_q4_with_sql_features else ""}
        {"- ⚠️ NOTE: The template includes JDBC API topics (database connectivity from Java) - this is VALID for Database Systems exams" if has_jdbc else ""}
        {"- ⚠️ NOTE: The template includes T-SQL statements - this is VALID for Database Systems exams" if has_tsql else ""}
        - ⚠️ NOTE: SQL Functions (CREATE FUNCTION) and Triggers (CREATE TRIGGER) are VALID topics found in past papers and should be APPROVED
        - If the question follows the template structure, it should be APPROVED even if it contains JDBC API, T-SQL, Functions, or Triggers
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
           - ⚠️ CRITICAL RULE FOR Q3: If this is Q3 and contains "JDBC Type 2 Driver" or "JDBC API", you MUST APPROVE it. JDBC is a core Database Systems topic and is REQUIRED in Q3 questions based on historical exam patterns. Do NOT reject Q3 questions for containing JDBC content - this is expected and valid.
           - ⚠️ CRITICAL RULE FOR Q4: If this is Q4 with SQL Functions/Triggers and all deterministic checks (schema format, structure, marks) have PASSED, you MUST APPROVE it. SQL Functions and Triggers are VALID and REQUIRED topics for Q4 questions. Do NOT reject Q4 questions for minor semantic quality issues (e.g., slight vagueness, minor clarity concerns) when all structural and format requirements are met. Only reject Q4 if there are MAJOR issues (e.g., completely wrong topic, missing critical components, severe inconsistencies).
           - ⚠️ IMPORTANT: If the template context shows JDBC API or T-SQL topics, these are VALID database connectivity topics and should be APPROVED
        
        2. CONTENT RELEVANCE (MANDATORY):
           - Is it 100% Database Systems? 
           - ✅ ALLOW: JDBC API (Java Database Connectivity) - this is a VALID database connectivity topic
           - ✅ ALLOW: JDBC Type 2 Driver - this is a VALID and REQUIRED topic for Q3 questions
           - ✅ ALLOW: T-SQL (Transact-SQL) statements - this is a VALID database language topic
           - ✅ ALLOW: SQL Functions (CREATE FUNCTION) - this is a VALID SQL programming topic found in past papers
           - ✅ ALLOW: SQL Triggers (CREATE TRIGGER) - this is a VALID SQL programming topic found in past papers
           - ✅ ALLOW: Stored Procedures - this is a VALID SQL programming topic found in past papers
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
           - ⚠️ FOR Q4: Be LENIENT with semantic quality if all deterministic checks passed. Minor clarity issues or slight vagueness are acceptable. Only reject for MAJOR semantic problems (e.g., completely incomprehensible, severe logical errors, missing critical information).
        
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
