from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Retrieve the OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class Settings:
    OPENAI_API_KEY = OPENAI_API_KEY
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")

    def validate_openai_key(self):
        if not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is missing. Please set it before using the generation endpoint.")

settings = Settings()