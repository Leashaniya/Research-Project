from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Retrieve the OpenAI API key from environment variables
# Retrieve the OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") # Optional: For Local LLM (e.g. http://localhost:11434/v1)

class Settings:
    OPENAI_API_KEY = OPENAI_API_KEY
    OPENAI_BASE_URL = OPENAI_BASE_URL
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "llama3.2") # Default to Local
    
    # MongoDB Config
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://it22891440_db_user:leasha@cluster0.nrfff5z.mongodb.net/?appName=Cluster0")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "pastpaper_db")


    def validate_openai_key(self):
        if not self.OPENAI_API_KEY:
            raise ValueError("AI Cloud API Key is missing. Please set it before using the generation endpoint.")

settings = Settings()