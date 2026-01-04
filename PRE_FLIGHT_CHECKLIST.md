# Pre-Flight Checklist: Model Paper Generation System
## Ready to Run? Complete Verification Guide

---

## ✅ **SYSTEM FLOW OVERVIEW**

When you run `run_all.py`, here's what happens:

1. **Backend Server Starts** (`start_server.py`)
   - FastAPI server on `http://127.0.0.1:8000`
   - Creates required directories
   - Initializes MongoDB connection

2. **Frontend Starts** (`npm start`)
   - React app on `http://localhost:3000`
   - Connects to backend API

3. **User Flow (via Frontend):**
   - Upload past papers → `data/past_paper_red_box/`
   - Upload lecture slides → `data/lectureslides/`
   - Click "Generate Paper" → Triggers `/model-paper/generate-paper`
   - Pipeline runs: Extraction → Blueprinting → AI Generation
   - Download PDF/JSON result

---

## 🔍 **PRE-FLIGHT CHECKS**

### 1. **Environment Variables** ✅ REQUIRED

**File:** `backend/.env` (or root `.env`)

**Required Variables:**
```env
# LLM Configuration (for Llama 3.2)
OPENAI_API_KEY=dummy_key  # Required even for local LLM (can be any string)
OPENAI_BASE_URL=http://localhost:11434/v1  # Ollama endpoint
OPENAI_MODEL=llama3.2  # or llama3.1, etc.

# MongoDB (already has default in config.py)
MONGO_URI=mongodb+srv://it22891440_db_user:leasha@cluster0.nrfff5z.mongodb.net/?appName=Cluster0
MONGO_DB_NAME=pastpaper_db
```

**Check:**
- [ ] `.env` file exists in `backend/` directory
- [ ] `OPENAI_API_KEY` is set (can be dummy for local LLM)
- [ ] `OPENAI_BASE_URL` points to your Ollama server (if using local LLM)
- [ ] `OPENAI_MODEL` matches your installed model

**If Missing:**
```bash
# Create backend/.env
cd backend
echo "OPENAI_API_KEY=dummy_key" > .env
echo "OPENAI_BASE_URL=http://localhost:11434/v1" >> .env
echo "OPENAI_MODEL=llama3.2" >> .env
```

---

### 2. **Python Dependencies** ✅ REQUIRED

**Check if installed:**
```bash
cd backend
python -m pip list | findstr "fastapi motor uvicorn openai sentence-transformers faiss-cpu fpdf pymupdf pytesseract"
```

**Required Packages:**
- [ ] `fastapi` - Web framework
- [ ] `uvicorn` - ASGI server
- [ ] `motor` - MongoDB async driver
- [ ] `openai` - LLM client (works with local LLMs via base_url)
- [ ] `sentence-transformers` - Embeddings for RAG
- [ ] `faiss-cpu` - Vector search
- [ ] `fpdf` - PDF generation
- [ ] `pymupdf` (fitz) - PDF processing
- [ ] `pytesseract` - OCR
- [ ] `opencv-python` - Image processing
- [ ] `numpy` - Numerical operations
- [ ] `python-dotenv` - Environment variables

**If Missing:**
```bash
pip install fastapi uvicorn motor openai sentence-transformers faiss-cpu fpdf pymupdf pytesseract opencv-python numpy python-dotenv
```

---

### 3. **Node.js Dependencies** ✅ REQUIRED

**Check:**
```bash
cd frontend
npm list --depth=0
```

**Required:**
- [ ] `react` - Frontend framework
- [ ] `react-dom` - DOM rendering
- [ ] `axios` or `fetch` - API calls

**If Missing:**
```bash
cd frontend
npm install
```

---

### 4. **MongoDB Connection** ✅ REQUIRED

**Check:**
- [ ] MongoDB URI is accessible (default is cloud MongoDB)
- [ ] Database `pastpaper_db` exists (will be created if missing)
- [ ] Network allows connection to MongoDB Atlas

**Test Connection:**
```python
# Run: python backend/scripts/test_mongo_connection.py
# Or check in start_server.py - it verifies motor import
```

---

### 5. **Local LLM (Ollama)** ✅ REQUIRED for Llama

**Check:**
- [ ] Ollama is installed and running
- [ ] Model `llama3.2` (or configured model) is downloaded
- [ ] Ollama API is accessible at `http://localhost:11434/v1`

**Test:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check if model exists
ollama list

# If missing, pull model:
ollama pull llama3.2
```

**If not using local LLM:**
- Set `OPENAI_BASE_URL` to empty string
- Set `OPENAI_MODEL` to `gpt-4o-mini` or `gpt-4`
- Provide valid `OPENAI_API_KEY`

---

### 6. **Directory Structure** ✅ AUTO-CREATED

**Required Directories (created automatically by `main.py`):**
- [x] `data/past_paper_red_box/` - Upload past papers here
- [x] `data/lectureslides/` - Upload lecture slides here
- [x] `data/outputs/model_papers/` - Generated papers
- [x] `data/artifacts/` - Blueprints and templates
- [x] `data/text_extraction_hybrid/` - Extracted text
- [x] `data/lecture_slides_extraction/` - Slide chunks
- [x] `data/slides_embeddings/` - FAISS index

**Note:** These are created automatically on server startup.

---

### 7. **Image Processing** ⚠️ NOT ACTIVE

**Status:** Image/diagram processing is **DISABLED** and will be implemented later.

**Current Behavior:**
- Questions use `[PLACEHOLDER FIGURE]` text placeholders for diagrams
- PDFs show placeholder text instead of images
- This is intentional and working as designed

**No Action Required:** System works correctly with text placeholders.

---

### 8. **Tesseract OCR** ⚠️ OPTIONAL (for PDF extraction)

**If processing scanned PDFs:**
- [ ] Tesseract OCR is installed
- [ ] `TESSERACT_CMD` environment variable is set (if not in PATH)

**Windows:**
```bash
# Set environment variable:
setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

**Check:**
```bash
tesseract --version
```

---

### 8. **Input Files** ⚠️ REQUIRED for Generation

**Before generating a paper:**
- [ ] At least 1 past paper PDF in `data/past_paper_red_box/`
- [ ] At least 1 lecture slide PDF in `data/lectureslides/` (recommended)

**Note:** System will work with just past papers, but slides improve context.

---

## 🚀 **RUNNING THE SYSTEM**

### Step 1: Start Services
```bash
python run_all.py
```

**Expected Output:**
```
🚀 Starting Backend...
🐍 Python: C:\...\python.exe
📂 Root: C:\...\Research Project
📂 Backend: C:\...\Research Project\backend
✅ Motor check passed.
🚀 Starting Server (http://127.0.0.1:8000)...
🚀 Starting Frontend...

✅ Services launched!
Backend: http://127.0.0.1:8000
Frontend: http://localhost:3000
```

### Step 2: Access Frontend
Open browser: `http://localhost:3000`

### Step 3: Upload Files
1. Upload past papers (PDFs)
2. Upload lecture slides (PDFs)
3. Click "Process Files" (optional - auto-runs on generate)
4. Click "Generate Paper"

### Step 4: Monitor Progress
- Check backend console for agent logs
- Check frontend for step-by-step progress
- Wait for completion (5-10 minutes typical)

### Step 5: Download Results
- JSON: `/model-paper/paper-json`
- PDF: `/model-paper/download-pdf`

---

## ⚠️ **COMMON ISSUES & FIXES**

### Issue 1: "Motor check failed"
**Fix:**
```bash
pip install motor
```

### Issue 2: "OPENAI_API_KEY missing"
**Fix:**
- Create `backend/.env` with `OPENAI_API_KEY=dummy_key`
- Or set environment variable: `set OPENAI_API_KEY=dummy_key`

### Issue 3: "Connection refused" (Ollama)
**Fix:**
- Start Ollama: `ollama serve`
- Or change to cloud LLM in `.env`

### Issue 4: "MongoDB connection failed"
**Fix:**
- Check internet connection (MongoDB Atlas requires internet)
- Verify MongoDB URI in `.env`
- Check firewall settings

### Issue 5: "No blueprint found"
**Fix:**
- Upload past papers first
- Run `/model-paper/process-files` endpoint
- Check `data/artifacts/exam_blueprint_template.json` exists

### Issue 6: "Frontend won't start"
**Fix:**
```bash
cd frontend
npm install
npm start
```

### Issue 7: "Port 8000 already in use"
**Fix:**
- Kill process using port 8000
- Or change port in `start_server.py` and `run_all.py`

---

## ✅ **FINAL VERIFICATION**

Before running `run_all.py`, verify:

1. [ ] `.env` file exists with required variables
2. [ ] Python dependencies installed
3. [ ] Node.js dependencies installed
4. [ ] Ollama running (if using local LLM)
5. [ ] MongoDB accessible
6. [ ] At least 1 past paper PDF ready
7. [ ] Ports 8000 and 3000 available

---

## 📊 **SYSTEM STATUS CHECK**

Run this quick test:

```python
# test_system.py
import sys
import os
sys.path.append('backend')

# Check config
from app.core.config import settings
print(f"✅ Config loaded")
print(f"   Model: {settings.OPENAI_MODEL}")
print(f"   Base URL: {settings.OPENAI_BASE_URL or 'Cloud'}")
print(f"   MongoDB: {settings.MONGO_URI[:30]}...")

# Check MongoDB
from app.core.db import db
try:
    db.connect()
    print("✅ MongoDB connected")
    db.close()
except Exception as e:
    print(f"❌ MongoDB failed: {e}")

# Check paths
from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR
print(f"✅ Paths configured")
print(f"   Past Papers: {PAST_PAPERS_DIR}")
print(f"   Slides: {SLIDES_DIR}")
```

---

## 🎯 **READY TO GO?**

If all checks pass:
1. ✅ Run `python run_all.py`
2. ✅ Open `http://localhost:3000`
3. ✅ Upload files and generate!

**Expected Runtime:**
- File processing: 2-5 minutes (per PDF)
- Blueprint generation: 1-2 minutes
- Model paper generation: 5-10 minutes (5 questions)
- **Total: ~10-20 minutes for first run**

---

*Last Updated: 2025-01-27*
*System Version: Agentic Pipeline V1*

