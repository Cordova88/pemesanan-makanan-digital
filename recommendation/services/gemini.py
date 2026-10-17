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

    def converse(
        self,
        message,
        system_instruction,
        tool_declarations,
        tool_handler,
        before_request,
        max_iterations,
    ):
        """Run Gemini's native function-calling loop.

        ``tool_handler`` is the Django-owned boundary. The provider never
        receives ORM access or executable code.
        """
        if self.client is None:
            return None, []

        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=message)],
            )
        ]
        tool = types.Tool(function_declarations=tool_declarations)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[tool],
            temperature=0.7,
            max_output_tokens=500,
        )
        tool_results = []
        for _ in range(max(1, max_iterations)):
            if not before_request():
                logger.warning("Gemini request limit reached before provider call")
                return None, tool_results
            try:
                response = self.client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                logger.warning(
                    "Gemini conversation request failed (%s)",
                    type(exc).__name__,
                )
                return None, tool_results
            candidate = (response.candidates or [None])[0]
            content = candidate.content if candidate else None
            if content is None:
                return None, tool_results
            contents.append(content)
            function_calls = [
                part.function_call
                for part in (content.parts or [])
                if part.function_call is not None
            ]
            if not function_calls:
                text = response.text or None
                if text:
                    logger.info(
                        "Gemini conversation response received (model=%s)",
                        settings.GEMINI_MODEL,
                    )
                return text, tool_results

            response_parts = []
            for function_call in function_calls:
                name = function_call.name or ""
                arguments = dict(function_call.args or {})
                logger.info(
                    "Gemini requested tool (name=%s, arguments=%s)",
                    name,
                    arguments,
                )
                result = tool_handler(name, arguments)
                tool_results.append(
                    {
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=name,
                            id=function_call.id,
                            response=result,
                        )
                    )
                )
            contents.append(
                types.Content(role="user", parts=response_parts)
            )
        logger.warning("Gemini conversation reached tool iteration limit")
        return None, tool_results
