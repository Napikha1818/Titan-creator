"""Pipeline Processor - orchestrates the full video translation pipeline."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Awaitable, Callable

from src.audio_extractor import AudioExtractor
from src.config import AppConfig, load_config
from src.errors import (
    AudioExtractionError,
    PipelineError,
    SubtitleError,
    TTSSynthesisError,
    TranscriptionError,
    TranslationError,
    VideoMergeError,
)
from src.models import PipelineStage
from src.speech_recognizer import SpeechRecognizer
from src.speech_synthesizer import SpeechSynthesizer
from src.subtitle_generator import SubtitleGenerator
from src.translator import ChessTranslator
from src.video_merger import VideoMerger
from src.vocal_separator import VocalSeparator

logger = logging.getLogger(__name__)

# Mapping from exception types to the pipeline stage where they occur
_STAGE_ERROR_MAP: dict[type[Exception], PipelineStage] = {
    AudioExtractionError: PipelineStage.AUDIO_EXTRACTION,
    TranscriptionError: PipelineStage.TRANSCRIPTION,
    TranslationError: PipelineStage.TRANSLATION,
    TTSSynthesisError: PipelineStage.TTS_SYNTHESIS,
    SubtitleError: PipelineStage.SUBTITLE_GENERATION,
    VideoMergeError: PipelineStage.VIDEO_MERGE,
}


def format_error_message(stage: PipelineStage, error_message: str) -> str:
    """Format a user-facing error message that includes the pipeline stage name.

    Args:
        stage: The pipeline stage where the error occurred.
        error_message: The underlying error detail message.

    Returns:
        Formatted error string containing the stage name.
    """
    return (
        f"❌ Pemrosesan gagal pada tahap: {stage.name}\n"
        f"Detail: {error_message}\n\n"
        f"Silakan coba lagi atau hubungi admin jika masalah berlanjut."
    )


def should_use_drive(file_size: int, limit: int) -> bool:
    """Determine whether a file should be uploaded to Google Drive.

    Returns True if file_size exceeds the limit, meaning the file is too
    large for direct Telegram delivery and should use Google Drive instead.

    Args:
        file_size: Size of the file in bytes.
        limit: Maximum size in bytes for direct delivery.

    Returns:
        True if file_size > limit (use Drive), False otherwise (direct send).
    """
    return file_size > limit


class PipelineProcessor:
    """Orkestrator pipeline pemrosesan video.

    Runs all processing stages sequentially:
    1. Audio extraction (video → WAV)
    2. Speech recognition (WAV → Segments)
    3. Translation (Segments ID → TranslatedSegments EN)
    4. TTS synthesis (TranslatedSegments → audio EN)
    5. Subtitle generation (TranslatedSegments → SRT)
    6. Video merge (video + audio EN + SRT → output MP4)
    """

    def __init__(
        self,
        work_dir: Path,
        progress_callback: Callable[[str], Awaitable[None]],
        config: AppConfig | None = None,
    ) -> None:
        """Initialize the pipeline processor.

        Args:
            work_dir: Working directory for intermediate files.
            progress_callback: Async callable that receives a PipelineStage
                value string to report progress at each stage.
            config: Optional AppConfig. If None, loads from environment.
        """
        self.work_dir = Path(work_dir)
        self.progress_callback = progress_callback
        self._config = config

    @property
    def config(self) -> AppConfig:
        """Lazy-load configuration."""
        if self._config is None:
            self._config = load_config()
        return self._config

    async def process(self, video_path: Path) -> Path:
        """Run the full pipeline and return the path to the output video.

        NOTE: Caller is responsible for cleaning up the work_dir after
        using the output file. This avoids the output being deleted
        before it can be sent to the user.
        """
        try:
            return await asyncio.wait_for(
                self._run_pipeline(video_path),
                timeout=self.config.max_processing_time,
            )
        except asyncio.TimeoutError:
            self.cleanup()
            raise PipelineError(
                f"Pemrosesan melebihi batas waktu {self.config.max_processing_time} detik.",
                stage=PipelineStage.VIDEO_MERGE,
            )
        except Exception:
            self.cleanup()
            raise

    async def _run_pipeline(self, video_path: Path) -> Path:
        """Execute all pipeline stages sequentially.

        Args:
            video_path: Path to the input video file.

        Returns:
            Path to the final output video.

        Raises:
            PipelineError: If any stage fails.
        """
        video_path = Path(video_path)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Define output paths for intermediate files
        audio_path = self.work_dir / "audio.wav"
        vocals_path = self.work_dir / "vocals.wav"
        background_path = self.work_dir / "background.wav"
        tts_audio_path = self.work_dir / "audio_en.wav"
        subtitle_path = self.work_dir / "subtitle.srt"
        output_path = self.work_dir / "output.mp4"

        # Stage 1: Audio Extraction
        await self._report_progress(PipelineStage.AUDIO_EXTRACTION)
        try:
            extractor = AudioExtractor()
            extractor.extract(video_path, audio_path)
        except AudioExtractionError as e:
            raise PipelineError(str(e), stage=PipelineStage.AUDIO_EXTRACTION) from e
        except Exception as e:
            raise PipelineError(str(e), stage=PipelineStage.AUDIO_EXTRACTION) from e

        # Stage 1.5: Vocal Separation (split vocals from SFX/background)
        await self._report_progress_custom("Memisahkan suara dari efek suara...")
        try:
            separator = VocalSeparator()
            demucs_dir = self.work_dir / "demucs_out"
            sep_vocals, sep_background = separator.separate(audio_path, demucs_dir)
            # Copy to standard paths

            shutil.copy2(sep_vocals, vocals_path)
            shutil.copy2(sep_background, background_path)
        except AudioExtractionError as e:
            logger.warning("Vocal separation failed, falling back to full audio: %s", e)
            # Fallback: use full audio for STT, no background SFX
            shutil.copy2(audio_path, vocals_path)
            background_path = None
        except Exception as e:
            logger.warning("Vocal separation failed, falling back to full audio: %s", e)

            shutil.copy2(audio_path, vocals_path)
            background_path = None

        # Stage 2: Speech Recognition (Transcription) — use vocals only
        await self._report_progress(PipelineStage.TRANSCRIPTION)
        try:
            recognizer = SpeechRecognizer(
                model_size=self.config.whisper_model,
                device=self.config.whisper_device,
            )
            segments = recognizer.transcribe(vocals_path)
        except TranscriptionError as e:
            raise PipelineError(str(e), stage=PipelineStage.TRANSCRIPTION) from e
        except Exception as e:
            raise PipelineError(str(e), stage=PipelineStage.TRANSCRIPTION) from e

        # Stage 3: Translation
        await self._report_progress(PipelineStage.TRANSLATION)
        try:
            translator = ChessTranslator(api_key=self.config.google_translate_api_key)
            translated_segments = translator.translate_segments(segments)
        except TranslationError as e:
            raise PipelineError(str(e), stage=PipelineStage.TRANSLATION) from e
        except Exception as e:
            raise PipelineError(str(e), stage=PipelineStage.TRANSLATION) from e

        # Stage 4: TTS Synthesis
        await self._report_progress(PipelineStage.TTS_SYNTHESIS)
        try:
            synthesizer = SpeechSynthesizer(
                voice=self.config.tts_voice,
                api_key=self.config.google_tts_api_key,
                engine=self.config.tts_engine,
            )
            await synthesizer.synthesize_segments(translated_segments, tts_audio_path)
        except TTSSynthesisError as e:
            raise PipelineError(str(e), stage=PipelineStage.TTS_SYNTHESIS) from e
        except Exception as e:
            raise PipelineError(str(e), stage=PipelineStage.TTS_SYNTHESIS) from e

        # Stage 5: Subtitle Generation
        await self._report_progress(PipelineStage.SUBTITLE_GENERATION)
        try:
            subtitle_gen = SubtitleGenerator()
            subtitle_gen.generate(translated_segments, subtitle_path)
        except SubtitleError as e:
            raise PipelineError(str(e), stage=PipelineStage.SUBTITLE_GENERATION) from e
        except Exception as e:
            raise PipelineError(str(e), stage=PipelineStage.SUBTITLE_GENERATION) from e

        # Stage 6: Video Merge (mix TTS + background SFX)
        await self._report_progress(PipelineStage.VIDEO_MERGE)
        try:
            merger = VideoMerger()
            merger.merge(video_path, tts_audio_path, subtitle_path, output_path,
                        background_audio_path=background_path)
        except VideoMergeError as e:
            raise PipelineError(str(e), stage=PipelineStage.VIDEO_MERGE) from e
        except Exception as e:
            raise PipelineError(str(e), stage=PipelineStage.VIDEO_MERGE) from e

        logger.info("Pipeline completed successfully. Output: %s", output_path)
        return output_path

    async def _report_progress(self, stage: PipelineStage) -> None:
        """Report progress to the callback."""
        try:
            await self.progress_callback(stage.value)
        except Exception:
            logger.warning("Failed to report progress for stage: %s", stage.name)

    async def _report_progress_custom(self, message: str) -> None:
        """Report custom progress message."""
        try:
            await self.progress_callback(message)
        except Exception:
            logger.warning("Failed to report progress: %s", message)

    def cleanup(self) -> None:
        """Delete the work directory and all its contents.

        Called in the finally block of process() to ensure temporary
        files are always cleaned up, whether the pipeline succeeds or fails.
        """
        try:
            if self.work_dir.exists():
                shutil.rmtree(self.work_dir)
                logger.info("Cleaned up work directory: %s", self.work_dir)
        except Exception:
            logger.warning(
                "Failed to clean up work directory: %s", self.work_dir, exc_info=True
            )
