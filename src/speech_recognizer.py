"""Speech recognition using faster-whisper for Indonesian audio."""

from __future__ import annotations

import logging
from pathlib import Path

from faster_whisper import WhisperModel

from src.errors import TranscriptionError
from src.models import Segment

logger = logging.getLogger(__name__)

# Normalization thresholds
MAX_SEGMENT_DURATION = 15.0  # seconds
MIN_SEGMENT_DURATION = 0.5  # seconds


class SpeechRecognizer:
    """Transkripsi audio menggunakan faster-whisper."""

    def __init__(
        self, model_size: str = "small", device: str = "cpu"
    ) -> None:
        """Inisialisasi SpeechRecognizer.

        Args:
            model_size: Ukuran model Whisper (default: "small").
            device: Device untuk inferensi (default: "cpu").
        """
        self.model_size = model_size
        self.device = device
        self._model: WhisperModel | None = None

    @property
    def model(self) -> WhisperModel:
        """Lazy-load Whisper model."""
        if self._model is None:
            self._model = WhisperModel(
                self.model_size, device=self.device
            )
        return self._model

    def transcribe(self, audio_path: Path) -> list[Segment]:
        """Transkripsi audio dan kembalikan daftar Segment.

        Args:
            audio_path: Path ke file audio WAV.

        Returns:
            Daftar Segment hasil transkripsi dengan durasi ternormalisasi.

        Raises:
            TranscriptionError: Jika tidak ada ucapan terdeteksi atau
                proses transkripsi gagal.
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise TranscriptionError(
                f"File audio tidak ditemukan: {audio_path}"
            )

        try:
            segments_iter, info = self.model.transcribe(
                str(audio_path),
                language="id",
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
            )
        except Exception as e:
            raise TranscriptionError(
                f"Gagal melakukan transkripsi: {e}"
            ) from e

        raw_segments: list[Segment] = []
        for seg in segments_iter:
            text = seg.text.strip()
            if text and seg.words:
                # Use word-level timestamps to split at natural pauses
                word_segments = self._split_by_word_pauses(seg)
                raw_segments.extend(word_segments)
            elif text:
                raw_segments.append(
                    Segment(start=seg.start, end=seg.end, text=text)
                )

        if not raw_segments:
            raise TranscriptionError(
                "Tidak ada ucapan yang terdeteksi dalam audio."
            )

        logger.info(
            "Transkripsi selesai: %d segmen mentah ditemukan", len(raw_segments)
        )

        # Log all segments for debugging chess term recognition
        for i, seg in enumerate(raw_segments):
            logger.info("  Segment %d [%.1f-%.1f]: %s", i, seg.start, seg.end, seg.text)

        normalized = self._normalize_segments(raw_segments)

        logger.info(
            "Normalisasi selesai: %d segmen setelah normalisasi",
            len(normalized),
        )

        return normalized

    def _normalize_segments(self, segments: list[Segment]) -> list[Segment]:
        """Normalisasi durasi segmen: split yang terlalu panjang, merge yang terlalu pendek.

        Args:
            segments: Daftar Segment mentah dari transkripsi.

        Returns:
            Daftar Segment dengan durasi antara MIN_SEGMENT_DURATION dan
            MAX_SEGMENT_DURATION.
        """
        # Step 1: Split segments that are too long
        split_segments = self._split_long_segments(segments)

        # Step 2: Merge segments that are too short
        merged_segments = self._merge_short_segments(split_segments)

        return merged_segments

    def _split_long_segments(
        self, segments: list[Segment]
    ) -> list[Segment]:
        """Split segmen yang durasinya melebihi MAX_SEGMENT_DURATION.

        Segmen dipecah menjadi bagian-bagian yang sama rata berdasarkan
        jumlah kata, dengan timestamp yang didistribusikan proporsional.

        Args:
            segments: Daftar Segment input.

        Returns:
            Daftar Segment di mana tidak ada segmen dengan durasi > MAX_SEGMENT_DURATION.
        """
        result: list[Segment] = []

        for seg in segments:
            if seg.duration <= MAX_SEGMENT_DURATION:
                result.append(seg)
                continue

            # Calculate how many parts we need
            num_parts = max(2, int(seg.duration / MAX_SEGMENT_DURATION) + 1)
            # Ensure each part is within the limit
            while seg.duration / num_parts > MAX_SEGMENT_DURATION:
                num_parts += 1

            words = seg.text.split()
            if len(words) <= 1:
                # Can't split by words, split by time only
                part_duration = seg.duration / num_parts
                for i in range(num_parts):
                    part_start = seg.start + i * part_duration
                    part_end = seg.start + (i + 1) * part_duration
                    result.append(
                        Segment(
                            start=part_start,
                            end=part_end,
                            text=seg.text,
                        )
                    )
                continue

            # Distribute words across parts as evenly as possible
            words_per_part = len(words) / num_parts
            part_duration = seg.duration / num_parts

            for i in range(num_parts):
                word_start_idx = int(i * words_per_part)
                word_end_idx = int((i + 1) * words_per_part)
                # Ensure last part gets remaining words
                if i == num_parts - 1:
                    word_end_idx = len(words)

                part_text = " ".join(words[word_start_idx:word_end_idx])
                if not part_text:
                    # Skip empty parts (shouldn't happen normally)
                    continue

                part_start = seg.start + i * part_duration
                part_end = seg.start + (i + 1) * part_duration

                result.append(
                    Segment(
                        start=part_start,
                        end=part_end,
                        text=part_text,
                    )
                )

        return result

    def _merge_short_segments(
        self, segments: list[Segment]
    ) -> list[Segment]:
        """Merge segmen yang durasinya kurang dari MIN_SEGMENT_DURATION dengan segmen terdekat.

        Segmen pendek digabungkan dengan segmen berikutnya jika ada,
        atau dengan segmen sebelumnya jika tidak ada segmen berikutnya.

        Args:
            segments: Daftar Segment input.

        Returns:
            Daftar Segment di mana tidak ada segmen dengan durasi < MIN_SEGMENT_DURATION
            (kecuali jika hanya ada satu segmen yang memang pendek).
        """
        if len(segments) <= 1:
            return list(segments)

        result: list[Segment] = []

        i = 0
        while i < len(segments):
            current = segments[i]

            if current.duration >= MIN_SEGMENT_DURATION:
                result.append(current)
                i += 1
                continue

            # Current segment is too short — merge with adjacent
            if i + 1 < len(segments):
                # Merge with next segment
                next_seg = segments[i + 1]
                merged = Segment(
                    start=current.start,
                    end=next_seg.end,
                    text=f"{current.text} {next_seg.text}",
                )
                # Replace next segment with merged and skip current
                segments = (
                    segments[:i] + [merged] + segments[i + 2 :]
                )
                # Don't increment i — re-check the merged segment
            elif result:
                # No next segment, merge with previous (last in result)
                prev = result.pop()
                merged = Segment(
                    start=prev.start,
                    end=current.end,
                    text=f"{prev.text} {current.text}",
                )
                result.append(merged)
                i += 1
            else:
                # Only segment and it's short — keep it as is
                result.append(current)
                i += 1

        return result

    @staticmethod
    def _split_by_word_pauses(seg) -> list[Segment]:
        """Split a Whisper segment at natural pauses using word-level timestamps.

        Detects gaps > PAUSE_THRESHOLD between consecutive words and splits
        the segment at those points. This preserves the speaker's natural
        rhythm and pauses in the TTS output.

        Args:
            seg: A faster-whisper segment object with .words attribute.

        Returns:
            List of Segment objects split at natural pause points.
        """
        PAUSE_THRESHOLD = 0.5  # seconds — split if gap between words > this

        words = seg.words
        if not words:
            text = seg.text.strip()
            if text:
                return [Segment(start=seg.start, end=seg.end, text=text)]
            return []

        result: list[Segment] = []
        current_words: list[str] = []
        current_start: float = words[0].start

        for i, word in enumerate(words):
            current_words.append(word.word.strip())

            # Check if there's a pause after this word
            if i < len(words) - 1:
                gap = words[i + 1].start - word.end
                if gap >= PAUSE_THRESHOLD and current_words:
                    # Split here — natural pause detected
                    text = " ".join(w for w in current_words if w)
                    if text:
                        result.append(Segment(
                            start=current_start,
                            end=word.end,
                            text=text,
                        ))
                    current_words = []
                    current_start = words[i + 1].start

        # Don't forget the last group of words
        if current_words:
            text = " ".join(w for w in current_words if w)
            if text:
                result.append(Segment(
                    start=current_start,
                    end=words[-1].end,
                    text=text,
                ))

        return result if result else [Segment(start=seg.start, end=seg.end, text=seg.text.strip())]
