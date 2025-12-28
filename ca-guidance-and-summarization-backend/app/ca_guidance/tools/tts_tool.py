import subprocess
from pathlib import Path
from datetime import datetime

PIPER_EXE = r"D:\tools\piper\piper.exe"
PIPER_MODEL = r"D:\tools\piper\models\en_US-amy-low.onnx"

OUTPUT_DIR = Path("outputs/audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def text_to_speech_wav(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text cannot be converted to audio.")

    filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    out_path = OUTPUT_DIR / filename

    proc = subprocess.run(
        [PIPER_EXE, "--model", PIPER_MODEL, "--output_file", str(out_path)],
        input=text,
        text=True,
        capture_output=True,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Piper failed: {proc.stderr}")

    return str(out_path).replace("\\", "/")
