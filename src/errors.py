"""Error hierarchy for Chess Video Translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import PipelineStage


class ChessTranslatorError(Exception):
    """Base exception untuk Chess Video Translator."""

    pass


class AudioExtractionError(ChessTranslatorError):
    """Error saat ekstraksi audio."""

    pass


class TranscriptionError(ChessTranslatorError):
    """Error saat transkripsi speech-to-text."""

    pass


class TranslationError(ChessTranslatorError):
    """Error saat terjemahan teks."""

    pass


class TTSSynthesisError(ChessTranslatorError):
    """Error saat sintesis text-to-speech."""

    pass


class SubtitleError(ChessTranslatorError):
    """Error saat pembuatan subtitle."""

    pass


class VideoMergeError(ChessTranslatorError):
    """Error saat penggabungan video."""

    pass


class DriveError(ChessTranslatorError):
    """Base error untuk Google Drive operations."""

    pass


class DriveDownloadError(DriveError):
    """Error saat download dari Google Drive."""

    pass


class DriveUploadError(DriveError):
    """Error saat upload ke Google Drive."""

    pass


class PipelineError(ChessTranslatorError):
    """Error pada level pipeline."""

    def __init__(self, message: str, stage: PipelineStage) -> None:
        super().__init__(message)
        self.stage = stage
