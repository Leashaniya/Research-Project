# Template Diversity Fix - Prevent Repeated Questions

## Problem
Q1 and Q2 (or other slots) were selecting the same template, resulting in repeated questions with the same intent/pattern.

## Solution Implemented

### 1. Global Diversity Tracking ✅

**Location**: `backend/app/agents/orchestrator.py` - `run_pipeline()` method

Added global tracking sets:
- `used_intents` - Tracks used `pattern_label`/intent across all questions
- `used_template_ids` - Tracks used template `_id` to never reuse exact same template

```python
used_intents = set()  # Track used pattern_label/intent
used_template_ids = set()  # Track used template _id
```

### 2. Updated `_select_template()` Method ✅

**Location**: `backend/app/agents/orchestrator.py`

**Changes**:
- Added `used_intents` and `used_template_ids` parameters
- Excludes already-used template IDs from MongoDB query
- Scores candidates with diversity bonuses/penalties:
  - **+30 bonus** for unused intent
  - **-50 penalty** for used intent
  - **-1000 penalty** for used template ID (shouldn't happen after filter)
- Logs template selection with diversity info

**Scoring Logic**:
```python
# Bonus: Unused intent
if intent not in used_intents:
    score += 30

# Penalty: Same intent already used
if intent in used_intents:
    score -= 50
```

### 3. Canonical Template Diversity Check ✅

**Location**: `backend/app/agents/orchestrator.py` - Template selection logic

**Changes**:
- Checks if canonical template is already used (by intent AND ID)
- If already used, searches for alternative template with different intent
- Only uses canonical template if it's not already used

```python
if canonical_intent in used_intents and canonical_id in used_template_ids:
    # Search for alternative
    template = await self._select_template(...)
else:
    # Use canonical template
    template = {...}
```

### 4. Template Tracking After Acceptance ✅

**Location**: Multiple places in `orchestrator.py`

**Changes**:
- After question is approved, track template ID and intent
- Ensures Q2, Q3, etc. know what was already used
- Applied in:
  - Normal approval flow
  - Safe mode approval flow
  - Fallback approval flow

### 5. Logging ✅

**Template Selection Log** (per slot):
```
📋 Template Selection Log:
   Slot ID: Q1
   Template ID: 507f1f77bcf86cd799439011
   Pattern Label/Intent: ER and EER Diagrams
   Already Used Intent: No
   Already Used Template ID: No
```

**Diversity Summary** (end of generation):
```
📊 Template Diversity Summary:
   Used Template IDs: 4 unique templates
   Used Intents: 4 unique intents
   Intent List: ER and EER Diagrams, Normalization, SQL Database Schema and Queries, Transaction Management
   ✅ All questions use unique templates
```

## Verification

After running generation, check logs for:
1. **Template Selection Log** - Each slot should show different template_id
2. **Diversity Summary** - Should show unique templates for each question
3. **Intent List** - Should show different intents for Q1, Q2, Q3, Q4

## Expected Behavior

- ✅ Q1 and Q2 will have different `template_id`
- ✅ Q1 and Q2 will preferably have different `pattern_label`/intent
- ✅ If canonical template is already used, system searches for alternative
- ✅ System never selects exact same template twice (by `_id`)

## Files Modified

1. `backend/app/agents/orchestrator.py`
   - Added `used_intents` and `used_template_ids` tracking
   - Updated `_select_template()` with diversity logic
   - Added canonical template diversity check
   - Added template tracking after acceptance
   - Added logging for template selection and diversity summary

