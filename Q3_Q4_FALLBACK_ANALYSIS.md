# Q3 and Q4 Fallback Analysis

## Summary
Both Q3 (SQL_DDL_DML) and Q4 (RELATIONAL_ALGEBRA) fell into fallback after 3 failed attempts each. This document analyzes the root causes.

---

## Q3 (SQL_DDL_DML) - Fallback Root Causes

### Attempt 1: Deterministic Rejection - SCENARIO_MISSING
**Error**: `SCENARIO_MISSING: ER/EER question must include at least 1 relationship indicator (e.g., 'has', 'contains', 'enrolls'). Found: 0.`

**Root Cause**: 
The Critic's `_check_er_scenario_required()` function incorrectly identified Q3 as an ER/EER question. The check logic (lines 131-135 in `critic.py`) looks for:
- `"er" in pattern_label` OR
- `"eer" in pattern_label` OR  
- `"diagram" in pattern_label` OR
- `"er diagram" in combined_text` OR
- `"eer diagram" in combined_text` OR
- `("draw" in combined_text and ("er" in combined_text or "entity" in combined_text))`

**Problem**: If the LLM generates a SQL question that mentions "ER diagram" in a subquestion (e.g., "Draw the ER diagram for the database schema"), the check incorrectly treats it as an ER/EER question and requires scenario content (entities, relationships) that SQL questions don't need.

**Example**: A SQL question might have a subquestion like "Draw the ER diagram representing the database schema" which triggers the ER check, but the main question is about SQL queries, not ER modeling.

### Attempt 2-3: LLM Rejections
- **Attempt 2**: Rejected for not aligning with historical patterns (too practical/operational, not theoretical enough)
- **Attempt 3**: Rejected for clarity issues (ambiguous role/permission requirements)

**Root Cause**: The LLM is generating SQL questions that are too application-oriented (e.g., T-SQL user management, JDBC drivers) rather than focusing on fundamental SQL concepts (SELECT, JOIN, WHERE, GROUP BY) as seen in past papers.

---

## Q4 (RELATIONAL_ALGEBRA) - Fallback Root Causes

### Attempt 1-2: LLM Rejections - Complexity Issues
**Errors**:
- Attempt 1: "subquestion (d) requires complex reasoning... tuple calculus... too advanced"
- Attempt 2: "subquestion (f) requires expressing queries in tuple calculus... may not align with historical patterns"

**Root Cause**: The LLM keeps generating relational algebra questions that include:
1. **Tuple Calculus**: Questions asking to "express queries in tuple calculus" which is not typically in basic exam patterns
2. **Division Operations**: Queries like "customers who have purchased tickets for ALL movies" require division operations (universal quantifiers) which are complex
3. **Complex Quantifiers**: "all available animals", "each menu" - these require advanced relational algebra operations

**Why This Happens**: The LLM is trying to create challenging questions but goes beyond the complexity level of past papers. Historical exam papers focus on simpler relational algebra operations (selection, projection, join, union, intersection) rather than division or tuple calculus.

### Attempt 3: Deterministic Rejection - DUPLICATE_SUBQUESTIONS
**Error**: `DUPLICATE_SUBQUESTIONS: Subquestions have 85.28% similarity: 'Find the names of the customers who have booked a ...' vs 'Retrieve the names of the customers who have booke...'`

**Root Cause**: After being rejected for complexity, the LLM tried to simplify the queries but ended up generating very similar subquestions:
- "Find the names of the customers who have booked a..."
- "Retrieve the names of the customers who have booked..."

These are semantically identical (both asking for customer names who booked something) with only minor wording differences ("Find" vs "Retrieve"), triggering the duplicate detection (85.28% similarity threshold is 85%).

**Why This Happens**: The LLM struggles to generate distinct relational algebra queries when constrained to avoid complex operations. It falls back to similar query patterns.

---

## Solutions and Recommendations

### For Q3 (SQL_DDL_DML):

1. **Fix ER/EER Check Logic**:
   - The `_check_er_scenario_required()` should be more strict about when to apply the check
   - Only apply if `pattern_label` explicitly contains "ER" or "EER", not just if text mentions "ER diagram"
   - SQL questions might mention ER diagrams in context but aren't ER modeling questions

2. **Strengthen SQL Prompt**:
   - Explicitly instruct the LLM to focus on fundamental SQL operations (SELECT, JOIN, WHERE, GROUP BY, HAVING, subqueries)
   - Avoid JDBC, T-SQL user management, or other advanced topics unless in template
   - Emphasize theoretical SQL concepts over operational/administrative tasks

3. **Template-Based Generation**:
   - Q3 template has 9 subquestions about JDBC and T-SQL
   - Consider if this template aligns with historical patterns
   - If not, the template selection logic should prioritize simpler SQL templates

### For Q4 (RELATIONAL_ALGEBRA):

1. **Explicit Complexity Constraints**:
   - Add to prompt: "Do NOT include tuple calculus, division operations, or universal quantifiers"
   - Emphasize: "Use only basic relational algebra operations: selection (σ), projection (π), join (⨝), union (∪), intersection (∩), difference (-)"
   - State: "Keep queries at the same complexity level as past exam papers"

2. **Improve Duplicate Detection Prevention**:
   - The Writer should ensure distinct query intents for each subquestion
   - Use different operations (selection vs projection vs join vs union)
   - Use different attributes/conditions to ensure semantic distinctness

3. **Fallback Enhancement**:
   - The `_generate_minimal_valid_draft()` fallback for relational algebra should generate simple, distinct queries
   - Use a predefined set of distinct query patterns to avoid duplicates

---

## Current Fallback Behavior

Both Q3 and Q4 fell back to `_generate_minimal_valid_draft()` which:
- **Q3**: Generated generic SQL subquestions (fallback uses predefined SQL task list)
- **Q4**: Generated generic ER diagram subquestions (fallback detected it as ER question)

**Issue**: The fallback for Q4 incorrectly generated ER diagram content when Q4 should be relational algebra. This suggests the fallback's intent detection needs improvement.

---

## Next Steps

1. **Fix ER/EER Check**: Make it more strict - only check if `pattern_label` explicitly indicates ER/EER
2. **Enhance SQL Prompts**: Add explicit constraints to avoid advanced topics
3. **Add Complexity Constraints**: Explicitly prohibit tuple calculus and division operations in relational algebra questions
4. **Improve Fallback**: Ensure fallback correctly identifies question type and generates appropriate content
5. **Template Review**: Review Q3 template to ensure it aligns with historical patterns

---

## Conclusion

Q3 and Q4 fall into fallback due to:
- **Q3**: Incorrect ER/EER scenario check + LLM generating too advanced SQL topics
- **Q4**: LLM generating overly complex queries (tuple calculus) + then generating duplicate queries when constrained

Both issues stem from the LLM not strictly following historical exam patterns and the validation logic being either too strict (Q3) or not strict enough about complexity (Q4).
