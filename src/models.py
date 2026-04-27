"""Core data models for Chess Video Translator."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    """Satu unit teks hasil speech-to-text dengan timestamp."""

    start: float  # Timestamp mulai dalam detik
    end: float  # Timestamp selesai dalam detik
    text: str  # Teks transkripsi bahasa Indonesia

    @property
    def duration(self) -> float:
        """Durasi segmen dalam detik."""
        return self.end - self.start


@dataclass(frozen=True)
class TranslatedSegment:
    """Segmen yang sudah diterjemahkan ke bahasa Inggris."""

    start: float  # Timestamp mulai (sama dengan Segment asli)
    end: float  # Timestamp selesai (sama dengan Segment asli)
    original_text: str  # Teks asli bahasa Indonesia
    translated_text: str  # Teks terjemahan bahasa Inggris

    @property
    def duration(self) -> float:
        """Durasi segmen dalam detik."""
        return self.end - self.start


class PipelineStage(Enum):
    """Tahapan pipeline pemrosesan."""

    AUDIO_EXTRACTION = "Mengekstrak audio..."
    TRANSCRIPTION = "Transkripsi audio..."
    TRANSLATION = "Menerjemahkan teks..."
    TTS_SYNTHESIS = "Sintesis suara bahasa Inggris..."
    SUBTITLE_GENERATION = "Membuat subtitle..."
    VIDEO_MERGE = "Menggabungkan video final..."
    UPLOADING = "Mengupload hasil..."


@dataclass
class PipelineResult:
    """Hasil dari pipeline pemrosesan."""

    success: bool
    output_path: Path | None = None
    error_message: str | None = None
    error_stage: PipelineStage | None = None


@dataclass
class JobContext:
    """Konteks untuk satu job pemrosesan video."""

    chat_id: int
    video_path: Path
    work_dir: Path
    audio_path: Path | None = None
    segments: list[Segment] = field(default_factory=list)
    translated_segments: list[TranslatedSegment] = field(default_factory=list)
    tts_audio_path: Path | None = None
    subtitle_path: Path | None = None
    output_path: Path | None = None
