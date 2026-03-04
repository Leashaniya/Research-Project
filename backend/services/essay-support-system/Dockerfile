FROM python:3.11-slim

WORKDIR /app

# System deps for PDF processing (PyMuPDF) and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Application code
COPY app ./app

# Data and model files
COPY Data ./Data
COPY bloom_model.pkl ./

# Create dirs the app expects
RUN mkdir -p Data/Lecture_Notes Data/Past_papers

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=8002
EXPOSE 8002

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
