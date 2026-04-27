"""Unit tests for Speech Synthesizer module."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.errors import TTSSynthesisError
from src.models import TranslatedSegment
from src.speech_synthesizer import (
    SpeechSynthesizer,
    _DEFAULT_CHARS_PER_SECOND,
    _DURATION_TOLERANCE,
    _MAX_RATE_PERCENT,
    _MIN_RATE_PERCENT,
    calculate_segment_gap,
)


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------
class TestSpeechSynthesizerInit:
    """Tests for SpeechSynthesizer.__init__."""

    def test_default_voice(self) -> None:
        synth = SpeechSynthesizer()
        assert synth.voice == "en-US-Neural2-D"

    def test_custom_voice(self) -> None:
        synth = SpeechSynthesizer(voice="en-US-WaveNet-D")
        assert synth.voice == "en-US-WaveNet-D"

    def test_engine_defaults_to_edge_without_api_key(self) -> None:
        synth = SpeechSynthesizer(api_key=None)
        assert synth.engine == "edge"

    def test_engine_google_with_api_key(self) -> None:
        synth = SpeechSynthesizer(api_key="test-key")
        assert synth.engine == "google"


# ---------------------------------------------------------------------------
# _calculate_rate tests
# ---------------------------------------------------------------------------
class TestCalculateRate:
    """Tests for SpeechSynthesizer._calculate_rate."""

    RATE_PATTERN = re.compile(r"^[+-]\d+%$")

    def test_format_matches_pattern(self) -> None:
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("Hello world", 2.0)
        assert self.RATE_PATTERN.match(rate)

    def test_short_text_long_duration_negative_rate(self) -> None:
        """Short text with long target → slow down → negative rate."""
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("Hi", 10.0)
        assert rate.startswith("-")

    def test_long_text_short_duration_positive_rate(self) -> None:
        """Long text with short target → speed up → positive rate."""
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate(
            "This is a very long sentence that should require speeding up", 0.5
        )
        assert rate.startswith("+")

    def test_zero_duration_returns_plus_zero(self) -> None:
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("Some text", 0.0)
        assert rate == "+0%"

    def test_negative_duration_returns_plus_zero(self) -> None:
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("Some text", -1.0)
        assert rate == "+0%"

    def test_empty_text_returns_plus_zero(self) -> None:
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("", 2.0)
        assert rate == "+0%"

    def test_rate_clamped_to_max(self) -> None:
        """Very long text with very short duration should be clamped."""
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("a" * 1000, 0.1)
        # Extract numeric value
        numeric = int(rate.replace("%", "").replace("+", ""))
        assert numeric <= _MAX_RATE_PERCENT

    def test_rate_clamped_to_min(self) -> None:
        """Very short text with very long duration should be clamped."""
        synth = SpeechSynthesizer()
        rate = synth._calculate_rate("a", 1000.0)
        numeric = int(rate.replace("%", ""))
        assert numeric >= _MIN_RATE_PERCENT

    def test_various_inputs_all_valid_format(self) -> None:
        synth = SpeechSynthesizer()
        test_cases = [
            ("Hello", 1.0),
            ("A short phrase", 3.0),
            ("x" * 100, 5.0),
            ("Test", 0.5),
            ("Medium length text here", 2.0),
        ]
        for text, dur in test_cases:
            rate = synth._calculate_rate(text, dur)
            assert self.RATE_PATTERN.match(rate), f"Invalid rate {rate!r} for ({text!r}, {dur})"


# ---------------------------------------------------------------------------
# calculate_segment_gap tests
# ---------------------------------------------------------------------------
class TestCalculateSegmentGap:
    """Tests for calculate_segment_gap function."""

    def test_normal_gap(self) -> None:
        seg1 = TranslatedSegment(start=0.0, end=2.0, original_text="a", translated_text="b")
        seg2 = TranslatedSegment(start=3.0, end=5.0, original_text="c", translated_text="d")
        assert calculate_segment_gap(seg1, seg2) == pytest.approx(1.0)

    def test_adjacent_segments_zero_gap(self) -> None:
        seg1 = TranslatedSegment(start=0.0, end=2.0, original_text="a", translated_text="b")
        seg2 = TranslatedSegment(start=2.0, end=4.0, original_text="c", translated_text="d")
        assert calculate_segment_gap(seg1, seg2) == pytest.approx(0.0)

    def test_overlapping_segments_clamped_to_zero(self) -> None:
        seg1 = TranslatedSegment(start=0.0, end=3.0, original_text="a", translated_text="b")
        seg2 = TranslatedSegment(start=2.0, end=4.0, original_text="c", translated_text="d")
        assert calculate_segment_gap(seg1, seg2) == pytest.approx(0.0)

    def test_large_gap(self) -> None:
        seg1 = TranslatedSegment(start=0.0, end=1.0, original_text="a", translated_text="b")
        seg2 = TranslatedSegment(start=10.0, end=12.0, original_text="c", translated_text="d")
        assert calculate_segment_gap(seg1, seg2) == pytest.approx(9.0)

    def test_fractional_gap(self) -> None:
        seg1 = TranslatedSegment(start=1.5, end=2.7, original_text="a", translated_text="b")
        seg2 = TranslatedSegment(start=3.2, end=4.0, original_text="c", translated_text="d")
        assert calculate_segment_gap(seg1, seg2) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# synthesize_single tests (mocked edge-tts and FFmpeg)
# ---------------------------------------------------------------------------
class TestSynthesizeSingle:
    """Tests for SpeechSynthesizer.synthesize_single with mocked externals."""

    @pytest.mark.asyncio
    async def test_short_audio_gets_padded(self, tmp_path: Path) -> None:
        """Audio shorter than target should be padded via _fit_to_duration."""
        synth = SpeechSynthesizer()
        output = tmp_path / "out.wav"

        mock_communicate = AsyncMock()
        mock_communicate.save = AsyncMock()

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        with (
            patch.dict("sys.modules", {"edge_tts": mock_edge_tts}),
            patch.object(synth, "_convert_to_wav"),
            patch.object(synth, "_get_audio_duration", return_value=1.0),
            patch.object(synth, "_fit_to_duration") as mock_fit,
        ):
            await synth.synthesize_single("Hello world", 3.0, output)
            # _fit_to_duration is always called as the final step
            mock_fit.assert_called_once()

    @pytest.mark.asyncio
    async def test_within_tolerance_uses_raw(self, tmp_path: Path) -> None:
        """Audio within tolerance should use raw audio (no re-generation)."""
        synth = SpeechSynthesizer()
        output = tmp_path / "out.wav"

        mock_communicate = AsyncMock()
        mock_communicate.save = AsyncMock()

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        with (
            patch.dict("sys.modules", {"edge_tts": mock_edge_tts}),
            patch.object(synth, "_convert_to_wav"),
            patch.object(synth, "_get_audio_duration", return_value=3.1),
            patch.object(synth, "_fit_to_duration") as mock_fit,
            patch.object(synth, "_time_stretch") as mock_stretch,
        ):
            await synth.synthesize_single("Hello world", 3.0, output)
            # Should NOT time-stretch since within tolerance
            mock_stretch.assert_not_called()
            # But should still fit to exact duration
            mock_fit.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_audio_triggers_resynth(self, tmp_path: Path) -> None:
        """Audio moderately longer than target triggers two-pass re-synthesis."""
        synth = SpeechSynthesizer()
        output = tmp_path / "out.wav"

        mock_communicate = AsyncMock()
        mock_communicate.save = AsyncMock()

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        with (
            patch.dict("sys.modules", {"edge_tts": mock_edge_tts}),
            patch.object(synth, "_convert_to_wav"),
            # First call returns 4.0 (ratio 1.33), second returns 3.0 (after rate increase)
            patch.object(synth, "_get_audio_duration", side_effect=[4.0, 3.0]),
            patch.object(synth, "_fit_to_duration") as mock_fit,
        ):
            await synth.synthesize_single("Hello world", 3.0, output)
            # edge-tts Communicate should be called twice (natural + tuned)
            assert mock_edge_tts.Communicate.call_count == 2
            mock_fit.assert_called_once()

    @pytest.mark.asyncio
    async def test_edge_tts_failure_raises_tts_error(self, tmp_path: Path) -> None:
        """If edge-tts fails, TTSSynthesisError should be raised."""
        synth = SpeechSynthesizer()
        output = tmp_path / "out.wav"

        mock_communicate = AsyncMock()
        mock_communicate.save = AsyncMock(side_effect=Exception("TTS service down"))

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        with patch.dict("sys.modules", {"edge_tts": mock_edge_tts}):
            with pytest.raises(TTSSynthesisError, match="Failed to synthesize text"):
                await synth.synthesize_single("Hello", 2.0, output)


# ---------------------------------------------------------------------------
# synthesize_segments tests (mocked)
# ---------------------------------------------------------------------------
class TestSynthesizeSegments:
    """Tests for SpeechSynthesizer.synthesize_segments with mocked externals."""

    @pytest.mark.asyncio
    async def test_empty_segments_raises_error(self, tmp_path: Path) -> None:
        synth = SpeechSynthesizer()
        output = tmp_path / "out.wav"

        with pytest.raises(TTSSynthesisError, match="No segments to synthesize"):
            await synth.synthesize_segments([], output)

    @pytest.mark.asyncio
    async def test_calls_synthesize_single_for_each_segment(self, tmp_path: Path) -> None:
        synth = SpeechSynthesizer()
        output = tmp_path / "out.wav"

        segments = [
            TranslatedSegment(start=0.0, end=2.0, original_text="a", translated_text="Hello"),
            TranslatedSegment(start=3.0, end=5.0, original_text="b", translated_text="World"),
        ]

        with (
            patch.object(synth, "synthesize_single", new_callable=AsyncMock) as mock_single,
            patch.object(synth, "_build_absolute_track") as mock_build,
        ):
            mock_single.return_value = tmp_path / "seg.wav"

            await synth.synthesize_segments(segments, output)

            assert mock_single.call_count == 2
            mock_build.assert_called_once()


# ---------------------------------------------------------------------------
# _build_absolute_track tests
# ---------------------------------------------------------------------------
class TestBuildAbsoluteTrack:
    """Tests for the absolute-position track builder."""

    def test_empty_files_raises_error(self) -> None:
        synth = SpeechSynthesizer()
        with pytest.raises(TTSSynthesisError, match="No segment files"):
            synth._build_absolute_track([], [], Path("out.wav"))

    def test_segments_placed_at_correct_positions(self, tmp_path: Path) -> None:
        """Verify segments are placed at their absolute start timestamps."""
        import numpy as np

        synth = SpeechSynthesizer()

        # Create two small WAV files with known content
        seg1_path = tmp_path / "seg1.wav"
        seg2_path = tmp_path / "seg2.wav"

        # 0.5 seconds of ones at 24kHz
        ones_half_sec = np.ones(12000, dtype=np.float32) * 0.5
        synth._write_wav(ones_half_sec, seg1_path)
        synth._write_wav(ones_half_sec, seg2_path)

        segments = [
            TranslatedSegment(start=0.0, end=0.5, original_text="a", translated_text="b"),
            TranslatedSegment(start=2.0, end=2.5, original_text="c", translated_text="d"),
        ]

        output_path = tmp_path / "output.wav"
        synth._build_absolute_track([seg1_path, seg2_path], segments, output_path)

        # Read back and verify
        result = synth._read_wav_as_float(output_path)

        # First segment at t=0.0: samples 0-11999 should be ~0.5
        assert np.mean(np.abs(result[0:12000])) > 0.3

        # Gap at t=0.5-2.0: samples 12000-47999 should be ~0 (silence)
        assert np.mean(np.abs(result[12000:48000])) < 0.01

        # Second segment at t=2.0: samples 48000-59999 should be ~0.5
        assert np.mean(np.abs(result[48000:60000])) > 0.3


# ---------------------------------------------------------------------------
# FFmpeg helper tests (static methods)
# ---------------------------------------------------------------------------
class TestFFmpegHelpers:
    """Tests for FFmpeg-based static helper methods."""

    def test_convert_to_wav_success(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            SpeechSynthesizer._convert_to_wav(Path("in.mp3"), Path("out.wav"))
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "ffmpeg" in cmd
            assert "-ac" in cmd
            assert "1" in cmd

    def test_convert_to_wav_failure(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            with pytest.raises(TTSSynthesisError, match="WAV conversion failed"):
                SpeechSynthesizer._convert_to_wav(Path("in.mp3"), Path("out.wav"))

    def test_get_audio_duration_success(self) -> None:
        import json

        mock_output = json.dumps({"format": {"duration": "3.14"}})
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
            duration = SpeechSynthesizer._get_audio_duration(Path("test.wav"))
            assert duration == pytest.approx(3.14)

    def test_get_audio_duration_failure(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            with pytest.raises(TTSSynthesisError, match="Failed to get audio duration"):
                SpeechSynthesizer._get_audio_duration(Path("test.wav"))

    def test_get_audio_duration_bad_json(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="not json")
            with pytest.raises(TTSSynthesisError, match="Failed to parse audio duration"):
                SpeechSynthesizer._get_audio_duration(Path("test.wav"))

    def test_trim_audio_success(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            SpeechSynthesizer._trim_audio(Path("in.wav"), Path("out.wav"), 3.0)
            cmd = mock_run.call_args[0][0]
            assert "-t" in cmd
            assert "3.0" in cmd

    def test_trim_audio_failure(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            with pytest.raises(TTSSynthesisError, match="Audio trimming failed"):
                SpeechSynthesizer._trim_audio(Path("in.wav"), Path("out.wav"), 3.0)

    def test_pad_audio_success(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            SpeechSynthesizer._pad_audio(Path("in.wav"), Path("out.wav"), 5.0)
            cmd = mock_run.call_args[0][0]
            assert "apad=whole_dur=5.0" in " ".join(cmd)

    def test_pad_audio_failure(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            with pytest.raises(TTSSynthesisError, match="Audio padding failed"):
                SpeechSynthesizer._pad_audio(Path("in.wav"), Path("out.wav"), 5.0)

    def test_copy_audio_success(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            SpeechSynthesizer._copy_audio(Path("in.wav"), Path("out.wav"))
            cmd = mock_run.call_args[0][0]
            assert "-c" in cmd
            assert "copy" in cmd

    def test_copy_audio_failure(self) -> None:
        with patch("src.speech_synthesizer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            with pytest.raises(TTSSynthesisError, match="Audio copy failed"):
                SpeechSynthesizer._copy_audio(Path("in.wav"), Path("out.wav"))


# ---------------------------------------------------------------------------
# WAV I/O helper tests
# ---------------------------------------------------------------------------
class TestWavIO:
    """Tests for numpy-based WAV read/write helpers."""

    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        """Write a WAV, read it back, verify content is preserved."""
        import numpy as np

        original = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        wav_path = tmp_path / "test.wav"

        SpeechSynthesizer._write_wav(original, wav_path)
        result = SpeechSynthesizer._read_wav_as_float(wav_path)

        # Allow small quantization error from float32 → int16 → float32
        assert len(result) == len(original)
        np.testing.assert_allclose(result, original, atol=1e-4)
