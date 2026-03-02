import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app.main import app
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
