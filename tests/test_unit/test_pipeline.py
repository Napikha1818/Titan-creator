"""Unit tests for src/pipeline.py."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.errors import (
    AudioExtractionError,
    PipelineError,
    SubtitleError,
    TTSSynthesisError,
    TranscriptionError,
    TranslationError,
    VideoMergeError,
)
from src.models import PipelineStage, Segment, TranslatedSegment
from src.pipeline import (
    PipelineProcessor,
    format_error_message,
    should_use_drive,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal AppConfig without requiring env vars
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Create a test AppConfig with sensible defaults."""
    from src.config import AppConfig

    defaults = {
        "telegram_token": "test-token",
        "google_credentials_path": Path("/tmp/creds.json"),
        "google_drive_folder_id": "folder-id",
        "whisper_model": "small",
        "whisper_device": "cpu",
        "tts_voice": "en-US-AriaNeural",
        "max_processing_time": 1800,
        "telegram_file_limit": 50 * 1024 * 1024,
        "temp_dir": Path("/tmp/chess-translator"),
    }
    defaults.update(overrides)
    return AppConfig(**defaults)


# ---------------------------------------------------------------------------
# Tests for format_error_message
# ---------------------------------------------------------------------------

class TestFormatErrorMessage:
    """Tests for the format_error_message helper."""

    def test_includes_stage_name(self):
        msg = format_error_message(PipelineStage.AUDIO_EXTRACTION, "file corrupt")
        assert "AUDIO_EXTRACTION" in msg

    def test_includes_error_detail(self):
        msg = format_error_message(PipelineStage.TRANSCRIPTION, "no speech detected")
        assert "no speech detected" in msg

    def test_all_stages_included(self):
        for stage in PipelineStage:
            msg = format_error_message(stage, "some error")
            assert stage.name in msg


# ---------------------------------------------------------------------------
# Tests for should_use_drive
# ---------------------------------------------------------------------------

class TestShouldUseDrive:
    """Tests for the should_use_drive helper."""

    def test_below_limit_returns_false(self):
        assert should_use_drive(49, 50) is False

    def test_at_limit_returns_false(self):
        assert should_use_drive(50, 50) is False

    def test_above_limit_returns_true(self):
        assert should_use_drive(51, 50) is True

    def test_zero_size_returns_false(self):
        assert should_use_drive(0, 50 * 1024 * 1024) is False

    def test_telegram_limit_boundary(self):
        limit = 50 * 1024 * 1024  # 50 MB
        assert should_use_drive(limit, limit) is False
        assert should_use_drive(limit + 1, limit) is True


# ---------------------------------------------------------------------------
# Tests for PipelineProcessor
# ---------------------------------------------------------------------------

class TestPipelineProcessorInit:
    """Tests for PipelineProcessor initialization."""

    def test_init_stores_work_dir_and_callback(self, tmp_path):
        callback = AsyncMock()
        proc = PipelineProcessor(tmp_path / "work", callback)
        assert proc.work_dir == tmp_path / "work"
        assert proc.progress_callback is callback

    def test_init_with_config(self, tmp_path):
        callback = AsyncMock()
        config = _make_config()
        proc = PipelineProcessor(tmp_path / "work", callback, config=config)
        assert proc.config is config


class TestPipelineProcessorCleanup:
    """Tests for PipelineProcessor.cleanup()."""

    def test_cleanup_removes_work_dir(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "file.txt").write_text("data")

        proc = PipelineProcessor(work_dir, AsyncMock())
        proc.cleanup()

        assert not work_dir.exists()

    def test_cleanup_no_error_if_dir_missing(self, tmp_path):
        work_dir = tmp_path / "nonexistent"
        proc = PipelineProcessor(work_dir, AsyncMock())
        # Should not raise
        proc.cleanup()


class TestPipelineProcessorProcess:
    """Tests for PipelineProcessor.process() with mocked stages."""

    @pytest.fixture()
    def setup(self, tmp_path):
        """Common setup: work dir, callback, config, fake video file."""
        work_dir = tmp_path / "work"
        video_path = tmp_path / "input.mp4"
        video_path.write_text("fake video")

        callback = AsyncMock()
        config = _make_config(max_processing_time=10)

        return work_dir, video_path, callback, config

    def _make_processor(self, work_dir, callback, config):
        return PipelineProcessor(work_dir, callback, config=config)

    @pytest.mark.asyncio
    async def test_successful_pipeline_calls_all_stages(self, setup):
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]
        sample_translated = [
            TranslatedSegment(start=0.0, end=2.0, original_text="halo", translated_text="hello")
        ]

        with (
            patch("src.pipeline.AudioExtractor") as mock_ae,
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.SpeechSynthesizer") as mock_ss,
            patch("src.pipeline.SubtitleGenerator") as mock_sg,
            patch("src.pipeline.VideoMerger") as mock_vm,
            patch("src.pipeline.shutil") as mock_shutil,
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.return_value = sample_translated
            mock_ss.return_value.synthesize_segments = AsyncMock()
            mock_sg.return_value.generate.return_value = work_dir / "subtitle.srt"
            mock_vm.return_value.merge.return_value = work_dir / "output.mp4"

            proc = self._make_processor(work_dir, callback, config)
            result = await proc.process(video_path)

            # All extractors/processors were called
            mock_ae.return_value.extract.assert_called_once()
            mock_sr.return_value.transcribe.assert_called_once()
            mock_tr.return_value.translate_segments.assert_called_once()
            mock_ss.return_value.synthesize_segments.assert_called_once()
            mock_sg.return_value.generate.assert_called_once()
            mock_vm.return_value.merge.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_callback_called_for_each_stage(self, setup):
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]
        sample_translated = [
            TranslatedSegment(start=0.0, end=2.0, original_text="halo", translated_text="hello")
        ]

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.SpeechSynthesizer") as mock_ss,
            patch("src.pipeline.SubtitleGenerator"),
            patch("src.pipeline.VideoMerger"),
            patch("src.pipeline.shutil") as mock_shutil,
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.return_value = sample_translated
            mock_ss.return_value.synthesize_segments = AsyncMock()

            proc = self._make_processor(work_dir, callback, config)
            await proc.process(video_path)

            # 7 stages: 6 main + 1 vocal separation custom message
            assert callback.call_count == 7
            stage_values = [call.args[0] for call in callback.call_args_list]
            assert PipelineStage.AUDIO_EXTRACTION.value in stage_values
            assert PipelineStage.TRANSCRIPTION.value in stage_values
            assert PipelineStage.TRANSLATION.value in stage_values
            assert PipelineStage.TTS_SYNTHESIS.value in stage_values
            assert PipelineStage.SUBTITLE_GENERATION.value in stage_values
            assert PipelineStage.VIDEO_MERGE.value in stage_values

    @pytest.mark.asyncio
    async def test_audio_extraction_error_wrapped(self, setup):
        work_dir, video_path, callback, config = setup

        with patch("src.pipeline.AudioExtractor") as mock_ae:
            mock_ae.return_value.extract.side_effect = AudioExtractionError("no audio")

            proc = self._make_processor(work_dir, callback, config)
            with pytest.raises(PipelineError) as exc_info:
                await proc.process(video_path)

            assert exc_info.value.stage == PipelineStage.AUDIO_EXTRACTION
            assert "no audio" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcription_error_wrapped(self, setup):
        work_dir, video_path, callback, config = setup

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.shutil"),
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.side_effect = TranscriptionError("no speech")

            proc = self._make_processor(work_dir, callback, config)
            with pytest.raises(PipelineError) as exc_info:
                await proc.process(video_path)

            assert exc_info.value.stage == PipelineStage.TRANSCRIPTION

    @pytest.mark.asyncio
    async def test_translation_error_wrapped(self, setup):
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.shutil"),
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.side_effect = TranslationError("api down")

            proc = self._make_processor(work_dir, callback, config)
            with pytest.raises(PipelineError) as exc_info:
                await proc.process(video_path)

            assert exc_info.value.stage == PipelineStage.TRANSLATION

    @pytest.mark.asyncio
    async def test_tts_error_wrapped(self, setup):
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]
        sample_translated = [
            TranslatedSegment(start=0.0, end=2.0, original_text="halo", translated_text="hello")
        ]

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.SpeechSynthesizer") as mock_ss,
            patch("src.pipeline.shutil"),
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.return_value = sample_translated
            mock_ss.return_value.synthesize_segments = AsyncMock(
                side_effect=TTSSynthesisError("tts failed")
            )

            proc = self._make_processor(work_dir, callback, config)
            with pytest.raises(PipelineError) as exc_info:
                await proc.process(video_path)

            assert exc_info.value.stage == PipelineStage.TTS_SYNTHESIS

    @pytest.mark.asyncio
    async def test_subtitle_error_wrapped(self, setup):
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]
        sample_translated = [
            TranslatedSegment(start=0.0, end=2.0, original_text="halo", translated_text="hello")
        ]

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.SpeechSynthesizer") as mock_ss,
            patch("src.pipeline.SubtitleGenerator") as mock_sg,
            patch("src.pipeline.shutil"),
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.return_value = sample_translated
            mock_ss.return_value.synthesize_segments = AsyncMock()
            mock_sg.return_value.generate.side_effect = SubtitleError("srt failed")

            proc = self._make_processor(work_dir, callback, config)
            with pytest.raises(PipelineError) as exc_info:
                await proc.process(video_path)

            assert exc_info.value.stage == PipelineStage.SUBTITLE_GENERATION

    @pytest.mark.asyncio
    async def test_video_merge_error_wrapped(self, setup):
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]
        sample_translated = [
            TranslatedSegment(start=0.0, end=2.0, original_text="halo", translated_text="hello")
        ]

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.SpeechSynthesizer") as mock_ss,
            patch("src.pipeline.SubtitleGenerator"),
            patch("src.pipeline.VideoMerger") as mock_vm,
            patch("src.pipeline.shutil"),
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.return_value = sample_translated
            mock_ss.return_value.synthesize_segments = AsyncMock()
            mock_vm.return_value.merge.side_effect = VideoMergeError("ffmpeg crash")

            proc = self._make_processor(work_dir, callback, config)
            with pytest.raises(PipelineError) as exc_info:
                await proc.process(video_path)

            assert exc_info.value.stage == PipelineStage.VIDEO_MERGE

    @pytest.mark.asyncio
    async def test_cleanup_called_on_success(self, setup):
        """On success, cleanup is NOT called by process() — caller is responsible."""
        work_dir, video_path, callback, config = setup

        sample_segments = [Segment(start=0.0, end=2.0, text="halo")]
        sample_translated = [
            TranslatedSegment(start=0.0, end=2.0, original_text="halo", translated_text="hello")
        ]

        with (
            patch("src.pipeline.AudioExtractor"),
            patch("src.pipeline.VocalSeparator") as mock_vs,
            patch("src.pipeline.SpeechRecognizer") as mock_sr,
            patch("src.pipeline.ChessTranslator") as mock_tr,
            patch("src.pipeline.SpeechSynthesizer") as mock_ss,
            patch("src.pipeline.SubtitleGenerator"),
            patch("src.pipeline.VideoMerger"),
            patch("src.pipeline.shutil"),
        ):
            mock_vs.return_value.separate.return_value = (
                work_dir / "vocals.wav",
                work_dir / "background.wav",
            )
            mock_sr.return_value.transcribe.return_value = sample_segments
            mock_tr.return_value.translate_segments.return_value = sample_translated
            mock_ss.return_value.synthesize_segments = AsyncMock()

            proc = self._make_processor(work_dir, callback, config)
            with patch.object(proc, "cleanup") as mock_cleanup:
                await proc.process(video_path)
                # On success, process() does NOT call cleanup — caller does
                mock_cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_called_on_failure(self, setup):
        work_dir, video_path, callback, config = setup

        with patch("src.pipeline.AudioExtractor") as mock_ae:
            mock_ae.return_value.extract.side_effect = AudioExtractionError("fail")

            proc = self._make_processor(work_dir, callback, config)
            with patch.object(proc, "cleanup") as mock_cleanup:
                with pytest.raises(PipelineError):
                    await proc.process(video_path)
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_raises_pipeline_error(self, setup):
        work_dir, video_path, callback, config = setup
        # Use a very short timeout
        config = _make_config(max_processing_time=0)

        async def slow_extract(*args, **kwargs):
            await asyncio.sleep(5)

        with patch("src.pipeline.AudioExtractor") as mock_ae:
            mock_ae.return_value.extract = MagicMock(side_effect=lambda *a, **k: None)

            # Patch _run_pipeline to be slow
            proc = self._make_processor(work_dir, callback, config)
            original_run = proc._run_pipeline

            async def slow_pipeline(video_path):
                await asyncio.sleep(5)
                return await original_run(video_path)

            with patch.object(proc, "_run_pipeline", side_effect=slow_pipeline):
                with pytest.raises(PipelineError) as exc_info:
                    await proc.process(video_path)

                assert "batas waktu" in str(exc_info.value)
