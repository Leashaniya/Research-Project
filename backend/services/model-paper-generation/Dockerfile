FROM python:3.11-slim

WORKDIR /app

# System deps for scripts (tesseract for OCR, opencv libs, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Application code (app + scripts)
COPY app ./app
COPY scripts ./scripts
COPY start_server.py run_full_pipeline.py ./
# Optional: copy data/ if you bake data into image; else mount at runtime
# COPY data ./data

# Create dirs the app expects (see app/core/paths.py)
RUN mkdir -p data/past_paper_red_box data/lectureslides data/text_extraction_hybrid \
    data/_tmp_pdf_pages_hybrid data/lecture_slides_extraction data/slides_embeddings \
    data/artifacts data/outputs

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=8001
EXPOSE 8001

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
