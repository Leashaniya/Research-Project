# Q2 Fallback Analysis - Detailed Investigation

## Summary

Q2 fell into fallback because **all 3 attempts were rejected for `SCHEMA_MISSING`**. The root cause is a **template label mismatch** that prevents the Writer from knowing it needs to generate normalization content with schema.

---

## What Happened

### Pipeline Log:
```
>>> Processing Q2 (15 marks)...
   Template ID: 696d2a8334b588bc4896aae8
   Pattern Label/Intent: frame bytes time  ← BAD LABEL
   
[QUESTION WRITER]: Drafting question for Q2 (Mode: GEN-FROM-SCRATCH)...
[QUALITY CRITIC]: ❌ Deterministic Reject: SCHEMA_MISSING: Normalization question must include a relation schema...
   ❌ Critic Rejected (Attempt 1): SCHEMA_MISSING

[QUESTION WRITER]: Drafting question for Q2 (Mode: TEMPLATE-PARAPHRASE)...
[QUALITY CRITIC]: ❌ Deterministic Reject: SCHEMA_MISSING: Normalization question must include a relation schema...
   ❌ Critic Rejected (Attempt 2): SCHEMA_MISSING

[QUESTION WRITER]: Drafting question for Q2 (Mode: TEMPLATE-PARAPHRASE)...
[QUALITY CRITIC]: ❌ Deterministic Reject: SCHEMA_MISSING: Normalization question must include a relation schema...
   ❌ Critic Rejected (Attempt 3): SCHEMA_MISSING
   
⚠️ Max Retries reached. Using safest fallback.
```

---

## Root Cause Analysis

### The Problem Chain:

```
1. Template Selection
   ↓
   Template has pattern_label: "frame bytes time" (BAD - networking term)
   ↓
2. Writer Prompt Generation
   ↓
   Writer checks: is_norm_question = "normalization" in pattern_label
   ↓
   Result: FALSE (because pattern_label is "frame bytes time", not "normalization")
   ↓
   Writer prompt does NOT include normalization requirements
   ↓
3. Writer Generates Question
   ↓
   Writer generates normalization content (correctly, based on template structure)
   BUT: Doesn't include schema because prompt didn't tell it to
   ↓
4. Critic Validation
   ↓
   Critic checks: is_norm_question = "normalization" in combined_text
   ↓
   Result: TRUE (because Writer generated normalization content)
   ↓
   Critic checks for schema: NOT FOUND
   ↓
   REJECT: SCHEMA_MISSING
```

---

## Code Analysis

### Writer Prompt Logic (`backend/app/agents/writer.py:289-298`):

```python
# Determine if ER/EER or Normalization question
is_er_question = "er" in pattern_label or "eer" in pattern_label or ...
is_norm_question = "normalization" in pattern_label or "normal form" in pattern_label

# Later in prompt:
{"6. **NORMALIZATION QUESTION REQUIREMENTS**: " if is_norm_question else ""}
{"   - A relation schema (e.g., R(A,B,C) or explicit attributes)" if is_norm_question else ""}
{"   - Functional dependencies (FDs) in standard notation" if is_norm_question else ""}
```

**Problem**: `is_norm_question` is `False` because `pattern_label = "frame bytes time"` doesn't contain "normalization".

**Result**: Writer prompt doesn't include normalization requirements, so Writer doesn't know to include schema.

---

### Critic Validation Logic (`backend/app/agents/critic.py:192-196`):

```python
# Check if this is a normalization question
is_norm_question = (
    "normalization" in pattern_label or "normal form" in pattern_label or
    "normalization" in combined_text or "normal form" in combined_text or  ← CHECKS CONTENT TOO
    ("normalize" in combined_text and ("relation" in combined_text or "schema" in combined_text))
)
```

**Key Difference**: Critic checks **both** pattern_label AND combined_text.

**Result**: Critic correctly detects it as normalization (because Writer generated normalization content), but Writer didn't include schema.

---

## Why This Happens

1. **Template Label is Wrong**: `pattern_label: "frame bytes time"` (should be `"NORMALIZATION_FD_KEYS"`)

2. **Writer Relies on Pattern Label**: Writer uses pattern_label to determine question type and requirements

3. **Critic Checks Content**: Critic checks actual content, not just pattern_label

4. **Mismatch**: Writer doesn't know it's normalization (bad label), but Critic detects it is (content check)

---

## The Fix Needed

### Option 1: Fix Template Label (Best Solution)
- Regenerate templates with correct pattern labels
- Use the reclassification logic we added to `template_analyzer.py`
- This will fix "frame bytes time" → "NORMALIZATION_FD_KEYS"

### Option 2: Make Writer Check Content Too (Workaround)
- Update Writer to also check template content/structure, not just pattern_label
- If template structure suggests normalization (e.g., has normalization-related subquestions), treat as normalization

### Option 3: Improve Template Detection
- Use `classify_pattern()` in Writer to reclassify based on template content
- Similar to what we did in template_analyzer.py

---

## Current Status

✅ **Fallback Works**: System still generates valid questions using fallback mechanism

⚠️ **Template Label Issue**: Q2 template has wrong label, causing Writer-Critic mismatch

✅ **Fix Available**: Reclassification logic added to template_analyzer.py (needs to be run)

---

## Recommendation

**Immediate**: Regenerate templates using `template_analyzer.py` to fix pattern labels

**Future**: Consider making Writer also check content/structure, not just pattern_label, to be more robust

---

## Summary

Q2 fell into fallback because:
1. Template has wrong pattern_label ("frame bytes time")
2. Writer doesn't know it's normalization (relies on pattern_label)
3. Writer generates normalization content but without schema
4. Critic detects normalization (checks content) and requires schema
5. All 3 attempts rejected for SCHEMA_MISSING
6. Fallback used

**The fix**: Regenerate templates with correct pattern labels using the reclassification logic.
