FROM python:3.11-slim

WORKDIR /app

# System deps for some Python packages (e.g. opencv, pdf) and for Piper TTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from pyproject.toml
COPY pyproject.toml README.md* ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Application code
COPY . .

# Piper TTS: download Linux binary for this architecture (arm64 on Apple Silicon, x86_64 on Intel/AMD)
ENV PIPER_DIR=/app/piper
ARG TARGETARCH
RUN PIPER_ARCH=$(echo "${TARGETARCH}" | sed 's/amd64/x86_64/;s/arm64/aarch64/') \
    && mkdir -p "${PIPER_DIR}/voices" \
    && wget -q -O /tmp/piper.tar.gz "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_${PIPER_ARCH}.tar.gz" \
    && tar -xzf /tmp/piper.tar.gz -C /tmp && mv /tmp/piper/* "${PIPER_DIR}/" && rm -rf /tmp/piper /tmp/piper.tar.gz \
    && wget -q -O "${PIPER_DIR}/voices/en_US-amy-low.onnx" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx" \
    && wget -q -O "${PIPER_DIR}/voices/en_US-amy-low.onnx.json" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx.json" \
    && chmod +x "${PIPER_DIR}/piper"
ENV PIPER_EXE=${PIPER_DIR}/piper
ENV PIPER_MODEL=${PIPER_DIR}/voices/en_US-amy-low.onnx
# So the Piper binary finds its .so files (libpiper_phonemize, etc.) at runtime
ENV LD_LIBRARY_PATH=${PIPER_DIR}:${LD_LIBRARY_PATH:-}

# Run as non-root
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=8000
EXPOSE 8000

# When behind gateway, app still serves at root; gateway strips /guidance
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
