FROM python:3.11-slim

WORKDIR /app

# System deps for PDF, NLP, etc.
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
COPY start_server.py ./
COPY config.py pdf_utils.py nlp_utils.py mcq_utils.py analysis_utils.py evaluation_utils.py main.py graph_utils.py ./

# Create dirs
RUN mkdir -p Lecture_slides Questions outputs static

ENV PORT=8002
EXPOSE 8002

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
