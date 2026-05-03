import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.core.config import settings, AUDIO_OUTPUT_DIR

OUTPUT_DIR = AUDIO_OUTPUT_DIR


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

    # Remove tables (entire content between [TABLE] and next double newline or end of text)
    t = re.sub(r"\[TABLE\][\s\S]*?(?=\n\n|\Z)", "", t)

    return t.strip()


def text_to_speech_wav(text: str) -> Optional[str]:
    """
    Convert text to WAV using Piper. Returns path to WAV file, or None if TTS is not
    configured (PIPER_EXE/PIPER_MODEL unset or missing) so callers can skip audio.
    """
    import logging
    _log = logging.getLogger(__name__)
    piper_exe = (settings.PIPER_EXE or "").strip()
    piper_model = (settings.PIPER_MODEL or "").strip()
    if not piper_exe or not piper_model:
        _log.info("TTS skipped: PIPER_EXE or PIPER_MODEL not set")
        return None
    if not Path(piper_exe).exists():
        _log.warning("TTS skipped: Piper binary not found at %s", piper_exe)
        return None
    model_path = Path(piper_model)
    if not model_path.exists():
        _log.warning("TTS skipped: Piper model not found at %s", piper_model)
        return None
    config_path = Path(f"{piper_model}.json")
    if not config_path.exists():
        raise RuntimeError(
            "Piper model config file is missing. Expected "
            f"{config_path}. Download the matching .onnx.json file for this voice "
            "or set PIPER_MODEL to a model that has its companion JSON file."
        )

    # Clean markdown BEFORE sending to Piper
    clean_text = _strip_markdown_for_tts(text)

    if not clean_text:
        raise ValueError("Empty text cannot be converted to audio.")

    filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    out_path = OUTPUT_DIR / filename

    cmd = [piper_exe, "--model", piper_model, "--config", str(config_path), "--output_file", str(out_path)]
    espeak_data = Path(piper_exe).parent / "espeak-ng-data"
    if espeak_data.exists():
        cmd.extend(["--espeak_data", str(espeak_data)])

    proc = subprocess.run(
        cmd,
        input=clean_text,
        text=True,
        capture_output=True,
    )

    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout or "").strip()
        if not details:
            details = f"exit code {proc.returncode}"
        raise RuntimeError(f"Piper failed: {details}")

    return str(out_path).replace("\\", "/")
