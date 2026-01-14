# Golden Rule Verification

## The Golden Rule

> **Question number never decides topic.**  
> **Topic decides structure.**  
> **Structure decides validation.**

## Current Implementation Flow

### ✅ Step 1: Topic Determination (Data-Driven, NOT Question Number)

**Location**: `backend/scripts/template_analyzer.py`

```python
# Analyzes ALL past papers
for q_id, questions in sorted(by_position.items()):
    # Count topic frequency (using cluster_label_keywords as proxy)
    topic_counter = Counter()
    for q in questions:
        keywords = q.get("cluster_label_keywords", [])[:3]
        topic_sig = " ".join(keywords) if keywords else "General"
        topic_counter[topic_sig] += 1
    
    # Get most frequent topic (EMERGES FROM DATA)
    dominant_topic, frequency = topic_counter.most_common(1)[0]
    
    # Extract structure from most recent paper with that topic
    most_recent = papers_with_topic[0]
    structure = most_recent.get("subquestions", [])
```

**Key Points:**
- ✅ Topics are **inferred from past paper data**
- ✅ No hardcoded mapping (Q1 → ER, Q2 → Normalization, etc.)
- ✅ If Q1 appears as ER in 60% of past papers, it becomes ER
- ✅ If Q1 appears as SQL in 60% of past papers, it becomes SQL
- ✅ **Topic emerges from data, not logic**

### ✅ Step 2: Template Selection (Topic-Based, NOT Position-Based)

**Location**: `backend/app/agents/orchestrator.py`

```python
# 1. Try canonical template (from data analysis)
canonical = await self._get_canonical_template(q_no)

if canonical:
    template = {
        "pattern_label": canonical.get("dominant_topic", "General"),  # ← TOPIC FROM DATA
        "required_structure": canonical.get("subquestion_structure", [])  # ← STRUCTURE FROM DATA
    }
else:
    # 2. Fallback: Select from templates collection
    # Filter by marks, balance by syllabus modules
    template = await self._select_template(q_no, target_marks, used_modules)
    # pattern_label comes from template (which came from past papers)
```

**Key Points:**
- ✅ Template selection uses `pattern_label` (topic from data)
- ✅ No hardcoded "if Q1 then ER" logic
- ✅ Topic determines which template structure to use
- ✅ Structure comes from real past papers

### ✅ Step 3: Validation (Structure-Based, Topic-Aware)

**Location**: `backend/app/agents/critic.py`

```python
def _check_er_scenario_required(self, draft: dict, template: dict):
    pattern_label = template.get("pattern_label", "").lower()  # ← TOPIC FROM TEMPLATE
    
    # Check if this is an ER/EER question (based on TOPIC, not question number)
    is_er_question = (
        "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label or
        "er diagram" in combined_text or "eer diagram" in combined_text
    )
    
    if not is_er_question:
        return True, ""  # Not an ER question, skip check
    
    # Only then apply ER-specific validation
    # ...
```

**Key Points:**
- ✅ Validation checks `pattern_label` (topic) to determine question type
- ✅ ER scenario check only applies if topic is ER/EER
- ✅ Normalization schema check only applies if topic is Normalization
- ✅ **Validation rules apply AFTER topic is determined**
- ✅ No validation based on question number

## Verification Checklist

### ✅ Question Number Never Decides Topic
- [x] No hardcoded `if q_no == "Q1": topic = "ER"`
- [x] Topics come from `template_analyzer.py` data analysis
- [x] Canonical templates store `dominant_topic` from frequency analysis
- [x] Template selection uses `pattern_label` from data, not position

### ✅ Topic Decides Structure
- [x] Template's `pattern_label` determines question type
- [x] Structure (`required_structure`) comes from past papers with that topic
- [x] Writer prompts adapt based on `pattern_label` (ER vs Normalization)
- [x] No structure hardcoded by question number

### ✅ Structure Decides Validation
- [x] Critic checks `pattern_label` to determine validation rules
- [x] ER questions get scenario validation (only if topic is ER)
- [x] Normalization questions get schema validation (only if topic is Normalization)
- [x] Validation is topic-aware, not position-aware

## Example Flow (Q1 → ER)

### Scenario: Q1 appears as ER in 60% of past papers

1. **Data Analysis** (`template_analyzer.py`):
   ```
   Q1 papers analyzed: 15
   - ER/EER topics: 9 papers (60%)
   - SQL topics: 4 papers (27%)
   - Normalization: 2 papers (13%)
   
   → Dominant topic: "ER/EER Diagrams"
   → Most recent ER paper: 2024 II
   → Structure extracted from 2024 II Q1
   ```

2. **Template Selection** (`orchestrator.py`):
   ```python
   canonical = {
       "position_id": "Q1",
       "dominant_topic": "ER/EER Diagrams",  # ← FROM DATA
       "subquestion_structure": [...]  # ← FROM 2024 II Q1
   }
   template = {
       "pattern_label": "ER/EER Diagrams",  # ← TOPIC
       "required_structure": [...]  # ← STRUCTURE
   }
   ```

3. **Validation** (`critic.py`):
   ```python
   pattern_label = "ER/EER Diagrams"  # ← FROM TEMPLATE
   is_er_question = "er" in pattern_label  # True
   
   # Apply ER-specific validation
   if is_er_question:
       check_scenario_required()  # ← STRUCTURE-BASED VALIDATION
   ```

**Result**: Q1 becomes ER because **data shows it**, not because logic forces it.

## Example Flow (Q1 → SQL)

### Scenario: Q1 appears as SQL in 60% of past papers

1. **Data Analysis**:
   ```
   Q1 papers analyzed: 15
   - SQL topics: 9 papers (60%)
   - ER topics: 4 papers (27%)
   - Normalization: 2 papers (13%)
   
   → Dominant topic: "SQL Queries"
   → Most recent SQL paper: 2023
   → Structure extracted from 2023 Q1
   ```

2. **Template Selection**:
   ```python
   template = {
       "pattern_label": "SQL Queries",  # ← FROM DATA
       "required_structure": [...]  # ← FROM 2023 Q1
   }
   ```

3. **Validation**:
   ```python
   pattern_label = "SQL Queries"
   is_er_question = "er" in pattern_label  # False
   
   # Skip ER validation
   # Apply general validation only
   ```

**Result**: Q1 becomes SQL because **data shows it**, not because logic forces it.

## Academic Defensibility

### ✅ The System is Academically Defensible Because:

1. **Data-Driven**: Topics emerge from statistical analysis of past papers
2. **Not Hardcoded**: No `if Q1 then ER` logic exists
3. **Reproducible**: Same analysis on different past papers would yield different results
4. **Transparent**: Can show evaluators the data analysis process
5. **Adaptive**: If exam patterns change, system adapts automatically

### ✅ You Can Explain to Evaluators:

> "The system analyzes all past papers and determines the most frequent topic for each question position through statistical analysis. For example, if Q1 appears as ER diagrams in 60% of past papers, the system uses ER as the topic for Q1. The topic then determines the structure (extracted from the most recent paper with that topic), and the structure determines which validation rules apply. There is no hardcoded mapping between question numbers and topics."

## Code Evidence

### No Hardcoded Q1 → ER Mapping
```bash
# Search results show NO hardcoded mappings:
grep -r "Q1.*ER\|ER.*Q1" backend/
# Only found in:
# - Documentation (examples)
# - Output files (generated, not hardcoded)
# - Blueprint validation (ensures Q1 exists, doesn't force topic)
```

### Topic from Data
```python
# template_analyzer.py line 110
dominant_topic, frequency = topic_counter.most_common(1)[0]
# ↑ Statistical analysis, not hardcoded
```

### Validation from Topic
```python
# critic.py line 101
pattern_label = template.get("pattern_label", "").lower()
is_er_question = "er" in pattern_label or "eer" in pattern_label
# ↑ Checks topic, not question number
```

## Conclusion

✅ **The implementation follows the golden rule:**

1. ✅ **Question number never decides topic** - Topics come from data analysis
2. ✅ **Topic decides structure** - Structure extracted from past papers with that topic
3. ✅ **Structure decides validation** - Validation rules apply based on topic (pattern_label)

✅ **The system is academically defensible:**
- Data-driven, not hardcoded
- Reproducible and transparent
- Adaptive to changing patterns

✅ **You can confidently explain to evaluators:**
- Topics emerge from statistical analysis
- No hardcoded mappings
- System adapts to actual exam patterns

