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
        if not self.api_key or self.api_key.startswith("your-openrouter-api-key"):
            logger.warning("Using mock response because OPENROUTER_API_KEY is not set.")
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

