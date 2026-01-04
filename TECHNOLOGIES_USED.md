# Technologies Used in Your Project

## Complete Technology Stack Breakdown

Based on your Tools & Technology diagram and actual codebase analysis:

---

## ✅ **1. TEXT PROCESSING LIBRARIES**

### **Regex** ✅ USED
- **Location:** `backend/scripts/audit_report.py`
- **Usage:** Pattern matching, text cleaning, validation
- **Example:** Text sanitization, placeholder detection

### **NLTK** ❌ NOT USED
- Not found in codebase
- Could be added for advanced NLP features

### **spaCy** ❌ NOT USED
- Not found in codebase
- Could be added for entity recognition

**Status:** Basic text processing with Regex only

---

## ✅ **2. DATA HANDLING TOOLS**

### **NumPy** ✅ USED
- **Location:** Multiple files
  - `backend/scripts/structure_topics_template.py`
  - `backend/scripts/pastpaper_extract.py`
  - `backend/scripts/lectureslide_extract.py`
  - `backend/app/agents/researcher.py`
  - `backend/scripts/generate_model_paper_openai.py`
- **Usage:** 
  - Array operations for image processing
  - Embedding vector operations
  - Mathematical calculations

### **Pandas** ✅ USED
- **Location:** `backend/scripts/structure_topics_template.py`
- **Usage:** 
  - Data analysis of past papers
  - Statistical calculations (median marks, topic distribution)
  - DataFrame operations for blueprint generation

**Status:** Both NumPy and Pandas actively used

---

## ✅ **3. SIMILARITY SEARCH**

### **FAISS** ✅ USED
- **Location:** 
  - `backend/app/agents/researcher.py` (ContentResearcher agent)
  - `backend/scripts/lectureslide_extract.py` (Index building)
  - `backend/scripts/generate_model_paper_openai.py`
- **Usage:**
  - Vector similarity search for lecture slides
  - Retrieval-Augmented Generation (RAG)
  - Finding relevant slide content for question generation
  - Index type: `IndexFlatIP` (Inner Product)
  - Normalization: L2 normalization

**Status:** Core component for RAG system

---

## ✅ **4. FRAMEWORKS**

### **FastAPI** ✅ USED (Instead of Flask/Streamlit)
- **Location:** `backend/app/main.py`, all API routes
- **Usage:**
  - REST API framework
  - Async request handling
  - Automatic API documentation
  - CORS middleware
- **Why FastAPI over Flask:**
  - Better async support
  - Automatic validation
  - Modern Python features

### **Flask** ❌ NOT USED
- FastAPI chosen instead

### **Streamlit** ❌ NOT USED
- Using React frontend instead

**Status:** FastAPI for backend, React for frontend

---

## ✅ **5. NLP & ML MODELS**

### **SBERT (Sentence-BERT)** ✅ USED
- **Model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Location:**
  - `backend/app/agents/researcher.py`
  - `backend/scripts/lectureslide_extract.py`
  - `backend/scripts/generate_model_paper_openai.py`
- **Usage:**
  - Generating embeddings for lecture slides
  - Converting text to vectors for FAISS search
  - Semantic similarity search

### **DistilBERT** ❌ NOT USED
- SBERT (based on BERT) used instead

### **FLAN-T5** ❌ NOT USED
- Using OpenAI-compatible LLMs (Llama 3.2) instead

### **LLM Models** ✅ USED
- **Primary:** Llama 3.2 (via Ollama)
- **Alternative:** GPT-4o-mini, GPT-4 (via OpenAI API)
- **Location:** `backend/app/agents/writer.py`, `backend/app/agents/critic.py`
- **Usage:**
  - Question generation
  - Quality validation
  - Content review

**Status:** SBERT for embeddings, LLMs for generation

---

## ✅ **6. PROGRAMMING LANGUAGES**

### **Python** ✅ USED
- **Location:** Entire backend
- **Usage:**
  - All server-side logic
  - Data processing
  - AI agent implementation
  - PDF processing
  - OCR operations

### **JavaScript** ✅ USED
- **Location:** `frontend/` directory
- **Framework:** React
- **Usage:**
  - Frontend UI
  - API calls to backend
  - File upload interface
  - Progress tracking

**Status:** Both languages actively used

---

## ✅ **7. DATABASE**

### **MongoDB** ✅ USED
- **Driver:** Motor (async MongoDB driver)
- **Location:**
  - `backend/app/core/db.py`
  - `backend/app/agents/orchestrator.py`
  - `backend/scripts/migrate_data.py`
- **Usage:**
  - Storing question templates
  - Storing canonical templates
  - Storing generated papers
  - Collections: `templates`, `canonical_templates`, `papers`
- **Connection:** MongoDB Atlas (cloud) or local

**Status:** Core database for template storage

---

## ✅ **8. PROJECT MANAGEMENT**

### **Jira** ❌ NOT USED (External Tool)
- Not part of codebase
- Likely used for project tracking externally

**Status:** External tool, not in code

---

## ✅ **9. OTHER TOOLS**

### **Git** ✅ USED (Version Control)
- **Location:** `.gitignore` file present
- **Usage:** Version control (standard practice)

### **Draw.io** ❌ NOT USED (External Tool)
- Not part of codebase
- Likely used for diagramming externally

---

## 🔧 **ADDITIONAL TECHNOLOGIES USED (Not in Diagram)**

### **Uvicorn** ✅ USED
- **Location:** `start_server.py`, `backend/scripts/run_server.py`
- **Usage:** ASGI server for FastAPI

### **PyMuPDF (fitz)** ✅ USED
- **Location:** `backend/scripts/pastpaper_extract.py`, `backend/scripts/lectureslide_extract.py`
- **Usage:** PDF rendering, page extraction

### **OpenCV (cv2)** ✅ USED
- **Location:** `backend/scripts/pastpaper_extract.py`, `backend/scripts/lectureslide_extract.py`
- **Usage:**
  - Image processing
  - Diagram detection (red/green boxes)
  - Image masking
  - Deskewing

### **Pytesseract** ✅ USED
- **Location:** `backend/scripts/pastpaper_extract.py`, `backend/scripts/lectureslide_extract.py`
- **Usage:** OCR (Optical Character Recognition) for scanned PDFs

### **FPDF** ✅ USED
- **Location:** `backend/app/services/pdf_service.py`
- **Usage:** PDF generation for model papers

### **Motor** ✅ USED
- **Location:** `backend/app/core/db.py`
- **Usage:** Async MongoDB driver

### **React** ✅ USED
- **Location:** `frontend/` directory
- **Usage:** Frontend framework

### **python-dotenv** ✅ USED
- **Location:** `backend/app/core/config.py`
- **Usage:** Environment variable management

---

## 📊 **SUMMARY TABLE**

| Category | Technology | Status | Usage Level |
|----------|-----------|--------|-------------|
| **Text Processing** | Regex | ✅ Used | Medium |
| | NLTK | ❌ Not Used | - |
| | spaCy | ❌ Not Used | - |
| **Data Handling** | NumPy | ✅ Used | High |
| | Pandas | ✅ Used | Medium |
| **Similarity Search** | FAISS | ✅ Used | High |
| **Frameworks** | FastAPI | ✅ Used | High |
| | Flask | ❌ Not Used | - |
| | Streamlit | ❌ Not Used | - |
| **NLP & ML** | SBERT | ✅ Used | High |
| | DistilBERT | ❌ Not Used | - |
| | FLAN-T5 | ❌ Not Used | - |
| | LLM (Llama/GPT) | ✅ Used | High |
| **Languages** | Python | ✅ Used | High |
| | JavaScript | ✅ Used | High |
| **Database** | MongoDB | ✅ Used | High |
| **Project Management** | Jira | ❌ External | - |
| **Other Tools** | Git | ✅ Used | Standard |
| | Draw.io | ❌ External | - |

---

## 🎯 **KEY TECHNOLOGIES BY FUNCTION**

### **Backend Framework:**
- ✅ FastAPI (not Flask/Streamlit)

### **Frontend:**
- ✅ React (JavaScript)

### **Database:**
- ✅ MongoDB with Motor

### **AI/ML:**
- ✅ SBERT for embeddings
- ✅ FAISS for similarity search
- ✅ LLM (Llama 3.2/GPT) for generation

### **Data Processing:**
- ✅ NumPy for arrays
- ✅ Pandas for analysis

### **PDF Processing:**
- ✅ PyMuPDF for extraction
- ✅ OpenCV for image processing
- ✅ Pytesseract for OCR
- ✅ FPDF for generation

---

## ✅ **FINAL COUNT**

**Technologies from Diagram:**
- ✅ Used: 8 out of 13
- ❌ Not Used: 5 (NLTK, spaCy, Flask, Streamlit, DistilBERT, FLAN-T5)
- ⚠️ External: 2 (Jira, Draw.io)

**Additional Technologies:**
- ✅ 8+ additional tools (Uvicorn, PyMuPDF, OpenCV, Pytesseract, FPDF, Motor, React, python-dotenv)

**Total Active Technologies:** ~16

---

*Last Updated: 2025-01-27*
*Based on codebase analysis*

