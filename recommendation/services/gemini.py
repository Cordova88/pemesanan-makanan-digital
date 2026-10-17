import logging
import os
from pathlib import Path

from django.conf import settings
from dotenv import load_dotenv
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env", override=False)

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self):
        self.client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=15000),
            )

    @property
    def available(self):
        return self.client is not None

    def generate(self, prompt):
        if self.client is None:
            return None
        model = settings.GEMINI_MODEL
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
            )
            text = response.text or None
            if text:
                logger.info("Gemini provider response received (model=%s)", model)
            else:
                logger.info("Gemini provider returned no text (model=%s)", model)
            return text
        except Exception as exc:
            logger.warning("Gemini provider request failed (%s)", type(exc).__name__)
            return None
