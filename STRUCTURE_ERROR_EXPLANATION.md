# STRUCTURE_ERROR Explanation

## Error Message
```
STRUCTURE_ERROR: Generated 3 sub-questions, but template requires EXACTLY 7. Please follow the required structure.
```

## What This Error Means

This error occurs when the **Quality Critic** agent validates a generated question and finds that:

1. **The LLM (Writer agent) generated**: 3 sub-questions
2. **The template requires**: Exactly 7 sub-questions
3. **Result**: The question is **rejected** because it doesn't match the required structure

---

## Why This Happens

### 1. **Template Structure Comes from Past Papers**

The `required_structure` is derived from analyzing historical exam papers:

```
Past Paper Analysis
    ↓
Extract sub-question patterns (e.g., 7 parts: a, b, c, d, e, f, g)
    ↓
Store as "required_structure" in template
    ↓
Template says: "You MUST generate exactly 7 sub-questions"
```

**Location**: `backend/scripts/template_analyzer.py` and `backend/scripts/structure_topics_template.py`

### 2. **The LLM Sometimes Ignores the Structure**

Even though the prompt includes:
```
REQUIRED STRUCTURE:
- Part a: 2 marks
- Part b: 1 marks
- Part c: 2 marks
- Part d: 3 marks
- Part e: 2 marks
- Part f: 2 marks
- Part g: 3 marks
```

The LLM (GPT-4o-mini) sometimes:
- Generates fewer sub-questions (e.g., 3 instead of 7)
- Generates more sub-questions (e.g., 8 instead of 7)
- Ignores the structure entirely

**Why?**
- LLMs are probabilistic and don't always follow instructions perfectly
- The structure requirement might not be emphasized strongly enough
- The LLM might think it's "simplifying" the question

### 3. **The Critic Validates Strictly**

The **Quality Critic** agent checks:

```python
# Location: backend/app/agents/critic.py (line 310-315)

required_struct = template.get("required_structure") or template.get("subquestions", [])
if required_struct and len(sub_qs) != len(required_struct):
    err_msg = f"STRUCTURE_ERROR: Generated {len(sub_qs)} sub-questions, but template requires EXACTLY {len(required_struct)}. Please follow the required structure."
    return {"approved": False, "feedback": err_msg, "feedback_code": "STRUCTURE_ERROR"}
```

**This is a HARD validation** - no tolerance for mismatches.

---

## The Flow

```
1. Template Selection
   ↓
   Template has: required_structure = [7 parts with marks]
   
2. Writer Agent (LLM)
   ↓
   Prompt includes: "REQUIRED STRUCTURE: 7 parts"
   ↓
   LLM generates: 3 sub-questions ❌
   
3. Quality Critic
   ↓
   Checks: len(generated) == len(required)?
   ↓
   3 != 7 → REJECT ❌
   ↓
   Returns: STRUCTURE_ERROR
   
4. Orchestrator
   ↓
   Retries with feedback (up to 3 times)
   ↓
   If all retries fail → Uses fallback draft
```

---

## Where the Structure Comes From

### Step 1: Past Paper Analysis
**File**: `backend/scripts/structure_topics_template.py`

```python
# Analyzes past papers and extracts sub-question patterns
for q in questions:
    subqs = q.get("subquestions", [])
    subq_marks = [sq.get("marks") for sq in subqs]
    
    # Records: "This question had 7 parts with marks [2,1,2,3,2,2,3]"
    slot_stats[qpos]["structural_fingerprint"] = subq_marks
```

### Step 2: Template Creation
**File**: `backend/scripts/template_analyzer.py`

```python
# Finds most recent paper with this topic
most_recent = papers_with_topic[0]
subquestions = most_recent.get("subquestions", [])

# Extracts structure
structure = []
for sq in subquestions:
    structure.append({
        "label": sq.get("label"),
        "marks": sq.get("marks"),
        "type": determine_type(sq.get("text"))
    })

# Stores in canonical template
canonical_template["subquestion_structure"] = structure  # 7 parts
```

### Step 3: Template Usage
**File**: `backend/app/agents/orchestrator.py`

```python
# Gets template with required_structure
template = await self._select_template(...)
required_structure = template.get("required_structure")  # 7 parts

# Passes to Writer
writer_input = {
    "template": template,  # Contains required_structure
    ...
}
```

### Step 4: Writer Prompt
**File**: `backend/app/agents/writer.py`

```python
structure_fingerprint = template.get("required_structure")  # 7 parts
structure_str = "\n".join([f"- Part {s.get('label')}: {s.get('marks')} marks" 
                           for s in structure_fingerprint])

prompt = f"""
REQUIRED STRUCTURE:
{structure_str}  # Shows: Part a: 2 marks, Part b: 1 marks, ... (7 parts)
"""
```

---

## Why 7 Parts Instead of 3?

The structure (7 parts) comes from **real past papers**. For example:

**Past Paper Example:**
```
Q2 (15 marks)
a) Define... (2 marks)
b) Describe... (1 mark)
c) Analyze... (2 marks)
d) Compare... (3 marks)
e) Evaluate... (2 marks)
f) Explain... (2 marks)
g) List... (3 marks)
Total: 15 marks, 7 parts
```

The system learned: "Q2 typically has 7 parts" and enforces this pattern.

---

## Solutions

### Current Behavior (Automatic Retry)

The system **automatically retries** up to 3 times:

```
Attempt 1: LLM generates 3 parts → REJECTED
Attempt 2: LLM generates 3 parts → REJECTED  
Attempt 3: LLM generates 3 parts → REJECTED
Fallback: Uses minimal valid draft (follows structure exactly)
```

### Potential Improvements

1. **Strengthen the Prompt**
   - Add explicit instruction: "You MUST generate EXACTLY {N} sub-questions"
   - Show example structure more prominently

2. **Post-Processing Fix**
   - After LLM generates, check count
   - If wrong, automatically add/remove sub-questions to match structure

3. **Make Structure Optional**
   - Allow flexibility if structure is too rigid
   - Only enforce if structure is critical

---

## Current Status

✅ **The system handles this automatically:**
- Retries with feedback (up to 3 times)
- Falls back to template-copy mode if LLM fails
- Generates valid question even if LLM doesn't follow structure

⚠️ **You see this error because:**
- The LLM didn't follow the structure on first attempt
- The system is working correctly by rejecting invalid output
- The retry mechanism will eventually succeed or use fallback

---

## Summary

**The Error**: LLM generated 3 sub-questions, but template requires 7.

**Why**: Template structure comes from past papers (7 parts), but LLM sometimes ignores instructions.

**What Happens**: Critic rejects → System retries → Eventually succeeds or uses fallback.

**Status**: This is **expected behavior** - the system is correctly validating and will eventually generate a valid question.
