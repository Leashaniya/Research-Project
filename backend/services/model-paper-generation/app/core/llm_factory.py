from openai import OpenAI
from app.core.config import settings

def get_llm_client():
    """
    Returns an initialized OpenAI client.
    Always uses standard OpenAI API 
    """
    # Always use OpenAI (Azure is not used)
    if not settings.OPENAI_API_KEY:
        raise ValueError("OpenAI API Key not set. Please set OPENAI_API_KEY in your .env file.")
    
    # Only set base_url if explicitly provided (for local LLMs like Ollama)
    # Do NOT set base_url for standard OpenAI API
    client_kwargs = {"api_key": settings.OPENAI_API_KEY}
    if settings.OPENAI_BASE_URL:
        # Only use base_url if it's explicitly set (for local LLMs)
        # Ensure it's not an Azure endpoint
        if "azure" not in settings.OPENAI_BASE_URL.lower() and "openai.azure.com" not in settings.OPENAI_BASE_URL.lower():
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL
        
    return OpenAI(**client_kwargs)
