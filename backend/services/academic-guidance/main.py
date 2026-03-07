import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app.main import app
from app.core.config import settings

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
