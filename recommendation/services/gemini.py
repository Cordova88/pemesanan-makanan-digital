
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env", override=True)


class GeminiClient:
    def __init__(self):
        self.client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=15000),
            )
        
    def generate(self, prompt):
        if self.client is None:
            return None
        try:
            response = self.client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
            )
            
            return response.text
        except Exception as e:
            print(f"Error generating content: {e}", flush=True)
            return 
        
