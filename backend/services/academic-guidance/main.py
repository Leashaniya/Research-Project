import os
import uvicorn
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the service root (works regardless of CWD when started via script/Docker)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

from app.main import app
from app.core.config import settings

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
