import os
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY
import pytest
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

# Thay your_module bằng module thực tế chứa lớp DeepgramSTT
from your_module import DeepgramSTT

logging.disable(logging.CRITICAL)


# ===================== Fixtures =====================

@pytest.fixture
def mock_callbacks():
    return (
        MagicMock(),  # on_transcript
        MagicMock(),  # on_connect
        MagicMock(),  # on_close_cb
    )


@pytest.fixture
def mock_deepgram_client():
    with patch('your_module.AsyncDeepgramClient', autospec=True) as mock:
        yield mock


@pytest.fixture
def mock_environment(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test_api_key")


# ============================================================
# Test __init__
# ============================================================

class TestInit:
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT___init___001: Khởi tạo thành công với tham số hợp lệ.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )
        assert stt is not None
        assert stt.api_key == "test_api_key"
        assert stt.on_transcript is on_transcript
        assert stt.on_connect is on_connect
        assert stt.on_close_cb is on_close_cb
        assert stt.endpointing == 800
        assert isinstance(stt.client, AsyncDeepgramClient)

    @pytest.mark.asyncio
    async def test_missing_api_key(self, mock_deepgram_client, mock_callbacks, monkeypatch):
        """
        DeepgramSTT___init___002: Lỗi khi DEEPGRAM_API_KEY không tồn tại.
        """
        monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
        on_transcript, on_connect, on_close_cb = mock_callbacks
        with pytest.raises(ValueError, match="DEEPGRAM_API_KEY not found"):
            DeepgramSTT(
                on_transcript=on_transcript,
                on_connect=on_connect,
                on_close=on_close_cb,
                endpointing_ms=800
            )


# ============================================================
# Test send_finalize
# ============================================================

class TestSendFinalize:
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT_send_finalize_001: Gửi finalize thành công.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )
        mock_connection = AsyncMock()
        stt.connection = mock_connection
        await stt.send_finalize()
        mock_connection.send_finalize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connection_none(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT_send_finalize: Không gọi gì nếu connection là None.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )
        stt.connection = None
        await stt.send_finalize()  # Không ném lỗi

    @pytest.mark.asyncio
    async def test_error_in_send_finalize(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT_send_finalize_002: Lỗi từ connection.send_finalize được bắt và log.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )
        mock_connection = AsyncMock()
        mock_connection.send_finalize.side_effect = RuntimeError("Test error")
        stt.connection = mock_connection
        await stt.send_finalize()
        mock_connection.send_finalize.assert_awaited_once()


# ============================================================
# Test _keep_alive_loop
# ============================================================

class TestKeepAliveLoop:
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT__keep_alive_loop_001: Vòng lặp keep-alive chạy đúng.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )
        mock_connection = AsyncMock()
        # Lần đầu thành công, lần thứ hai ném lỗi để thoát vòng lặp
        mock_connection.send_keep_alive.side_effect = [None, RuntimeError("Stop")]
        stt.connection = mock_connection

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await stt._keep_alive_loop()
            assert mock_connection.send_keep_alive.call_count == 2
            mock_sleep.assert_awaited_once_with(4.0)

    @pytest.mark.asyncio
    async def test_connection_none(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT__keep_alive_loop: Khi connection None, vòng lặp không chạy.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )
        stt.connection = None
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await stt._keep_alive_loop()
            mock_sleep.assert_not_called()


# ============================================================
# Test run_stream
# ============================================================

class TestRunStream:
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_deepgram_client, mock_callbacks, mock_environment):
        """
        DeepgramSTT_run_stream_001: Stream chạy thành công và kết thúc khi nhận sentinel.
        """
        on_transcript, on_connect, on_close_cb = mock_callbacks
        stt = DeepgramSTT(
            on_transcript=on_transcript,
            on_connect=on_connect,
            on_close=on_close_cb,
            endpointing_ms=800
        )

        # Chuẩn bị audio queue với một chunk và sentinel
        audio_queue = asyncio.Queue()
        await audio_queue.put(b"audio_chunk_1")
        await audio_queue.put(None)

        # Mock connection và context manager
        mock_connection = AsyncMock()
        mock_connection.on = MagicMock()
        mock_connection.start_listening = AsyncMock()
        mock_connection.send_media = AsyncMock()
        mock_connection.send_finalize = AsyncMock()

        mock_connect_ctx = AsyncMock()
        mock_connect_ctx.__aenter__.return_value = mock_connection
        mock_connect_ctx.__aexit__.return_value = None

        stt.client = MagicMock()
        stt.client.listen.v1.connect.return_value = mock_connect_ctx

        await stt.run_stream(audio_queue)

        # Kiểm tra các lời gọi quan trọng
        stt.client.listen.v1.connect.assert_awaited_once()
        mock_connection.start_listening.assert_awaited_once()
        mock_connection.send_media.assert_awaited_once_with(b"audio_chunk_1")
        mock_connection.send_finalize.assert_awaited_once()
        # Kiểm tra rằng các event handler đã được đăng ký
        assert mock_connection.on.call_count == 3
        mock_connection.on.assert_any_call(EventType.MESSAGE, ANY)
        mock_connection.on.assert_any_call(EventType.ERROR, ANY)
        mock_connection.on.assert_any_call(EventType.CLOSE, ANY)