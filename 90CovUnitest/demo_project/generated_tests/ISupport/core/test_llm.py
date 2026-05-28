import pytest
import os
import json
import httpx
import logging
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from openrouter_llm import OpenRouterLLM  # Giả sử module là openrouter_llm

logger = logging.getLogger(__name__)


# ========== Fixtures ==========

@pytest.fixture
def mock_env_vars():
    """Mock os.getenv và load_dotenv để kiểm soát biến môi trường."""
    with patch('openrouter_llm.load_dotenv') as mock_load_dotenv, \
         patch('openrouter_llm.os.getenv') as mock_getenv:
        yield mock_load_dotenv, mock_getenv


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient và các phương thức liên quan."""
    with patch('openrouter_llm.httpx.AsyncClient') as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance
        yield mock_client_instance


# ========== Tests for __init__ ==========

class TestInit:
    """Test cases for OpenRouterLLM.__init__"""

    def test_init_success(self, mock_env_vars):
        """Happy path: API key tồn tại trong environment."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        # Giả lập OPENROUTER_HAIKU_API_KEY có giá trị
        mock_getenv.side_effect = lambda key: {
            "OPENROUTER_HAIKU_API_KEY": "test-api-key-123",
            "OPENROUTER_API_KEY": None
        }.get(key)

        llm = OpenRouterLLM()

        # Kiểm tra instance được tạo thành công
        assert llm is not None
        assert llm.api_key == "test-api-key-123"

        # Verify các mock được gọi đúng
        mock_load_dotenv.assert_called_once()
        mock_getenv.assert_any_call("OPENROUTER_HAIKU_API_KEY")
        mock_getenv.assert_any_call("OPENROUTER_API_KEY")

    def test_init_fallback_api_key(self, mock_env_vars):
        """Fallback: OPENROUTER_HAIKU_API_KEY không có, dùng OPENROUTER_API_KEY."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        mock_getenv.side_effect = lambda key: {
            "OPENROUTER_HAIKU_API_KEY": None,
            "OPENROUTER_API_KEY": "fallback-api-key"
        }.get(key)

        llm = OpenRouterLLM()
        assert llm.api_key == "fallback-api-key"

    def test_init_missing_api_key(self, mock_env_vars):
        """Error path: không có API key nào -> raise ValueError."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        mock_getenv.return_value = None  # Cả hai key đều None

        with pytest.raises(ValueError, match="OPENROUTER_HAIKU_API_KEY not found"):
            OpenRouterLLM()

        mock_load_dotenv.assert_called_once()
        mock_getenv.assert_any_call("OPENROUTER_HAIKU_API_KEY")
        mock_getenv.assert_any_call("OPENROUTER_API_KEY")


# ========== Tests for get_suggestions_stream ==========

class TestGetSuggestionsStream:
    """Test cases for OpenRouterLLM.get_suggestions_stream"""

    @pytest.mark.asyncio
    async def test_stream_success(self, mock_env_vars, mock_httpx_client):
        """Happy path: API trả về streaming thành công."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        mock_getenv.side_effect = lambda key: {
            "OPENROUTER_HAIKU_API_KEY": "test-api-key",
            "OPENROUTER_API_KEY": None
        }.get(key)

        # Tạo mock response stream
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = AsyncMock(return_value=async_generator([
            "data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}",
            "data: {\"choices\":[{\"delta\":{\"content\":\" world\"}}]}",
            "data: [DONE]"
        ]))
        mock_response.aread = AsyncMock(return_value=b"")

        # Cấu hình mock client.stream trả về mock_response
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__.return_value = mock_response
        mock_httpx_client.stream.return_value = mock_stream_context

        llm = OpenRouterLLM()
        config = {
            "model": "anthropic/claude-3.5-haiku",
            "system_prompt": "You are helpful",
            "context": "Some context",
            "max_tokens": 500
        }
        history = [{"role": "user", "content": "previous"}]

        # Thu thập các chunk từ async generator
        chunks = []
        async for chunk in llm.get_suggestions_stream("What is AI?", config, history):
            chunks.append(chunk)

        assert chunks == ["Hello", " world"]

        # Verify các mock
        mock_httpx_client.stream.assert_called_once_with(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-api-key",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/google-deepmind/antigravity",
                "X-Title": "Interview Assistant"
            },
            json={
                "model": "anthropic/claude-3.5-haiku",
                "messages": [
                    {"role": "system", "content": "You are helpful\n\n[CONTEXT / MY BACKGROUND]:\nSome context"},
                    {"role": "user", "content": "previous"},
                    {"role": "user", "content": "What is AI?"}
                ],
                "stream": True,
                "max_tokens": 500,
                "temperature": 0.3
            }
        )

    @pytest.mark.asyncio
    async def test_stream_model_mapping(self, mock_env_vars, mock_httpx_client):
        """Kiểm tra mapping model generic name sang full name."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        mock_getenv.side_effect = lambda key: {
            "OPENROUTER_HAIKU_API_KEY": "test-api-key",
            "OPENROUTER_API_KEY": None
        }.get(key)

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = AsyncMock(return_value=async_generator([
            "data: {\"choices\":[{\"delta\":{\"content\":\"test\"}}]}",
            "data: [DONE]"
        ]))
        mock_response.aread = AsyncMock(return_value=b"")

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__.return_value = mock_response
        mock_httpx_client.stream.return_value = mock_stream_context

        llm = OpenRouterLLM()
        config = {"model": "sonnet"}  # Generic name

        chunks = []
        async for chunk in llm.get_suggestions_stream("test", config):
            chunks.append(chunk)

        # Kiểm tra model đã được map thành "anthropic/claude-3.5-sonnet"
        call_args = mock_httpx_client.stream.call_args
        assert call_args[1]['json']['model'] == "anthropic/claude-3.5-sonnet"

    @pytest.mark.asyncio
    async def test_stream_http_error(self, mock_env_vars, mock_httpx_client):
        """Error path: API trả về status code != 200."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        mock_getenv.side_effect = lambda key: {
            "OPENROUTER_HAIKU_API_KEY": "test-api-key",
            "OPENROUTER_API_KEY": None
        }.get(key)

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.aread = AsyncMock(return_value=b"Internal Server Error")
        # aiter_lines không cần thiết vì không vào stream

        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__.return_value = mock_response
        mock_httpx_client.stream.return_value = mock_stream_context

        llm = OpenRouterLLM()
        config = {"model": "haiku"}

        chunks = []
        async for chunk in llm.get_suggestions_stream("test", config):
            chunks.append(chunk)

        # Kiểm tra yield error message
        assert len(chunks) == 1
        assert "[Error: OpenRouter API returned status 500" in chunks[0]

    @pytest.mark.asyncio
    async def test_stream_request_exception(self, mock_env_vars, mock_httpx_client):
        """Error path: httpx request exception."""
        mock_load_dotenv, mock_getenv = mock_env_vars
        mock_getenv.side_effect = lambda key: {
            "OPENROUTER_HAIKU_API_KEY": "test-api-key",
            "OPENROUTER_API_KEY": None
        }.get(key)

        # Giả lập client.stream raise exception
        mock_httpx_client.stream.side_effect = httpx.RequestError("Connection timeout")

        llm = OpenRouterLLM()
        config = {"model": "haiku"}

        chunks = []
        async for chunk in llm.get_suggestions_stream("test", config):
            chunks.append(chunk)

        # Kiểm tra yield error message
        assert len(chunks) == 1
        assert "[Error communicating with OpenRouter" in chunks[0]


# ========== Helper ==========

def async_generator(items):
    """Helper để tạo async generator từ list."""
    async def gen():
        for item in items:
            yield item
    return gen()