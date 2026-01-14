# Mark Assignment Rules Verification

## Golden Rule Compliance

✅ **Marks are NOT assigned based on question number**

All mark assignments follow these rules (in priority order):

1. **Blueprint values** (from historical statistics)
   - Uses `canonical_total_marks` from blueprint
   - Derived from past paper analysis

2. **Even distribution**: `total_marks / number_of_slots`
   - When blueprint total is available, distribute evenly
   - Example: 100 total marks / 4 slots = 25 marks per slot

3. **Configurable defaults** (not tied to slot ID)
   - Uses `DEFAULT_SLOT_MARKS` from config
   - Applied to any invalid slot, not just Q1

## Implementation Details

### Blueprint Validation (`backend/app/agents/analyst.py`)

**Repair Logic (Priority Order)**:

1. **Blueprint Total Marks** (from historical statistics):
   ```python
   if blueprint_total and blueprint_total > 0:
       repaired_marks = int(round(blueprint_total / len(slots)))
   ```

2. **Average from Valid Slots** (proportional distribution):
   ```python
   elif valid_marks_sum > 0:
       avg_marks = valid_marks_sum / (len(slots) - len(invalid_slots))
       repaired_marks = int(round(avg_marks))
   ```

3. **Configurable Default**:
   ```python
   else:
       repaired_marks = settings.DEFAULT_SLOT_MARKS
   ```

**Key Points**:
- ✅ No Q1-specific logic
- ✅ Any slot with marks <= 0 gets repaired
- ✅ Marks derived from calculation, not position
- ✅ Position-agnostic repair

### Default Blueprint (`_default_blueprint()`)

**Mark Assignment**:

1. **Try Historical Statistics**:
   ```python
   if canonical_total_marks:
       marks_per_slot = int(round(canonical_total_marks / num_slots))
   ```

2. **Fallback to Config**:
   ```python
   else:
       marks_per_slot = settings.DEFAULT_SLOT_MARKS
   ```

**Key Points**:
- ✅ Marks calculated, not hardcoded
- ✅ Uses `canonical_total_marks` if available (historical statistics)
- ✅ Falls back to config default (not tied to slot ID)
- ✅ All slots get same marks (even distribution)

## Verification Results

### Code Check
✅ **PASSED**: No Q1-specific mark assignments found
✅ **PASSED**: No position-based mark assignments found
✅ **PASSED**: Marks derived from blueprint values, total_marks/num_slots, or config defaults

### Blueprint Repair Tests

**Test 1**: Q2 has zero marks (not Q1)
- ✅ Q2 marks repaired to 25
- ✅ Marks derived from `canonical_total_marks / num_slots = 100 / 4 = 25`
- ✅ Not Q1-specific

**Test 2**: Q3 has zero marks
- ✅ Q3 marks repaired to 25
- ✅ Same calculation as Q2 (position-agnostic)

**Test 3**: No canonical_total_marks
- ✅ Uses config default (`DEFAULT_SLOT_MARKS = 25`)
- ✅ Not hardcoded, configurable

## Examples

### Example 1: Blueprint with canonical_total_marks

```python
blueprint = {
    "canonical_total_marks": 100,  # From historical statistics
    "question_slots": [
        {"question_no": "Q1", "target_marks": 25},
        {"question_no": "Q2", "target_marks": 0},  # Invalid
        {"question_no": "Q3", "target_marks": 25},
        {"question_no": "Q4", "target_marks": 25}
    ]
}

# Repair: Q2 gets 100 / 4 = 25 marks
# NOT because it's Q2, but because: blueprint_total / num_slots
```

### Example 2: No canonical_total_marks

```python
blueprint = {
    "question_slots": [
        {"question_no": "Q1", "target_marks": 0},  # Invalid
        {"question_no": "Q2", "target_marks": 0}  # Invalid
    ]
}

# Repair: Both get DEFAULT_SLOT_MARKS (25)
# NOT because Q1=25, but because config default applies to any invalid slot
```

### Example 3: Average from valid slots

```python
blueprint = {
    "question_slots": [
        {"question_no": "Q1", "target_marks": 20},
        {"question_no": "Q2", "target_marks": 30},
        {"question_no": "Q3", "target_marks": 0},  # Invalid
        {"question_no": "Q4", "target_marks": 30}
    ]
}

# Repair: Q3 gets (20+30+30) / 3 = 26.67 ≈ 27 marks
# NOT because it's Q3, but because: average of valid slots
```

## Configuration

All mark-related settings are configurable:

```python
# backend/app/core/config.py
MIN_SLOTS = 4  # Minimum slots in blueprint
DEFAULT_SLOT_MARKS = 25  # Default marks per slot (not tied to slot ID)
```

## Summary

✅ **All mark assignments are position-agnostic**

- No marks assigned based on question number
- Marks derived from:
  1. Blueprint values (historical statistics)
  2. Even distribution (total_marks / num_slots)
  3. Configurable defaults (not tied to slot ID)

✅ **System is academically defensible**

- Marks come from data analysis or config, not hardcoded rules
- Repairs are generic and apply to any invalid slot
- No special treatment for Q1 or any specific position

