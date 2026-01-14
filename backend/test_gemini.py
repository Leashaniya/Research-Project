import time
from google import genai

# Replace with your actual key
client = genai.Client(api_key="AIzaSyBGHQut9nZ9TEjyoi1USDdOT5lfW-ex0Ko") 

def safe_generate(prompt):
    try:
        # Use the newest 2026 stable model
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        print("Gemini says:", response.text)
    except Exception as e:
        if "429" in str(e):
            print("Speed limit hit! Waiting 65 seconds...")
            time.sleep(65) # Wait and try once more
            safe_generate(prompt)
        else:
            print(f"Error: {e}")

safe_generate("Hello! Is my new key working now?")