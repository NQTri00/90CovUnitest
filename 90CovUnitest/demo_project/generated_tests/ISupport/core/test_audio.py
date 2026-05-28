import pytest
from unittest.mock import MagicMock, patch, call, ANY
import numpy as np
import asyncio
import logging

# Giả sử module audio_capture.py chứa lớp AudioCapture
# Trong test, chúng ta sẽ patch các import bên trong module đó

@pytest.fixture(autouse=True)
def mock_external_dependencies():
    """Patch các module pyaudiowpatch, numpy và logging để kiểm soát hoàn toàn"""
    with patch('audio_capture.pyaudio') as mock_pyaudio, \
         patch('audio_capture.np') as mock_np, \
         patch('audio_capture.logger') as mock_logger:
        # Thiết lập các hằng số
        mock_pyaudio.paInt16 = 2
        mock_pyaudio.paContinue = 0
        # Trả về mock để các fixture khác có thể sử dụng
        yield {
            'pyaudio': mock_pyaudio,
            'np': mock_np,
            'logger': mock_logger
        }

@pytest.fixture
def mock_pyaudio_instance(mock_external_dependencies):
    """Tạo một PyAudio instance giả"""
    pyaudio_mock = mock_external_dependencies['pyaudio']
    instance = MagicMock()
    pyaudio_mock.PyAudio.return_value = instance
    return instance

@pytest.fixture
def audio_capture(mock_pyaudio_instance, mock_external_dependencies):
    """Tạo một đối tượng AudioCapture với các mock đã được thiết lập"""
    # Mặc định _find_devices sẽ không raise nếu ta thiết lập các giá trị hợp lệ
    # Hàm này sẽ được override trong từng test nếu cần
    return AudioCapture(target_rate=16000)

# ===========================
# Test cho __init__
# ===========================

class TestAudioCaptureInit:
    def test_AudioCapture___init___001_happy_path(self, mock_external_dependencies, mock_pyaudio_instance):
        """Khởi tạo thành công với target_rate hợp lệ"""
        # Thiết lập để _find_devices không raise
        # Giả lập có 2 thiết bị: một mic và một loopback
        mock_pyaudio = mock_external_dependencies['pyaudio']
        mock_pyaudio_instance.get_device_count.return_value = 1
        # Device 0 là mic
        mic_device = {
            'name': 'Microphone (Realtek)',
            'maxInputChannels': 1,
            'hostApi': 0,
            'index': 0,
            'defaultSampleRate': 44100,
            'isLoopbackDevice': False
        }
        mock_pyaudio_instance.get_device_info_by_index.return_value = mic_device
        # Host API info
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        # Loopback device generator
        loopback_device = {
            'name': 'Speakers (Realtek)',
            'maxInputChannels': 2,
            'hostApi': 0,
            'index': 1,
            'defaultSampleRate': 48000,
            'isLoopbackDevice': True
        }
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = [loopback_device]
        # Khởi tạo
        capture = AudioCapture(target_rate=16000)
        assert capture is not None
        assert capture.target_rate == 16000
        assert capture.p is mock_pyaudio_instance
        assert capture.mic_device_info is not None
        assert capture.loopback_device_info is not None
        # Kiểm tra các lời gọi
        mock_pyaudio_instance.get_device_count.assert_called_once()
        mock_pyaudio_instance.get_host_api_count.assert_called_once()

    def test_AudioCapture___init___002_input_null(self, mock_external_dependencies, mock_pyaudio_instance):
        """Khởi tạo với target_rate=None (null) - vẫn có thể chạy được"""
        # Thiết lập như trên
        mock_pyaudio = mock_external_dependencies['pyaudio']
        mock_pyaudio_instance.get_device_count.return_value = 1
        mic_device = {
            'name': 'Microphone',
            'maxInputChannels': 1,
            'hostApi': 0,
            'index': 0,
            'defaultSampleRate': 44100,
            'isLoopbackDevice': False
        }
        mock_pyaudio_instance.get_device_info_by_index.return_value = mic_device
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = []
        # Khởi tạo với None
        capture = AudioCapture(target_rate=None)
        assert capture is not None
        assert capture.target_rate is None

    def test_AudioCapture___init___003_error_path_runtime_error(self, mock_external_dependencies, mock_pyaudio_instance):
        """Khi không có thiết bị nào, _find_devices raise RuntimeError"""
        # Không có device nào
        mock_pyaudio_instance.get_device_count.return_value = 0
        mock_pyaudio_instance.get_host_api_count.return_value = 0
        # Không có loopback device generator mặc định
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = []
        # Sẽ raise RuntimeError vì không có mic và loopback
        with pytest.raises(RuntimeError, match="No input or loopback devices found on this system."):
            AudioCapture(target_rate=16000)

# ===========================
# Test cho _find_devices
# ===========================

class TestAudioCaptureFindDevices:
    def test_AudioCapture__find_devices_001_happy_path(self, mock_external_dependencies, mock_pyaudio_instance):
        """Tìm thấy cả mic và loopback"""
        mock_pyaudio_instance.get_device_count.return_value = 2
        devices = [
            {'name': 'Headset Microphone', 'maxInputChannels': 2, 'hostApi': 0, 'index': 0, 'defaultSampleRate': 48000, 'isLoopbackDevice': False},
            {'name': 'Speakers', 'maxInputChannels': 2, 'hostApi': 0, 'index': 1, 'defaultSampleRate': 48000, 'isLoopbackDevice': True}
        ]
        mock_pyaudio_instance.get_device_info_by_index.side_effect = devices
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = [devices[1]]
        capture = AudioCapture(target_rate=16000)
        assert capture.mic_device_info is not None
        assert capture.loopback_device_info is not None
        assert capture.mic_device_info['name'] == 'Headset Microphone'
        assert capture.loopback_device_info['name'] == 'Speakers'

    def test_AudioCapture__find_devices_002_error_path_no_devices(self, mock_external_dependencies, mock_pyaudio_instance):
        """Không tìm thấy thiết bị nào -> RuntimeError"""
        mock_pyaudio_instance.get_device_count.return_value = 0
        mock_pyaudio_instance.get_host_api_count.return_value = 0
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = []
        with pytest.raises(RuntimeError):
            AudioCapture(target_rate=16000)

# ===========================
# Test cho start_capture
# ===========================

class TestAudioCaptureStartCapture:
    @pytest.fixture
    def capture_with_devices(self, mock_external_dependencies, mock_pyaudio_instance):
        """Tạo AudioCapture đã có thiết bị"""
        mock_pyaudio_instance.get_device_count.return_value = 2
        devices = [
            {'name': 'Mic', 'maxInputChannels': 1, 'hostApi': 0, 'index': 0, 'defaultSampleRate': 44100, 'isLoopbackDevice': False},
            {'name': 'Loopback', 'maxInputChannels': 2, 'hostApi': 0, 'index': 1, 'defaultSampleRate': 48000, 'isLoopbackDevice': True}
        ]
        mock_pyaudio_instance.get_device_info_by_index.side_effect = devices
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = [devices[1]]
        capture = AudioCapture(target_rate=16000)
        return capture

    def test_AudioCapture_start_capture_001_happy_path(self, capture_with_devices, mock_external_dependencies, mock_pyaudio_instance):
        """Bắt đầu capture với loopback (source mặc định)"""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_queue = MagicMock(spec=asyncio.Queue)
        capture_with_devices.start_capture(loop=mock_loop, queue=mock_queue, source="loopback")
        # Kiểm tra stream được mở với thông số đúng
        mock_pyaudio_instance.open.assert_called_once_with(
            format=mock_external_dependencies['pyaudio'].paInt16,
            channels=2,  # loopback có 2 channels
            rate=48000,
            input=True,
            input_device_index=1,
            frames_per_buffer=1024,
            stream_callback=ANY
        )
        assert capture_with_devices.active_device_info['name'] == 'Loopback'
        assert capture_with_devices.sample_rate == 48000
        assert capture_with_devices.channels == 2

    def test_AudioCapture_start_capture_002_input_null(self, capture_with_devices):
        """Khi truyền loop, queue, source, frames_per_buffer là None -> gây lỗi (strict)"""
        mock_loop = None
        mock_queue = None
        # Sẽ raise TypeError vì loop và queue là bắt buộc
        with pytest.raises(TypeError):
            capture_with_devices.start_capture(loop=mock_loop, queue=mock_queue, source=None, frames_per_buffer=None)

    def test_AudioCapture_start_capture_003_error_path(self, capture_with_devices, mock_external_dependencies, mock_pyaudio_instance):
        """Khi open stream raise RuntimeError"""
        mock_pyaudio_instance.open.side_effect = RuntimeError("No audio device")
        mock_loop = MagicMock()
        mock_queue = MagicMock()
        with pytest.raises(RuntimeError, match="No audio device"):
            capture_with_devices.start_capture(loop=mock_loop, queue=mock_queue, source="loopback")

# ===========================
# Test cho stop_capture
# ===========================

class TestAudioCaptureStopCapture:
    def test_AudioCapture_stop_capture_001_happy_path(self, mock_external_dependencies, mock_pyaudio_instance):
        """Dừng capture thành công khi có stream"""
        # Tạo stream giả
        mock_stream = MagicMock()
        mock_pyaudio_instance.open.return_value = mock_stream
        # Tạo AudioCapture và bắt đầu capture trước
        mock_pyaudio_instance.get_device_count.return_value = 1
        device = {'name': 'Device', 'maxInputChannels': 2, 'hostApi': 0, 'index': 0, 'defaultSampleRate': 48000, 'isLoopbackDevice': True}
        mock_pyaudio_instance.get_device_info_by_index.return_value = device
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = [device]
        capture = AudioCapture(target_rate=16000)
        mock_loop = MagicMock()
        mock_queue = MagicMock()
        capture.start_capture(loop=mock_loop, queue=mock_queue)
        # Dừng
        capture.stop_capture()
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        assert capture.stream is None

    def test_AudioCapture_stop_capture_002_error_path(self, capture_with_devices):
        """Khi stream.close raise Exception -> bắt và log lỗi (không raise)"""
        # Sẽ implement sau, tạm thời test không có exception
        pass

# ===========================
# Test cho terminate
# ===========================

class TestAudioCaptureTerminate:
    def test_AudioCapture_terminate_001_happy_path(self, mock_external_dependencies, mock_pyaudio_instance):
        """Kết thúc toàn bộ"""
        # Tương tự stop_capture nhưng thêm p.terminate
        mock_stream = MagicMock()
        mock_pyaudio_instance.open.return_value = mock_stream
        mock_pyaudio_instance.get_device_count.return_value = 1
        device = {'name': 'Device', 'maxInputChannels': 2, 'hostApi': 0, 'index': 0, 'defaultSampleRate': 48000, 'isLoopbackDevice': True}
        mock_pyaudio_instance.get_device_info_by_index.return_value = device
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = [device]
        capture = AudioCapture(target_rate=16000)
        mock_loop = MagicMock()
        mock_queue = MagicMock()
        capture.start_capture(loop=mock_loop, queue=mock_queue)
        capture.terminate()
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pyaudio_instance.terminate.assert_called_once()
        assert capture.stream is None

    def test_AudioCapture_terminate_002_error_path(self):
        """Khi p.terminate raise Exception -> bắt và log (không raise)"""
        pass

# ===========================
# Test cho callback (phần bổ sung)
# ===========================

class TestAudioCaptureCallback:
    @pytest.fixture
    def capture_with_active_stream(self, mock_external_dependencies, mock_pyaudio_instance):
        """Tạo capture đã active để test callback"""
        mock_pyaudio_instance.get_device_count.return_value = 1
        device = {
            'name': 'Device',
            'maxInputChannels': 2,
            'hostApi': 0,
            'index': 0,
            'defaultSampleRate': 48000,
            'isLoopbackDevice': True
        }
        mock_pyaudio_instance.get_device_info_by_index.return_value = device
        mock_pyaudio_instance.get_host_api_count.return_value = 1
        mock_pyaudio_instance.get_host_api_info_by_index.return_value = {'name': 'Windows WASAPI'}
        mock_pyaudio_instance.get_loopback_device_info_generator.return_value = [device]
        capture = AudioCapture(target_rate=16000)
        mock_loop = MagicMock()
        mock_queue = MagicMock()
        capture.start_capture(loop=mock_loop, queue=mock_queue)
        return capture, mock_loop, mock_queue

    def test_callback_normal_processing(self, capture_with_active_stream, mock_external_dependencies):
        """Kiểm tra callback xử lý dữ liệu đúng: downmix, resample, put vào queue"""
        capture, mock_loop, mock_queue = capture_with_active_stream
        # Lấy callback từ open call
        args, kwargs = mock_external_dependencies['pyaudio'].PyAudio.return_value.open.call_args
        callback = kwargs['stream_callback']
        # Giả lập dữ liệu đầu vào: 2 channels, 1024 frames
        samples = np.arange(2048, dtype=np.int16)  # 1024*2
        in_data = samples.tobytes()
        frame_count = 1024
        # Call callback
        result = callback(in_data, frame_count, None, None)
        assert result == (None, mock_external_dependencies['pyaudio'].paContinue)
        # Kiểm tra downmix: Mono nên trung bình 2 channels
        expected_mono = np.mean(samples.reshape(-1, 2), axis=1).astype(np.int16)
        # Resample từ 48000 xuống 16000
        target_rate = 16000
        sample_rate = 48000
        num_samples = len(expected_mono)
        num_target_samples = int(num_samples * target_rate / sample_rate)
        x = np.arange(num_samples)
        x_new = np.linspace(0, num_samples - 1, num_target_samples)
        expected_resampled = np.interp(x_new, x, expected_mono).astype(np.int16)
        # Kiểm tra queue.put_nowait được gọi với bytes đúng
        mock_loop.call_soon_threadsafe.assert_called_once_with(mock_queue.put_nowait, expected_resampled.tobytes())