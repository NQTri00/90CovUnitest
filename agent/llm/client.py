import os
import time
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not found in environment variables.")
        
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key or "mock-key",
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "kimi/kimi-k2.6",
        response_format: Optional[Dict[str, Any]] = None,
        temperature: float = 0.1,
        max_retries: int = 3,
        backoff_in_seconds: int = 2,
    ) -> str:
        """
        Send a chat completion request to OpenRouter.
        """
        MOCK_KEY_PREFIXES = ("your-openrouter-api-key", "mock-key", "sk-test", "test-")
        if not self.api_key or any(self.api_key.startswith(p) for p in MOCK_KEY_PREFIXES):
            logger.warning("Using mock response because OPENROUTER_API_KEY is not set or is mock.")
            return '{"mocked": true}'

        for attempt in range(max_retries):
            try:
                # Add default headers for OpenRouter
                extra_headers = {
                    "HTTP-Referer": "https://github.com/anhluong447/90CovUnitest",
                    "X-Title": "Unit Test Agent",
                }
                
                params = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "extra_headers": extra_headers,
                    "max_tokens": 4096,
                }
                
                if response_format:
                    params["response_format"] = response_format

                response = self.client.chat.completions.create(**params)
                return response.choices[0].message.content
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise e
                time.sleep(backoff_in_seconds * (2 ** attempt))
                
        raise RuntimeError("Chat completion failed after all retries.")

def clean_json_response(content: str) -> str:
    """
    Cleans and extracts JSON block from a potentially noisy markdown string.
    """
    if not content:
        return ""
        
    s = content.strip()
    
    # Remove markdown code block markers
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
        
    if s.endswith("```"):
        s = s[:-3]
        
    s = s.strip()
    
    # Extract outermost braces to isolate JSON block from LLM chat wrapper text
    try:
        start_idx = s.index("{")
        end_idx = s.rindex("}")
        s = s[start_idx:end_idx + 1]
    except ValueError:
        pass
        
    return s


def robust_json_loads(content: str) -> Any:
    """
    Tries to load JSON, and if it fails, cleans common LLM malformations and retries.
    """
    if not content:
        return {}
        
    content = content.strip()
    
    import json
    import re
    import ast

    # Try 1: Standard json.loads
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try 2: Clean trailing commas
    # Remove trailing commas right before closing brackets/braces (e.g. [1, 2,] or {"a": 1,})
    cleaned = re.sub(r',\s*([\]}])', r'\1', content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try 3: ast.literal_eval fallback
    # Replace JSON-like values (true/false/null) to Python literals (True/False/None) 
    # so ast.literal_eval can read it!
    py_literal_str = cleaned.replace("true", "True").replace("false", "False").replace("null", "None")
    try:
        return ast.literal_eval(py_literal_str)
    except Exception:
        pass

    # Try 4: Fix unescaped newlines inside quotes
    try:
        fixed_newlines = re.sub(
            r'"([^"\\]*(?:\\.[^"\\]*)*)"',
            lambda m: m.group(0).replace('\n', '\\n').replace('\r', '\\r'),
            cleaned
        )
        return json.loads(fixed_newlines)
    except Exception:
        pass

    # If all fail, raise the original exception
    return json.loads(content)

