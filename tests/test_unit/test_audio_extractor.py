"""Unit tests for AudioExtractor."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from src.audio_extractor import AudioExtractor
from src.errors import AudioExtractionError


@pytest.fixture
def extractor():
    return AudioExtractor()


class TestExtract:
    """Tests for AudioExtractor.extract()."""

    def test_extract_success(self, extractor, tmp_path):
        """Test successful audio extraction returns output path."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = "audio\n"

        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 0

        with patch("src.audio_extractor.subprocess.run", side_effect=[probe_result, ffmpeg_result]) as mock_run:
            result = extractor.extract(video_path, output_path)

        assert result == output_path

        # Verify ffprobe call
        probe_call = mock_run.call_args_list[0]
        assert "ffprobe" in probe_call[0][0]

        # Verify ffmpeg call
        ffmpeg_call = mock_run.call_args_list[1]
        cmd = ffmpeg_call[0][0]
        assert "ffmpeg" in cmd
        assert "-vn" in cmd
        assert "-ar" in cmd
        assert "16000" in cmd
        assert "-ac" in cmd
        assert "1" in cmd
        assert "-acodec" in cmd
        assert "pcm_s16le" in cmd

    def test_extract_file_not_found(self, extractor, tmp_path):
        """Test error when video file does not exist."""
        video_path = tmp_path / "nonexistent.mp4"
        output_path = tmp_path / "audio.wav"

        with pytest.raises(AudioExtractionError, match="tidak ditemukan"):
            extractor.extract(video_path, output_path)

    def test_extract_no_audio_track(self, extractor, tmp_path):
        """Test error when video has no audio track."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = ""

        with patch("src.audio_extractor.subprocess.run", return_value=probe_result):
            with pytest.raises(AudioExtractionError, match="tidak mengandung audio"):
                extractor.extract(video_path, output_path)

    def test_extract_corrupt_file(self, extractor, tmp_path):
        """Test error when video file is corrupt."""
        video_path = tmp_path / "corrupt.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        probe_result = MagicMock()
        probe_result.returncode = 1
        probe_result.stdout = ""
        probe_result.stderr = "Invalid data found"

        with patch("src.audio_extractor.subprocess.run", return_value=probe_result):
            with pytest.raises(AudioExtractionError, match="corrupt"):
                extractor.extract(video_path, output_path)

    def test_extract_ffmpeg_failure(self, extractor, tmp_path):
        """Test error when FFmpeg extraction process fails."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = "audio\n"

        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 1
        ffmpeg_result.stderr = "Conversion failed"

        with patch("src.audio_extractor.subprocess.run", side_effect=[probe_result, ffmpeg_result]):
            with pytest.raises(AudioExtractionError, match="Gagal mengekstrak"):
                extractor.extract(video_path, output_path)

    def test_extract_ffmpeg_not_installed(self, extractor, tmp_path):
        """Test error when FFmpeg is not installed."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        with patch("src.audio_extractor.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(AudioExtractionError, match="tidak ditemukan"):
                extractor.extract(video_path, output_path)

    def test_extract_ffprobe_timeout(self, extractor, tmp_path):
        """Test error when ffprobe times out."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        with patch("src.audio_extractor.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 30)):
            with pytest.raises(AudioExtractionError, match="Timeout"):
                extractor.extract(video_path, output_path)

    def test_extract_ffmpeg_timeout(self, extractor, tmp_path):
        """Test error when FFmpeg extraction times out."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = "audio\n"

        with patch(
            "src.audio_extractor.subprocess.run",
            side_effect=[probe_result, subprocess.TimeoutExpired("ffmpeg", 300)],
        ):
            with pytest.raises(AudioExtractionError, match="Timeout"):
                extractor.extract(video_path, output_path)


class TestCheckAudioStream:
    """Tests for AudioExtractor._check_audio_stream()."""

    def test_audio_stream_present(self, extractor, tmp_path):
        """Test no error when audio stream is present."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = "audio\n"

        with patch("src.audio_extractor.subprocess.run", return_value=probe_result):
            # Should not raise
            extractor._check_audio_stream(video_path)

    def test_no_audio_stream(self, extractor, tmp_path):
        """Test error when no audio stream found."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = ""

        with patch("src.audio_extractor.subprocess.run", return_value=probe_result):
            with pytest.raises(AudioExtractionError, match="tidak mengandung audio"):
                extractor._check_audio_stream(video_path)


class TestFFmpegCommand:
    """Tests for FFmpeg command construction."""

    def test_ffmpeg_command_flags(self, extractor, tmp_path):
        """Test that FFmpeg command includes correct flags for WAV mono 16kHz."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"

        probe_result = MagicMock()
        probe_result.returncode = 0
        probe_result.stdout = "audio\n"

        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 0

        with patch("src.audio_extractor.subprocess.run", side_effect=[probe_result, ffmpeg_result]) as mock_run:
            extractor.extract(video_path, output_path)

        ffmpeg_call = mock_run.call_args_list[1]
        cmd = ffmpeg_call[0][0]

        # Verify WAV mono 16kHz flags
        assert cmd[0] == "ffmpeg"
        assert "-i" in cmd
        assert str(video_path) in cmd
        assert "-vn" in cmd  # No video
        assert "-acodec" in cmd
        idx = cmd.index("-acodec")
        assert cmd[idx + 1] == "pcm_s16le"  # PCM 16-bit
        assert "-ar" in cmd
        idx = cmd.index("-ar")
        assert cmd[idx + 1] == "16000"  # 16kHz sample rate
        assert "-ac" in cmd
        idx = cmd.index("-ac")
        assert cmd[idx + 1] == "1"  # Mono
        assert "-y" in cmd  # Overwrite output
        assert str(output_path) == cmd[-1]
