"""Unit tests for SpeechRecognizer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.errors import TranscriptionError
from src.models import Segment
from src.speech_recognizer import (
    MAX_SEGMENT_DURATION,
    MIN_SEGMENT_DURATION,
    SpeechRecognizer,
)


class TestSpeechRecognizerInit:
    """Tests for SpeechRecognizer initialization."""

    def test_default_parameters(self):
        recognizer = SpeechRecognizer()
        assert recognizer.model_size == "small"
        assert recognizer.device == "cpu"

    def test_custom_parameters(self):
        recognizer = SpeechRecognizer(model_size="large", device="cuda")
        assert recognizer.model_size == "large"
        assert recognizer.device == "cuda"

    @patch("src.speech_recognizer.WhisperModel")
    def test_lazy_model_loading(self, mock_whisper_cls):
        recognizer = SpeechRecognizer()
        # Model not loaded yet
        assert recognizer._model is None
        # Access model property triggers loading
        _ = recognizer.model
        mock_whisper_cls.assert_called_once_with("small", device="cpu")


class TestTranscribe:
    """Tests for the transcribe method."""

    def test_file_not_found_raises_error(self):
        recognizer = SpeechRecognizer()
        with pytest.raises(TranscriptionError, match="File audio tidak ditemukan"):
            recognizer.transcribe(Path("/nonexistent/audio.wav"))

    @patch("src.speech_recognizer.WhisperModel")
    def test_no_speech_detected_raises_error(self, mock_whisper_cls, tmp_path):
        audio_file = tmp_path / "empty.wav"
        audio_file.touch()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())
        mock_whisper_cls.return_value = mock_model

        recognizer = SpeechRecognizer()
        with pytest.raises(TranscriptionError, match="Tidak ada ucapan"):
            recognizer.transcribe(audio_file)

    @patch("src.speech_recognizer.WhisperModel")
    def test_empty_text_segments_filtered(self, mock_whisper_cls, tmp_path):
        """Segments with empty text after stripping should be filtered out."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        seg1 = MagicMock(start=0.0, end=2.0, text="  ")
        seg2 = MagicMock(start=2.0, end=4.0, text="")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg1, seg2]), MagicMock())
        mock_whisper_cls.return_value = mock_model

        recognizer = SpeechRecognizer()
        with pytest.raises(TranscriptionError, match="Tidak ada ucapan"):
            recognizer.transcribe(audio_file)

    @patch("src.speech_recognizer.WhisperModel")
    def test_successful_transcription(self, mock_whisper_cls, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        seg1 = MagicMock(start=0.0, end=3.0, text="Halo dunia")
        seg2 = MagicMock(start=3.0, end=6.0, text="Ini adalah tes")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([seg1, seg2]), MagicMock())
        mock_whisper_cls.return_value = mock_model

        recognizer = SpeechRecognizer()
        result = recognizer.transcribe(audio_file)

        assert len(result) == 2
        assert result[0].text == "Halo dunia"
        assert result[0].start == 0.0
        assert result[0].end == 3.0
        assert result[1].text == "Ini adalah tes"

    @patch("src.speech_recognizer.WhisperModel")
    def test_transcription_exception_wrapped(self, mock_whisper_cls, tmp_path):
        """Exceptions from faster-whisper should be wrapped in TranscriptionError."""
        audio_file = tmp_path / "audio.wav"
        audio_file.touch()

        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("Model error")
        mock_whisper_cls.return_value = mock_model

        recognizer = SpeechRecognizer()
        with pytest.raises(TranscriptionError, match="Gagal melakukan transkripsi"):
            recognizer.transcribe(audio_file)


class TestSplitLongSegments:
    """Tests for _split_long_segments."""

    def setup_method(self):
        self.recognizer = SpeechRecognizer()

    def test_segment_within_limit_unchanged(self):
        segments = [Segment(start=0.0, end=10.0, text="Normal segment")]
        result = self.recognizer._split_long_segments(segments)
        assert len(result) == 1
        assert result[0] == segments[0]

    def test_segment_at_limit_unchanged(self):
        segments = [Segment(start=0.0, end=15.0, text="Exactly at limit")]
        result = self.recognizer._split_long_segments(segments)
        assert len(result) == 1
        assert result[0] == segments[0]

    def test_long_segment_split(self):
        # 20 second segment with multiple words
        segments = [
            Segment(start=0.0, end=20.0, text="kata satu dua tiga empat lima")
        ]
        result = self.recognizer._split_long_segments(segments)

        assert len(result) >= 2
        # All parts should be within the limit
        for seg in result:
            assert seg.duration <= MAX_SEGMENT_DURATION
        # Timestamps should be contiguous
        assert result[0].start == 0.0
        assert result[-1].end == 20.0
        # All words should be preserved
        all_text = " ".join(s.text for s in result)
        assert all_text == "kata satu dua tiga empat lima"

    def test_very_long_segment_split_into_multiple(self):
        # 50 second segment
        words = " ".join(f"word{i}" for i in range(20))
        segments = [Segment(start=0.0, end=50.0, text=words)]
        result = self.recognizer._split_long_segments(segments)

        assert len(result) >= 4  # 50/15 = ~3.3, so at least 4 parts
        for seg in result:
            assert seg.duration <= MAX_SEGMENT_DURATION

    def test_long_segment_single_word(self):
        """A long segment with a single word should still be split by time."""
        segments = [Segment(start=0.0, end=20.0, text="word")]
        result = self.recognizer._split_long_segments(segments)

        assert len(result) >= 2
        for seg in result:
            assert seg.duration <= MAX_SEGMENT_DURATION
            assert seg.text == "word"


class TestMergeShortSegments:
    """Tests for _merge_short_segments."""

    def setup_method(self):
        self.recognizer = SpeechRecognizer()

    def test_normal_segments_unchanged(self):
        segments = [
            Segment(start=0.0, end=2.0, text="First"),
            Segment(start=2.0, end=4.0, text="Second"),
        ]
        result = self.recognizer._merge_short_segments(segments)
        assert len(result) == 2
        assert result[0].text == "First"
        assert result[1].text == "Second"

    def test_short_segment_merged_with_next(self):
        segments = [
            Segment(start=0.0, end=0.3, text="Hi"),
            Segment(start=0.3, end=3.0, text="there friend"),
        ]
        result = self.recognizer._merge_short_segments(segments)

        assert len(result) == 1
        assert result[0].start == 0.0
        assert result[0].end == 3.0
        assert result[0].text == "Hi there friend"

    def test_short_segment_at_end_merged_with_previous(self):
        segments = [
            Segment(start=0.0, end=3.0, text="Hello world"),
            Segment(start=3.0, end=3.2, text="ya"),
        ]
        result = self.recognizer._merge_short_segments(segments)

        assert len(result) == 1
        assert result[0].start == 0.0
        assert result[0].end == 3.2
        assert result[0].text == "Hello world ya"

    def test_multiple_consecutive_short_segments(self):
        segments = [
            Segment(start=0.0, end=0.2, text="A"),
            Segment(start=0.2, end=0.3, text="B"),
            Segment(start=0.3, end=3.0, text="C long enough"),
        ]
        result = self.recognizer._merge_short_segments(segments)

        # All short segments should be merged
        for seg in result:
            assert seg.duration >= MIN_SEGMENT_DURATION or len(result) == 1

    def test_single_short_segment_kept(self):
        """A single short segment should be kept as-is."""
        segments = [Segment(start=0.0, end=0.3, text="Hi")]
        result = self.recognizer._merge_short_segments(segments)
        assert len(result) == 1
        assert result[0].text == "Hi"

    def test_empty_list(self):
        result = self.recognizer._merge_short_segments([])
        assert result == []


class TestNormalizeSegments:
    """Tests for _normalize_segments (combined split + merge)."""

    def setup_method(self):
        self.recognizer = SpeechRecognizer()

    def test_mixed_segments_normalized(self):
        """Test with a mix of long, short, and normal segments."""
        segments = [
            Segment(start=0.0, end=0.3, text="Hi"),
            Segment(start=0.3, end=5.0, text="Normal segment here"),
            Segment(
                start=5.0,
                end=25.0,
                text="This is a very long segment that needs splitting into parts",
            ),
        ]
        result = self.recognizer._normalize_segments(segments)

        # No segment should exceed MAX_SEGMENT_DURATION
        for seg in result:
            assert seg.duration <= MAX_SEGMENT_DURATION

        # Short segments should have been merged (unless only one remains)
        short_count = sum(
            1 for s in result if s.duration < MIN_SEGMENT_DURATION
        )
        # At most one short segment allowed (the edge case of a single remaining)
        assert short_count <= 1 or len(result) == 1

    def test_all_normal_segments_unchanged(self):
        segments = [
            Segment(start=0.0, end=3.0, text="First"),
            Segment(start=3.0, end=6.0, text="Second"),
            Segment(start=6.0, end=9.0, text="Third"),
        ]
        result = self.recognizer._normalize_segments(segments)
        assert len(result) == 3
        assert result == segments
