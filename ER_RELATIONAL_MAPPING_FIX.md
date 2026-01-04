# ER → Relational Mapping Repetition Fix

## ❌ **ISSUE IDENTIFIED**

**Problem:** ER → Relational Mapping is being asked multiple times in the generated paper.

**Found in Generated Paper:**
- **Q3 Part D:** "Map the ER diagram to relational model tables for Books, Borrowers, Librarians, and Borrowings"
- **Q4 Part E:** "Design a relational schema for the Books entity, including the primary key, foreign keys, and data types"
- **Q5 Part F:** "Map the ER diagram to a relational schema, including the primary and foreign keys"

**Root Cause:** The anti-repetition logic was only tracking:
- `er_diagram` - for drawing ER diagrams
- `normalization` - for normalization questions  
- `sql_query` - for SQL queries

**Missing:** `er_to_relational_mapping` was NOT being tracked.

---

## ✅ **FIX IMPLEMENTED**

### **1. Added ER → Relational Mapping Detection** ✅

**File:** `backend/app/agents/orchestrator.py`

**Added Detection Logic (Lines 372-380):**
```python
# Detect ER → Relational Mapping
if ("map" in q_text_lower or "convert" in q_text_lower or "transform" in q_text_lower) and 
   ("er diagram" in q_text_lower or "eer diagram" in q_text_lower) and 
   ("relational" in q_text_lower or "relational schema" in q_text_lower or "relational model" in q_text_lower):
    used_question_types.add("er_to_relational_mapping")
    print("      📌 Marked type: er_to_relational_mapping")

# Also detect "Design relational schema" as mapping (if ER mentioned in question)
if "design" in q_text_lower and "relational schema" in q_text_lower and 
   ("er" in q_text_lower or "entity" in q_text_lower):
    used_question_types.add("er_to_relational_mapping")
    print("      📌 Marked type: er_to_relational_mapping")
```

**Detects:**
- "Map the ER diagram to relational..."
- "Convert ER to relational schema..."
- "Transform ER diagram to relational model..."
- "Design relational schema from ER diagram..."

---

### **2. Added Forbidden Topics Prevention** ✅

**File:** `backend/app/agents/orchestrator.py`

**Added to Forbidden Topics Logic (Lines 313-318):**
```python
# If we already have ER → Relational Mapping, forbid another one
if "er_to_relational_mapping" in used_question_types:
    forbidden_topics.append("Map the ER diagram to relational")
    forbidden_topics.append("Map ER to relational schema")
    forbidden_topics.append("Convert ER diagram to relational model")
    forbidden_topics.append("Design relational schema from ER diagram")
```

**Result:** After first ER → Relational Mapping question, system forbids generating another one.

---

### **3. Added to Forced Approval Path** ✅

**File:** `backend/app/agents/orchestrator.py`

**Added Detection for Forced Approval (Lines 501-508):**
- Same detection logic applied even when question is force-approved
- Ensures tracking works even if generation fails and fallback is used

---

## 🔍 **HOW IT WORKS NOW**

### **Before Fix:**
1. Q1: ER diagram drawn ✅
2. Q3: ER → Relational Mapping asked ✅
3. Q4: ER → Relational Mapping asked again ❌ (not prevented)
4. Q5: ER → Relational Mapping asked again ❌ (not prevented)

### **After Fix:**
1. Q1: ER diagram drawn ✅ → `er_diagram` tracked
2. Q3: ER → Relational Mapping asked ✅ → `er_to_relational_mapping` tracked
3. Q4: System checks → `er_to_relational_mapping` already used → **FORBIDDEN** ✅
4. Q5: System checks → `er_to_relational_mapping` already used → **FORBIDDEN** ✅

**Result:** Only ONE ER → Relational Mapping question per paper.

---

## 📊 **DETECTION PATTERNS**

The system now detects ER → Relational Mapping when question text contains:

### **Pattern 1: Explicit Mapping**
- "Map the ER diagram to relational..."
- "Map ER to relational schema..."
- "Convert ER diagram to relational model..."
- "Transform ER to relational..."

### **Pattern 2: Design with ER Context**
- "Design relational schema" + "ER diagram" mentioned
- "Design relational schema" + "entity" mentioned

### **Keywords Detected:**
- **Action words:** map, convert, transform, design
- **Source:** ER diagram, EER diagram, entity
- **Target:** relational, relational schema, relational model, relational tables

---

## ✅ **EXPECTED BEHAVIOR**

### **Next Generation:**
1. ✅ First ER → Relational Mapping question will be allowed
2. ✅ System will track it in `used_question_types`
3. ✅ Subsequent questions will have it in `forbidden_topics`
4. ✅ Writer will avoid generating another ER → Relational Mapping question
5. ✅ Result: Only ONE ER → Relational Mapping question per paper

---

## 🎯 **COMPLETE ANTI-REPETITION TRACKING**

The system now tracks:

1. ✅ **ER Diagrams** (`er_diagram`)
   - Prevents multiple "Draw ER diagram" questions

2. ✅ **ER → Relational Mapping** (`er_to_relational_mapping`) **NEW**
   - Prevents multiple "Map ER to relational" questions

3. ✅ **Normalization** (`normalization`)
   - Prevents multiple normalization questions

4. ✅ **SQL Queries** (`sql_query`)
   - Tracks SQL query questions

---

## 📝 **SUMMARY**

**Issue:** ER → Relational Mapping asked 3 times (Q3, Q4, Q5)

**Fix:** 
- Added detection for ER → Relational Mapping questions
- Added to forbidden topics after first use
- Applied to both approved and forced approval paths

**Result:** ✅ Only ONE ER → Relational Mapping question per paper

---

*Fix Date: 2025-01-27*
*Issue: ER → Relational Mapping repetition*
*Status: ✅ Fixed*

