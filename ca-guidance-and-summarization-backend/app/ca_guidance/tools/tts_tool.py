import subprocess
import re
from pathlib import Path
from datetime import datetime

PIPER_EXE = r"D:\tools\piper\piper.exe"
PIPER_MODEL = r"D:\tools\piper\models\en_US-amy-low.onnx"

OUTPUT_DIR = Path("outputs/audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _strip_markdown_for_tts(text: str) -> str:
    """
    Remove markdown + image references so TTS doesn't read symbols, URLs, or image filenames.
    """
    if not text:
        return ""

    t = text

    # Remove "Related Images" section completely (heading + following lines)
    # Matches:
    # **Related Images:**
    # - [IMAGE:...]
    # - ![...](...)
    t = re.sub(r"\n?\*\*Related Images:\*\*.*$", "", t, flags=re.DOTALL)

    # Remove explicit image markers [IMAGE:filename]
    t = re.sub(r"\[IMAGE:[^\]]+\]", "", t)

    # Remove markdown images entirely (do NOT keep alt text, since it's often the filename)
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", t)

    # Remove fenced code blocks ```...```
    t = re.sub(r"```.*?```", "", t, flags=re.DOTALL)

    # Remove inline code `...`
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Bold / italic
    t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)
    t = re.sub(r"__(.*?)__", r"\1", t)
    t = re.sub(r"\*(.*?)\*", r"\1", t)
    t = re.sub(r"_(.*?)_", r"\1", t)

    # Headings ### Title -> Title
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)

    # Blockquotes > text -> text
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.MULTILINE)

    # Links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)

    # Bullet points (-, *, 1.)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)

    # Remove any leftover bare image filenames like something.png/jpg (extra safety)
    t = re.sub(r"\b\S+\.(png|jpg|jpeg|gif|webp)\b", "", t, flags=re.IGNORECASE)

    # Collapse extra whitespace/newlines
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()
def _strip_markdown_for_tts(text: str) -> str:
    """
    Remove markdown + image references so TTS doesn't read symbols, URLs, or image filenames.
    """
    if not text:
        return ""

    t = text

    # Remove "Related Images" section completely (heading + following lines)
    # Matches:
    # **Related Images:**
    # - [IMAGE:...]
    # - ![...](...)
    t = re.sub(r"\n?\*\*Related Images:\*\*.*$", "", t, flags=re.DOTALL)

    # Remove explicit image markers [IMAGE:filename]
    t = re.sub(r"\[IMAGE:[^\]]+\]", "", t)

    # Remove markdown images entirely (do NOT keep alt text, since it's often the filename)
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", t)

    # Remove fenced code blocks ```...```
    t = re.sub(r"```.*?```", "", t, flags=re.DOTALL)

    # Remove inline code `...`
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Bold / italic
    t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)
    t = re.sub(r"__(.*?)__", r"\1", t)
    t = re.sub(r"\*(.*?)\*", r"\1", t)
    t = re.sub(r"_(.*?)_", r"\1", t)

    # Headings ### Title -> Title
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)

    # Blockquotes > text -> text
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.MULTILINE)

    # Links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)

    # Bullet points (-, *, 1.)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)

    # Remove any leftover bare image filenames like something.png/jpg (extra safety)
    t = re.sub(r"\b\S+\.(png|jpg|jpeg|gif|webp)\b", "", t, flags=re.IGNORECASE)

    # Collapse extra whitespace/newlines
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


def text_to_speech_wav(text: str) -> str:
    # Clean markdown BEFORE sending to Piper
    clean_text = _strip_markdown_for_tts(text)

    if not clean_text:
        raise ValueError("Empty text cannot be converted to audio.")

    filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    out_path = OUTPUT_DIR / filename

    proc = subprocess.run(
        [PIPER_EXE, "--model", PIPER_MODEL, "--output_file", str(out_path)],
        input=clean_text,
        text=True,
        capture_output=True,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Piper failed: {proc.stderr}")

    return str(out_path).replace("\\", "/")
