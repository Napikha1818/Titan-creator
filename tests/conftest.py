"""Shared test fixtures for Chess Video Translator.

Provides reusable fixtures for sample data models, test configuration,
and temporary directory management across all test modules.

Requirements: 3.2, 4.2
"""

from pathlib import Path

import pytest

from src.config import AppConfig
from src.models import Segment, TranslatedSegment


# ---------------------------------------------------------------------------
# Sample Segment fixtures (Requirement 3.2)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_segment() -> Segment:
    """A single sample Segment with typical values."""
    return Segment(start=1.0, end=4.0, text="kuda ke e4")


@pytest.fixture
def sample_segments() -> list[Segment]:
    """A list of sample Segments covering various durations and chess terms."""
    return [
        Segment(start=0.0, end=3.0, text="pembukaan dengan kuda ke f3"),
        Segment(start=3.5, end=7.0, text="benteng pindah ke d1"),
        Segment(start=8.0, end=12.5, text="gajah mengancam raja lawan"),
        Segment(start=13.0, end=15.0, text="skak mat"),
    ]


# ---------------------------------------------------------------------------
# Sample TranslatedSegment fixtures (Requirement 4.2)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_translated_segment() -> TranslatedSegment:
    """A single sample TranslatedSegment with typical values."""
    return TranslatedSegment(
        start=1.0,
        end=4.0,
        original_text="kuda ke e4",
        translated_text="knight to e4",
    )


@pytest.fixture
def sample_translated_segments() -> list[TranslatedSegment]:
    """A list of sample TranslatedSegments matching sample_segments."""
    return [
        TranslatedSegment(
            start=0.0,
            end=3.0,
            original_text="pembukaan dengan kuda ke f3",
            translated_text="opening with knight to f3",
        ),
        TranslatedSegment(
            start=3.5,
            end=7.0,
            original_text="benteng pindah ke d1",
            translated_text="rook moves to d1",
        ),
        TranslatedSegment(
            start=8.0,
            end=12.5,
            original_text="gajah mengancam raja lawan",
            translated_text="bishop threatens opponent king",
        ),
        TranslatedSegment(
            start=13.0,
            end=15.0,
            original_text="skak mat",
            translated_text="checkmate",
        ),
    ]


# ---------------------------------------------------------------------------
# AppConfig fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def test_config(tmp_path: Path) -> AppConfig:
    """An AppConfig instance with sensible test defaults.

    Uses tmp_path for temp_dir and a fake credentials path so tests
    never touch real credentials or the real filesystem outside tmp.
    """
    creds_path = tmp_path / "fake_credentials.json"
    creds_path.write_text("{}")
    return AppConfig(
        telegram_token="test-token-fixture",
        google_credentials_path=creds_path,
        google_drive_folder_id="test-folder-id",
        whisper_model="small",
        whisper_device="cpu",
        tts_voice="en-US-AriaNeural",
        max_processing_time=1800,
        telegram_file_limit=50 * 1024 * 1024,
        temp_dir=tmp_path / "chess-translator-test",
    )


# ---------------------------------------------------------------------------
# Temporary directory management fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """A pre-created temporary working directory for pipeline tests."""
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """A pre-created temporary output directory."""
    d = tmp_path / "output"
    d.mkdir()
    return d


@pytest.fixture
def fake_video(tmp_path: Path) -> Path:
    """A fake video file (empty) for tests that need a video path."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"\x00" * 1024)
    return video


@pytest.fixture
def fake_audio(tmp_path: Path) -> Path:
    """A fake audio file (empty) for tests that need an audio path."""
    audio = tmp_path / "test_audio.wav"
    audio.write_bytes(b"\x00" * 512)
    return audio


@pytest.fixture
def fake_subtitle(tmp_path: Path) -> Path:
    """A fake subtitle file with minimal SRT content."""
    srt = tmp_path / "test_subtitle.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nknight to e4\n\n",
        encoding="utf-8",
    )
    return srt
