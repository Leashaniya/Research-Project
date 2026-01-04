# Image Processing Status

## 🖼️ **CURRENT STATUS: DISABLED**

Image/diagram processing is **NOT currently active** in the model paper generation system. This feature will be implemented in a future update.

---

## ✅ **HOW IT WORKS NOW**

### Placeholder System

When questions require diagrams or images, the system uses **text placeholders** instead of actual images.

**Format:**
```
[PLACEHOLDER FIGURE] (Description of what the diagram should show)
```

### Example in Generated Paper:

```
Question 1 (20 marks)
a) Define the term "entity" in database design. (5 marks)
b) [PLACEHOLDER FIGURE] (Construct an ER diagram for a University database showing Student, Course, and Enrollment entities with their relationships and attributes) (15 marks)
```

### In PDF Output:

The placeholder text appears directly in the PDF where an image would normally be placed. This is **intentional** and working as designed.

---

## 🔧 **TECHNICAL IMPLEMENTATION**

### 1. Writer Agent (`backend/app/agents/writer.py`)

**Line 104:** Explicitly instructs the LLM to use placeholders:
```python
3. **FIGURE PLACEHOLDERS**: If a diagram is required, DO NOT describe it. 
   Instead, insert exactly: `[PLACEHOLDER FIGURE] (Description of what diagram should show)`.
```

### 2. Critic Agent (`backend/app/agents/critic.py`)

**Lines 62-64:** Explicitly allows the placeholder format:
```python
# EXCEPTION: We explicitly ALLOW "[placeholder figure]" as per rule.
# So we remove that string before checking for other bad keywords.
clean_draft_str = draft_str.replace("[placeholder figure]", "")
```

**Line 66:** Rejects other figure references:
```python
hallucination_keywords = ["[figure:", "slide ", "slide_", "fig_", "page ", "page_", "refer to", "diagram above", "shown in figure"]
```

### 3. PDF Service (`backend/app/services/pdf_service.py`)

**Lines 82-94:** Renders text as-is (no image processing):
```python
text = PDFService._sanitize_text(sq.get("text", ""))
full_text = f"{label})  {text}"
pdf.multi_cell(155, 6, full_text)  # Renders placeholder text directly
```

---

## ✅ **SYSTEM BEHAVIOR**

### What Happens:

1. **Question Generation:**
   - Writer agent generates question text
   - If diagram needed, inserts `[PLACEHOLDER FIGURE] (description)`

2. **Quality Check:**
   - Critic agent validates the placeholder format
   - Allows `[PLACEHOLDER FIGURE]` but rejects other figure references

3. **PDF Generation:**
   - PDF service renders the placeholder text directly
   - No image processing occurs
   - Placeholder appears in final PDF

### Result:

- ✅ Questions are generated correctly
- ✅ Placeholders indicate where diagrams should be
- ✅ PDFs are generated successfully
- ✅ System works as intended

---

## 🚫 **WHAT IS NOT ACTIVE**

### Disabled Features:

- ❌ Image extraction from past papers
- ❌ Diagram detection and processing
- ❌ Image insertion into PDFs
- ❌ Diagram generation from text
- ❌ Image placeholder replacement

### Note:

The extraction scripts (`pastpaper_extract.py`, `lectureslide_extract.py`) may have diagram detection code, but **it is not used** in the current model paper generation flow.

---

## 🔮 **FUTURE IMPLEMENTATION**

### Planned Features (To Be Implemented):

1. **Image Extraction:**
   - Extract diagrams from past papers
   - Store in `data/text_extraction_hybrid/*/diagrams/`

2. **Placeholder Replacement:**
   - Detect `[PLACEHOLDER FIGURE]` in generated questions
   - Match with appropriate diagram from database
   - Replace placeholder with actual image

3. **Diagram Generation:**
   - Generate diagrams from text descriptions
   - Use AI tools for ER diagram creation
   - Insert generated diagrams into PDFs

4. **PDF Image Support:**
   - Update PDF service to handle image insertion
   - Position images correctly in PDF layout
   - Maintain proper formatting

---

## 📝 **CURRENT WORKFLOW**

```
User Uploads Files
    ↓
Extract Text (diagrams saved but not used)
    ↓
Generate Questions
    ├─ Writer: Creates text with [PLACEHOLDER FIGURE]
    └─ Critic: Validates placeholder format
    ↓
Generate PDF
    └─ PDF Service: Renders placeholder text as-is
    ↓
Output PDF with Text Placeholders
```

---

## ✅ **VERIFICATION**

### To Verify Current Behavior:

1. Generate a model paper
2. Check for questions requiring diagrams
3. Look for `[PLACEHOLDER FIGURE]` text in PDF
4. Confirm placeholder appears where image would be

### Expected Result:

- ✅ Placeholder text visible in PDF
- ✅ No actual images in PDF
- ✅ System completes successfully
- ✅ No errors related to image processing

---

## 🎯 **SUMMARY**

**Status:** Image processing is **DISABLED** - working as intended

**Current Behavior:** Text placeholders are used instead of images

**Action Required:** None - system works correctly

**Future:** Image processing will be added in a later update

---

*Last Updated: 2025-01-27*
*Status: Image Processing Disabled (Intentional)*

