"""Unit tests for configuration and constants."""

import os
from pathlib import Path

import pytest

from src.config import (
    CHESS_TERM_MAPPING,
    GOOGLE_DRIVE_PATTERNS,
    SUPPORTED_VIDEO_EXTENSIONS,
    AppConfig,
    is_supported_video_format,
    load_config,
)


class TestAppConfig:
    """Tests for the AppConfig dataclass."""

    def test_required_fields(self):
        config = AppConfig(
            telegram_token="test-token",
            google_credentials_path=Path("/path/to/creds.json"),
            google_drive_folder_id="folder123",
        )
        assert config.telegram_token == "test-token"
        assert config.google_credentials_path == Path("/path/to/creds.json")
        assert config.google_drive_folder_id == "folder123"

    def test_default_values(self):
        config = AppConfig(
            telegram_token="tok",
            google_credentials_path=Path("/creds.json"),
            google_drive_folder_id="fid",
        )
        assert config.whisper_model == "small"
        assert config.whisper_device == "cpu"
        assert config.tts_voice == "en-US-Neural2-D"
        assert config.tts_engine == "google"
        assert config.max_processing_time == 1800
        assert config.telegram_file_limit == 50 * 1024 * 1024
        assert config.supported_formats == (".mp4", ".avi", ".mkv", ".mov", ".webm")
        assert config.temp_dir == Path("/tmp/chess-translator")

    def test_custom_values(self):
        config = AppConfig(
            telegram_token="tok",
            google_credentials_path=Path("/creds.json"),
            google_drive_folder_id="fid",
            whisper_model="large",
            whisper_device="cuda",
            tts_voice="en-GB-RyanNeural",
            max_processing_time=3600,
            telegram_file_limit=100 * 1024 * 1024,
            temp_dir=Path("/custom/tmp"),
        )
        assert config.whisper_model == "large"
        assert config.whisper_device == "cuda"
        assert config.tts_voice == "en-GB-RyanNeural"
        assert config.max_processing_time == 3600
        assert config.telegram_file_limit == 100 * 1024 * 1024
        assert config.temp_dir == Path("/custom/tmp")

    def test_frozen(self):
        config = AppConfig(
            telegram_token="tok",
            google_credentials_path=Path("/creds.json"),
            google_drive_folder_id="fid",
        )
        with pytest.raises(AttributeError):
            config.telegram_token = "new"  # type: ignore[misc]


class TestConstants:
    """Tests for module-level constants."""

    def test_supported_video_extensions(self):
        assert SUPPORTED_VIDEO_EXTENSIONS == {".mp4", ".avi", ".mkv", ".mov", ".webm"}

    def test_supported_video_extensions_is_set(self):
        assert isinstance(SUPPORTED_VIDEO_EXTENSIONS, set)

    def test_google_drive_patterns_count(self):
        assert len(GOOGLE_DRIVE_PATTERNS) == 2

    def test_google_drive_pattern_file_d(self):
        import re

        pattern = GOOGLE_DRIVE_PATTERNS[0]
        match = re.search(pattern, "https://drive.google.com/file/d/abc123_-XYZ/view")
        assert match is not None
        assert match.group(1) == "abc123_-XYZ"

    def test_google_drive_pattern_open_id(self):
        import re

        pattern = GOOGLE_DRIVE_PATTERNS[1]
        match = re.search(pattern, "https://drive.google.com/open?id=abc123_-XYZ")
        assert match is not None
        assert match.group(1) == "abc123_-XYZ"

    def test_chess_term_mapping_core_pieces(self):
        assert CHESS_TERM_MAPPING["kuda"] == "knight"
        assert CHESS_TERM_MAPPING["benteng"] == "rook"
        assert CHESS_TERM_MAPPING["gajah"] == "bishop"
        assert CHESS_TERM_MAPPING["menteri"] == "queen"
        assert CHESS_TERM_MAPPING["raja"] == "king"
        assert CHESS_TERM_MAPPING["bidak"] == "pawn"

    def test_chess_term_mapping_special_terms(self):
        assert CHESS_TERM_MAPPING["skak mat"] == "checkmate"
        assert CHESS_TERM_MAPPING["skak"] == "check"
        assert CHESS_TERM_MAPPING["rokade"] == "castling"
        assert CHESS_TERM_MAPPING["en passant"] == "en passant"
        assert CHESS_TERM_MAPPING["promosi"] == "promotion"
        assert CHESS_TERM_MAPPING["pat"] == "stalemate"

    def test_chess_term_mapping_has_entries(self):
        # The mapping has been expanded with many chess terms
        assert len(CHESS_TERM_MAPPING) >= 17


class TestIsSupportedVideoFormat:
    """Tests for the is_supported_video_format function."""

    def test_valid_lowercase(self):
        assert is_supported_video_format(".mp4") is True
        assert is_supported_video_format(".avi") is True
        assert is_supported_video_format(".mkv") is True
        assert is_supported_video_format(".mov") is True
        assert is_supported_video_format(".webm") is True

    def test_valid_uppercase(self):
        assert is_supported_video_format(".MP4") is True
        assert is_supported_video_format(".AVI") is True

    def test_valid_mixed_case(self):
        assert is_supported_video_format(".Mp4") is True
        assert is_supported_video_format(".MkV") is True

    def test_invalid_formats(self):
        assert is_supported_video_format(".txt") is False
        assert is_supported_video_format(".pdf") is False
        assert is_supported_video_format(".jpg") is False
        assert is_supported_video_format(".flv") is False

    def test_empty_string(self):
        assert is_supported_video_format("") is False

    def test_no_dot(self):
        assert is_supported_video_format("mp4") is False


class TestLoadConfig:
    """Tests for the load_config function."""

    def test_load_with_required_vars(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "test-token-123")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/path/to/creds.json")
        monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder-abc")

        config = load_config()

        assert config.telegram_token == "test-token-123"
        assert config.google_credentials_path == Path("/path/to/creds.json")
        assert config.google_drive_folder_id == "folder-abc"
        # Defaults
        assert config.whisper_model == "small"
        assert config.whisper_device == "cpu"
        assert config.tts_voice == "en-US-Neural2-D"
        assert config.tts_engine == "google"
        assert config.max_processing_time == 1800

    def test_load_with_all_vars(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/creds.json")
        monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "fid")
        monkeypatch.setenv("WHISPER_MODEL", "large")
        monkeypatch.setenv("WHISPER_DEVICE", "cuda")
        monkeypatch.setenv("TTS_VOICE", "en-GB-RyanNeural")
        monkeypatch.setenv("MAX_PROCESSING_TIME", "3600")
        monkeypatch.setenv("TELEGRAM_FILE_LIMIT", "104857600")
        monkeypatch.setenv("TEMP_DIR", "/custom/tmp")

        config = load_config()

        assert config.whisper_model == "large"
        assert config.whisper_device == "cuda"
        assert config.tts_voice == "en-GB-RyanNeural"
        assert config.max_processing_time == 3600
        assert config.telegram_file_limit == 104857600
        assert config.temp_dir == Path("/custom/tmp")

    def test_missing_telegram_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
        monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/creds.json")
        monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "fid")

        with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
            load_config()

    def test_missing_google_credentials_path(self, monkeypatch):
        """Google credentials are optional — should not raise."""
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
        monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "fid")

        config = load_config()
        assert config.google_credentials_path is None

    def test_missing_google_drive_folder_id(self, monkeypatch):
        """Google Drive folder ID is optional — should not raise."""
        monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
        monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/creds.json")
        monkeypatch.delenv("GOOGLE_DRIVE_FOLDER_ID", raising=False)

        config = load_config()
        assert config.google_drive_folder_id is None
