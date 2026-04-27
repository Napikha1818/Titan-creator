"""Unit tests for VideoMerger."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.errors import VideoMergeError
from src.video_merger import VideoMerger


@pytest.fixture
def merger():
    return VideoMerger()


def _make_probe_result(duration: float) -> MagicMock:
    """Helper: buat mock ffprobe result dengan durasi tertentu."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps({"format": {"duration": str(duration)}})
    return result


def _make_ffmpeg_success() -> MagicMock:
    """Helper: buat mock FFmpeg result sukses."""
    result = MagicMock()
    result.returncode = 0
    result.stderr = ""
    return result


class TestMerge:
    """Tests for VideoMerger.merge()."""

    def test_merge_success(self, merger, tmp_path):
        """Test successful merge returns output path."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(120.0)
        ffmpeg_result = _make_ffmpeg_success()
        output_probe = _make_probe_result(120.0)

        def run_side_effect(cmd, **kwargs):
            # Create output file when ffmpeg runs
            if cmd[0] == "ffmpeg":
                output_path.touch()
            return {
                0: input_probe,
                1: ffmpeg_result,
                2: output_probe,
            }[run_side_effect.call_count]

        run_side_effect.call_count = -1

        def tracked_side_effect(cmd, **kwargs):
            run_side_effect.call_count += 1
            return run_side_effect(cmd, **kwargs)

        with patch("src.video_merger.subprocess.run", side_effect=tracked_side_effect):
            result = merger.merge(video_path, audio_path, subtitle_path, output_path)

        assert result == output_path

    def test_merge_video_not_found(self, merger, tmp_path):
        """Test error when video file does not exist."""
        video_path = tmp_path / "nonexistent.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        audio_path.touch()
        subtitle_path.touch()

        with pytest.raises(VideoMergeError, match="File video tidak ditemukan"):
            merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_audio_not_found(self, merger, tmp_path):
        """Test error when audio file does not exist."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "nonexistent.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        subtitle_path.touch()

        with pytest.raises(VideoMergeError, match="File audio tidak ditemukan"):
            merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_subtitle_not_found(self, merger, tmp_path):
        """Test error when subtitle file does not exist."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "nonexistent.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()

        with pytest.raises(VideoMergeError, match="File subtitle tidak ditemukan"):
            merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_ffmpeg_failure(self, merger, tmp_path):
        """Test error when FFmpeg merge process fails."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(120.0)

        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 1
        ffmpeg_result.stderr = "Encoding failed"

        with patch(
            "src.video_merger.subprocess.run",
            side_effect=[input_probe, ffmpeg_result],
        ):
            with pytest.raises(VideoMergeError, match="Gagal menggabungkan video"):
                merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_ffmpeg_not_installed(self, merger, tmp_path):
        """Test error when FFmpeg is not installed."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        with patch(
            "src.video_merger.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with pytest.raises(VideoMergeError, match="tidak ditemukan"):
                merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_duration_mismatch(self, merger, tmp_path):
        """Test error when output duration differs from input by more than 5 seconds."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(120.0)
        ffmpeg_result = _make_ffmpeg_success()
        output_probe = _make_probe_result(126.0)  # 6 seconds difference (>5s tolerance)

        probes = iter([input_probe, output_probe])

        def tracked_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                output_path.touch()
                return ffmpeg_result
            return next(probes)

        with patch("src.video_merger.subprocess.run", side_effect=tracked_side_effect):
            with pytest.raises(VideoMergeError, match="toleransi 5 detik"):
                merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_duration_within_tolerance(self, merger, tmp_path):
        """Test success when output duration differs by less than 5 seconds."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(120.0)
        ffmpeg_result = _make_ffmpeg_success()
        output_probe = _make_probe_result(124.0)  # 4s difference, within 5s tolerance

        results = iter([input_probe, output_probe])

        def tracked_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                output_path.touch()
                return ffmpeg_result
            return next(results)

        with patch("src.video_merger.subprocess.run", side_effect=tracked_side_effect):
            result = merger.merge(video_path, audio_path, subtitle_path, output_path)

        assert result == output_path

    def test_merge_timeout(self, merger, tmp_path):
        """Test error when FFmpeg merge times out."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(120.0)

        with patch(
            "src.video_merger.subprocess.run",
            side_effect=[input_probe, subprocess.TimeoutExpired("ffmpeg", 1800)],
        ):
            with pytest.raises(VideoMergeError, match="Timeout"):
                merger.merge(video_path, audio_path, subtitle_path, output_path)

    def test_merge_output_not_created(self, merger, tmp_path):
        """Test error when FFmpeg succeeds but output file is not created."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(120.0)
        ffmpeg_result = _make_ffmpeg_success()

        with patch(
            "src.video_merger.subprocess.run",
            side_effect=[input_probe, ffmpeg_result],
        ):
            with pytest.raises(VideoMergeError, match="tidak dihasilkan"):
                merger.merge(video_path, audio_path, subtitle_path, output_path)


class TestFFmpegCommand:
    """Tests for FFmpeg command construction."""

    def test_ffmpeg_command_has_h264_aac(self, merger, tmp_path):
        """Test that FFmpeg command includes H.264 and AAC codec flags."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(60.0)
        ffmpeg_result = _make_ffmpeg_success()
        output_probe = _make_probe_result(60.0)

        probes = iter([input_probe, output_probe])

        def tracked_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                output_path.touch()
                return ffmpeg_result
            return next(probes)

        with patch("src.video_merger.subprocess.run", side_effect=tracked_side_effect) as mock_run:
            merger.merge(video_path, audio_path, subtitle_path, output_path)

        # Find the ffmpeg call
        ffmpeg_call = None
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd[0] == "ffmpeg":
                ffmpeg_call = cmd
                break

        assert ffmpeg_call is not None

        # Verify H.264 video codec
        assert "-c:v" in ffmpeg_call
        idx = ffmpeg_call.index("-c:v")
        assert ffmpeg_call[idx + 1] == "libx264"

        # Verify AAC audio codec
        assert "-c:a" in ffmpeg_call
        idx = ffmpeg_call.index("-c:a")
        assert ffmpeg_call[idx + 1] == "aac"

    def test_ffmpeg_command_has_subtitle_filter(self, merger, tmp_path):
        """Test that FFmpeg command includes subtitle burn-in filter."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(60.0)
        ffmpeg_result = _make_ffmpeg_success()
        output_probe = _make_probe_result(60.0)

        probes = iter([input_probe, output_probe])

        def tracked_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                output_path.touch()
                return ffmpeg_result
            return next(probes)

        with patch("src.video_merger.subprocess.run", side_effect=tracked_side_effect) as mock_run:
            merger.merge(video_path, audio_path, subtitle_path, output_path)

        ffmpeg_call = None
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd[0] == "ffmpeg":
                ffmpeg_call = cmd
                break

        assert ffmpeg_call is not None

        # Verify subtitle filter
        assert "-vf" in ffmpeg_call
        idx = ffmpeg_call.index("-vf")
        vf_value = ffmpeg_call[idx + 1]
        assert "subtitles=" in vf_value

    def test_ffmpeg_command_maps_video_and_audio(self, merger, tmp_path):
        """Test that FFmpeg command maps video from first input and audio from second."""
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        subtitle_path = tmp_path / "subtitle.srt"
        output_path = tmp_path / "output.mp4"

        video_path.touch()
        audio_path.touch()
        subtitle_path.touch()

        input_probe = _make_probe_result(60.0)
        ffmpeg_result = _make_ffmpeg_success()
        output_probe = _make_probe_result(60.0)

        probes = iter([input_probe, output_probe])

        def tracked_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                output_path.touch()
                return ffmpeg_result
            return next(probes)

        with patch("src.video_merger.subprocess.run", side_effect=tracked_side_effect) as mock_run:
            merger.merge(video_path, audio_path, subtitle_path, output_path)

        ffmpeg_call = None
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd[0] == "ffmpeg":
                ffmpeg_call = cmd
                break

        assert ffmpeg_call is not None

        # Verify input mapping: video from input 0, audio from input 1
        assert "-map" in ffmpeg_call
        map_indices = [i for i, v in enumerate(ffmpeg_call) if v == "-map"]
        assert len(map_indices) >= 2
        assert ffmpeg_call[map_indices[0] + 1] == "0:v:0"
        assert ffmpeg_call[map_indices[1] + 1] == "1:a:0"


class TestGetDuration:
    """Tests for VideoMerger._get_duration()."""

    def test_get_duration_success(self, merger, tmp_path):
        """Test successful duration retrieval."""
        file_path = tmp_path / "video.mp4"

        probe_result = _make_probe_result(123.45)

        with patch("src.video_merger.subprocess.run", return_value=probe_result):
            duration = merger._get_duration(file_path)

        assert duration == 123.45

    def test_get_duration_ffprobe_failure(self, merger, tmp_path):
        """Test error when ffprobe fails."""
        file_path = tmp_path / "video.mp4"

        result = MagicMock()
        result.returncode = 1
        result.stderr = "Error reading file"

        with patch("src.video_merger.subprocess.run", return_value=result):
            with pytest.raises(VideoMergeError, match="Gagal membaca durasi"):
                merger._get_duration(file_path)

    def test_get_duration_invalid_json(self, merger, tmp_path):
        """Test error when ffprobe returns invalid JSON."""
        file_path = tmp_path / "video.mp4"

        result = MagicMock()
        result.returncode = 0
        result.stdout = "not json"

        with patch("src.video_merger.subprocess.run", return_value=result):
            with pytest.raises(VideoMergeError, match="Gagal parsing durasi"):
                merger._get_duration(file_path)

    def test_get_duration_ffprobe_timeout(self, merger, tmp_path):
        """Test error when ffprobe times out."""
        file_path = tmp_path / "video.mp4"

        with patch(
            "src.video_merger.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffprobe", 30),
        ):
            with pytest.raises(VideoMergeError, match="Timeout"):
                merger._get_duration(file_path)


class TestVerifyDuration:
    """Tests for VideoMerger._verify_duration()."""

    def test_exact_match(self, merger):
        """Test no error when durations match exactly."""
        merger._verify_duration(120.0, 120.0)

    def test_within_tolerance(self, merger):
        """Test no error when difference is within 5 seconds."""
        merger._verify_duration(120.0, 124.0)
        merger._verify_duration(120.0, 116.0)

    def test_at_boundary(self, merger):
        """Test no error when difference is exactly 5 seconds."""
        merger._verify_duration(120.0, 125.0)
        merger._verify_duration(120.0, 115.0)

    def test_exceeds_tolerance(self, merger):
        """Test error when difference exceeds 5 seconds."""
        with pytest.raises(VideoMergeError, match="toleransi 5 detik"):
            merger._verify_duration(120.0, 125.5)

        with pytest.raises(VideoMergeError, match="toleransi 5 detik"):
            merger._verify_duration(120.0, 114.0)
