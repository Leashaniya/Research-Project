# Quality Improvements Summary

## Overview
This document summarizes the quality improvements made to the AI exam paper generation system to prevent empty/placeholder content, duplicate subquestions, and unnecessary fallbacks.

## Changes Implemented

### A) CRITIC: Strict Deterministic Validation (`backend/app/agents/critic.py`)

**New Hard-Fail Rules (Run BEFORE LLM review):**

1. **Empty/Placeholder Detection**
   - Rejects empty question stems or subquestions
   - Detects placeholders: `"...", "TBD", "[insert", "[placeholder"`
   - Minimum text length: 10 characters for subquestions
   - Feedback codes: `EMPTY_STEM`, `EMPTY_SUBQUESTION`

2. **Marks Validation**
   - Rejects questions with marks <= 0
   - Validates sub-question marks sum to total marks
   - Feedback code: `MATH_ERROR`, `MARKS_ERROR`

3. **Duplicate Subquestion Detection**
   - Uses `SequenceMatcher` to detect similarity >= 85%
   - Checks for exact duplicates (after normalization)
   - Checks if one subquestion is contained in another
   - Feedback code: `DUPLICATE_SUBQUESTIONS`

4. **ER/EER Scenario Requirement**
   - For ER/EER questions, requires scenario block (2-5 sentences)
   - Must describe entities, relationships, and attributes
   - Feedback code: `SCENARIO_MISSING`

5. **Normalization Schema Requirement**
   - For normalization questions, requires relation schema (e.g., R(A,B,C))
   - Requires functional dependencies (FDs)
   - Feedback code: `SCHEMA_MISSING`

6. **Reference Validation**
   - Rejects "described above" / "as shown above" without actual content
   - Feedback code: `REFERENCE_ERROR`

**Why These Checks:**
- **Deterministic**: No LLM needed, fast and reliable
- **Prevents Bad Output**: Catches issues before they reach final paper
- **Explicit Feedback**: Each violation has a specific code for debugging

---

### B) ORCHESTRATOR: Improved Retry/Fallback Policy (`backend/app/agents/orchestrator.py`)

**Key Changes:**

1. **No Auto-Approval of Bad Drafts**
   - Changed default: `is_approved = review.get("approved", False)` (was `True`)
   - Never force-approves invalid drafts after retries

2. **Fallback Validation**
   - After building fallback draft, runs critic validation
   - If fallback fails validation, rebuilds with stricter constraints
   - Only accepts fallback if it passes all deterministic checks

3. **Structured Logging**
   - Logs fallback triggers with:
     - Question number
     - Attempt count
     - Writer mode (generate/paraphrase)
     - Feedback code
     - Validation status
   - Example: `📝 Fallback Log: Q1 | Trigger: SCENARIO_MISSING | Validated: True`

4. **Diagram Placeholder Logic**
   - Removed diagram extraction/injection
   - Sets `needs_diagram` and `diagram_type` flags
   - Adds `diagram_placeholder_text` to draft JSON

**Fallback Flow:**
```
1. Retry loop (up to 4 attempts)
   ├─ Attempt 0-1: Generate mode
   └─ Attempt 2-3: Paraphrase mode

2. If all retries fail:
   ├─ Build fallback draft from template structure
   ├─ Validate fallback with critic
   ├─ If validation fails: Rebuild with stricter constraints
   └─ Only accept if validation passes

3. Never force-approve invalid drafts
```

**Why This Approach:**
- **Quality First**: Ensures only valid content reaches final paper
- **Debugging**: Structured logs help identify why fallbacks occur
- **Last Resort**: Fallback only after true failure, not premature

---

### C) WRITER: Enhanced Prompts (`backend/app/agents/writer.py`)

**New Constraints in Prompts:**

1. **Strict Generation Rules**
   - "NO PLACEHOLDERS" - explicit prohibition
   - "MARKS MUST SUM EXACTLY" - math validation reminder
   - "EACH SUBQUESTION MUST BE SEMANTICALLY DISTINCT" - prevents duplicates
   - "NO 'DESCRIBED ABOVE' REFERENCES" - prevents hallucinations

2. **ER/EER Question Requirements**
   - Must include scenario block in stem (2-5 sentences)
   - Must describe entities, relationships, attributes
   - Subquestions: identify entities → identify relationships → draw diagram → map to relational

3. **Normalization Question Requirements**
   - Must include relation schema (e.g., R(A,B,C))
   - Must include functional dependencies
   - Subquestions: normalization steps to 3NF/BCNF → final decomposition

4. **Diagram Placeholder Instructions**
   - Use `[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram...]`
   - Do NOT use Mermaid code or image references

**Why These Constraints:**
- **Prevention**: Stops bad output at generation time
- **Template-Aware**: Automatically applies based on `pattern_label`
- **Non-Hardcoded**: All content still generated, just with better constraints

---

### D) PDF SERVICE: Diagram Placeholder Rendering (`backend/app/services/pdf_service.py`)

**Changes:**

1. **Placeholder Box Rendering**
   - Draws a boxed placeholder instead of Mermaid code
   - Light gray background with border
   - Centered placeholder text
   - Dimensions: 170mm width × 40mm height

2. **Backward Compatibility**
   - Still supports legacy `mermaid_code` field
   - New `needs_diagram` flag takes precedence

**Why Placeholders:**
- **No Preprocessing**: Removes dependency on diagram extraction
- **Clear Instructions**: Students know where to draw diagrams
- **Consistent Layout**: Maintains PDF structure

---

### E) BLUEPRINT: Validation (`backend/app/agents/analyst.py`)

**New Validation:**

1. **Marks Validation**
   - Ensures total marks = sum of question_slots.target_marks
   - Repairs slots with marks <= 0 (sets to 25)
   - Ensures Q1 exists and has marks > 0

2. **Structure Validation**
   - Checks for missing slots
   - Adds Q1 if missing
   - Logs all repairs

**Why This:**
- **Structure Integrity**: Ensures blueprint is valid before generation
- **Automatic Repair**: Fixes common issues without manual intervention
- **Not Hardcoding**: Only repairs structure, not content

---

## Fallback Logic Explanation

### When Fallbacks Happen

Fallbacks are triggered when:
1. **All retries exhausted** (4 attempts failed)
2. **MATH_ERROR detected** (immediate fallback, no retries)
3. **Critical validation failure** (e.g., SCENARIO_MISSING, SCHEMA_MISSING)

### Why Fallbacks Happen

Common reasons (from logs):
- `SCENARIO_MISSING`: ER question generated without scenario
- `SCHEMA_MISSING`: Normalization question without schema/FDs
- `DUPLICATE_SUBQUESTIONS`: LLM generated similar subquestions
- `MATH_ERROR`: Marks don't sum correctly
- `EMPTY_SUBQUESTION`: Generated placeholder text

### How Fallbacks Work

1. **Template-Based Generation**
   - Uses `required_structure` from canonical template
   - Ensures marks sum correctly (scales if needed)
   - Generates context-aware fallback text (never placeholders)

2. **Validation Loop**
   - Runs critic on fallback draft
   - If fails: Rebuilds with stricter constraints
   - If still fails: Uses minimal valid structure
   - Only accepts if passes validation

3. **Logging**
   - Structured log entry with all details
   - Helps identify patterns in fallback triggers
   - Enables debugging and improvement

### Debugging Fallbacks

Check logs for:
```
🔄 FALLBACK TRIGGERED for Q1
   Reason: SCENARIO_MISSING
   Attempts: 4/4
   Final Mode: paraphrase
   Feedback: ER/EER question must include a scenario block...
📝 Fallback Log: Q1 | Trigger: SCENARIO_MISSING | Validated: True
```

**If fallbacks are frequent:**
- Check if prompts need adjustment
- Verify template quality
- Review LLM responses for patterns

---

## Testing

Run the test suite:
```bash
python backend/scripts/test_quality_checks.py
```

**Tests:**
1. ✅ Empty/placeholder detection
2. ✅ Duplicate subquestion detection
3. ✅ ER scenario requirement
4. ✅ Normalization schema requirement
5. ✅ Marks validation
6. ✅ Valid draft approval

---

## Expected Results After Changes

### Generated Papers Should Have:
- ✅ No empty questions or subquestions
- ✅ No placeholder text ("...", "TBD", etc.)
- ✅ No duplicate/near-duplicate subquestions
- ✅ ER questions include scenarios
- ✅ Normalization questions include schema/FDs
- ✅ Diagrams appear as placeholders (not missing references)
- ✅ All marks sum correctly

### Fallback Behavior:
- ✅ Fallbacks only after true failure (not premature)
- ✅ Fallback drafts pass validation
- ✅ Structured logs for debugging
- ✅ No force-approval of invalid drafts

---

## Code Comments

### Why Fallbacks Happen
Fallbacks occur when the LLM fails to generate valid content after all retries. This can be due to:
- Prompt constraints not being followed
- LLM limitations (hallucinations, math errors)
- Template structure mismatches

### When They Should Happen
- After 4 retry attempts have failed
- When MATH_ERROR is detected (immediate)
- When critical validation fails (SCENARIO_MISSING, SCHEMA_MISSING)

### How Logs Help Debug
- **Feedback codes** identify specific failure types
- **Attempt counts** show retry effectiveness
- **Mode tracking** shows if generate/paraphrase mode matters
- **Validation status** confirms fallback quality

---

## Summary

All changes maintain **full automation** - no hard-coded questions. The system:
1. **Prevents** bad output through strict validation
2. **Retries** intelligently with mode switching
3. **Falls back** only when necessary, with validation
4. **Logs** everything for debugging and improvement

The result: **Higher quality papers with fewer fallbacks, and when fallbacks occur, they're validated and logged.**

