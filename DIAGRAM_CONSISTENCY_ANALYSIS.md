# ER/EER Diagram Consistency Analysis

## Current Behavior: **Diagrams VARY Each Time**

### Why Diagrams Are Different Each Generation:

1. **Writer Agent (Question Generation)**
   - **Temperature**: Not explicitly set → Uses GPT default (~1.0)
   - **Result**: Each generation produces different question text
   - **Location**: `backend/app/agents/writer.py` line 62-66
   ```python
   response = self.client.chat.completions.create(
       model=self.model_name,
       messages=[{"role": "user", "content": prompt}],
       response_format={"type": "json_object"}
       # No temperature parameter = uses default (~1.0)
   )
   ```

2. **Semantic Description Extraction**
   - The semantic description is extracted from the **generated question text**
   - Since question text varies, semantic description varies
   - **Location**: `backend/app/agents/orchestrator.py` ~line 1440-1520

3. **Diagram Parsing (Deterministic)**
   - **Temperature**: `0.1` (very low, almost deterministic)
   - **Location**: `backend/app/services/semantic_diagram_service.py` line 165
   - **BUT**: Input (semantic description) varies, so output varies

### Flow:
```
Writer (temp ~1.0) 
  → Generates different question text each time
  → Extracts semantic description from question
  → Diagram Parser (temp 0.1) 
  → Parses varying description
  → Generates different diagram
```

## Impact:

- **Q1 ER/EER Diagram**: Will be **different** each time you generate a paper
- **Entities**: May vary (e.g., Student/Course vs Employee/Department)
- **Relationships**: May vary (e.g., Enrolls vs Works)
- **Attributes**: May vary
- **ISA Hierarchies**: May vary (if applicable)

## Options to Make Diagrams Consistent:

### Option 1: Make Writer Deterministic (Recommended)
Set `temperature=0` for Writer to get same questions each time:
```python
response = self.client.chat.completions.create(
    model=self.model_name,
    messages=[{"role": "user", "content": prompt}],
    response_format={"type": "json_object"},
    temperature=0  # Fully deterministic
)
```

### Option 2: Add Seed Control
Add a seed parameter to control randomness:
```python
response = self.client.chat.completions.create(
    model=self.model_name,
    messages=[{"role": "user", "content": prompt}],
    response_format={"type": "json_object"},
    seed=42  # Fixed seed for reproducibility
)
```

### Option 3: Cache Semantic Descriptions
Store generated semantic descriptions and reuse them for same template.

## Recommendation:

**Keep current behavior (varying diagrams)** if you want:
- Diverse exam papers
- Different scenarios each time
- More realistic exam variety

**Make deterministic** if you want:
- Consistent testing
- Reproducible results
- Same diagram for same template
