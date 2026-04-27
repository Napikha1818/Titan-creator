"""Unit tests for the error hierarchy."""

import pytest

from src.errors import (
    AudioExtractionError,
    ChessTranslatorError,
    DriveDownloadError,
    DriveError,
    DriveUploadError,
    PipelineError,
    SubtitleError,
    TranscriptionError,
    TranslationError,
    TTSSynthesisError,
    VideoMergeError,
)
from src.models import PipelineStage


class TestChessTranslatorError:
    """Tests for the base exception."""

    def test_is_exception(self):
        err = ChessTranslatorError("base error")
        assert isinstance(err, Exception)

    def test_message(self):
        err = ChessTranslatorError("something went wrong")
        assert str(err) == "something went wrong"


class TestDirectSubclasses:
    """Tests that each error is a direct subclass of ChessTranslatorError."""

    @pytest.mark.parametrize(
        "error_cls",
        [
            AudioExtractionError,
            TranscriptionError,
            TranslationError,
            TTSSynthesisError,
            SubtitleError,
            VideoMergeError,
            DriveError,
            PipelineError,
        ],
    )
    def test_inherits_from_base(self, error_cls):
        assert issubclass(error_cls, ChessTranslatorError)

    @pytest.mark.parametrize(
        "error_cls,msg",
        [
            (AudioExtractionError, "ffmpeg failed"),
            (TranscriptionError, "no speech detected"),
            (TranslationError, "translation api error"),
            (TTSSynthesisError, "tts failed"),
            (SubtitleError, "srt generation failed"),
            (VideoMergeError, "merge failed"),
            (DriveError, "drive error"),
        ],
    )
    def test_message_preserved(self, error_cls, msg):
        err = error_cls(msg)
        assert str(err) == msg

    @pytest.mark.parametrize(
        "error_cls",
        [
            AudioExtractionError,
            TranscriptionError,
            TranslationError,
            TTSSynthesisError,
            SubtitleError,
            VideoMergeError,
            DriveError,
        ],
    )
    def test_catchable_as_base(self, error_cls):
        with pytest.raises(ChessTranslatorError):
            raise error_cls("test")


class TestDriveErrorHierarchy:
    """Tests for DriveDownloadError and DriveUploadError inheriting from DriveError."""

    def test_download_inherits_drive_error(self):
        assert issubclass(DriveDownloadError, DriveError)

    def test_upload_inherits_drive_error(self):
        assert issubclass(DriveUploadError, DriveError)

    def test_download_inherits_base(self):
        assert issubclass(DriveDownloadError, ChessTranslatorError)

    def test_upload_inherits_base(self):
        assert issubclass(DriveUploadError, ChessTranslatorError)

    def test_download_catchable_as_drive_error(self):
        with pytest.raises(DriveError):
            raise DriveDownloadError("download failed")

    def test_upload_catchable_as_drive_error(self):
        with pytest.raises(DriveError):
            raise DriveUploadError("upload failed")

    def test_download_message(self):
        err = DriveDownloadError("file not found")
        assert str(err) == "file not found"

    def test_upload_message(self):
        err = DriveUploadError("auth failed")
        assert str(err) == "auth failed"


class TestPipelineError:
    """Tests for PipelineError with stage attribute."""

    def test_inherits_from_base(self):
        assert issubclass(PipelineError, ChessTranslatorError)

    def test_message_and_stage(self):
        err = PipelineError("extraction failed", PipelineStage.AUDIO_EXTRACTION)
        assert str(err) == "extraction failed"
        assert err.stage == PipelineStage.AUDIO_EXTRACTION

    def test_all_stages(self):
        for stage in PipelineStage:
            err = PipelineError(f"failed at {stage.value}", stage)
            assert err.stage is stage
            assert f"failed at {stage.value}" in str(err)

    def test_catchable_as_base(self):
        with pytest.raises(ChessTranslatorError):
            raise PipelineError("fail", PipelineStage.TRANSLATION)
