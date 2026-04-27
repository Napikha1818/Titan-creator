"""Subtitle Generator for creating SRT files from translated segments."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.errors import SubtitleError
from src.models import TranslatedSegment

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """Generator file subtitle SRT."""

    MAX_LINE_LENGTH: int = 42

    def generate(
        self, segments: list[TranslatedSegment], output_path: Path
    ) -> Path:
        """Buat file SRT dari segmen terjemahan.

        Memecah baris yang melebihi MAX_LINE_LENGTH (Req 6.1, 6.2, 6.3).

        Args:
            segments: List of translated segments to write as subtitles.
            output_path: Path for the output SRT file.

        Returns:
            Path to the generated SRT file.

        Raises:
            SubtitleError: If subtitle generation fails.
        """
        if not segments:
            raise SubtitleError("No segments to generate subtitles from")

        try:
            srt_content = self.format_srt(segments)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(srt_content, encoding="utf-8")
            logger.info("Generated SRT file: %s (%d segments)", output_path, len(segments))
            return output_path
        except SubtitleError:
            raise
        except Exception as e:
            raise SubtitleError(f"Failed to generate subtitle file: {e}") from e

    def _wrap_text(self, text: str) -> str:
        """Pecah teks menjadi baris-baris dengan panjang maksimal MAX_LINE_LENGTH.

        Breaks at word boundaries so no line exceeds 42 characters (Req 6.3).

        Args:
            text: Input text to wrap.

        Returns:
            Text with newlines inserted at word boundaries.
        """
        if len(text) <= self.MAX_LINE_LENGTH:
            return text

        words = text.split()
        lines: list[str] = []
        current_line = ""

        for word in words:
            if not current_line:
                # Start a new line with this word
                current_line = word
            elif len(current_line) + 1 + len(word) <= self.MAX_LINE_LENGTH:
                # Word fits on the current line
                current_line += " " + word
            else:
                # Word doesn't fit, start a new line
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return "\n".join(lines)

    def format_srt(self, segments: list[TranslatedSegment]) -> str:
        """Format segmen menjadi string SRT.

        SRT format per entry:
        - Index number (1-based)
        - Timestamp line: HH:MM:SS,mmm --> HH:MM:SS,mmm
        - Text (possibly multi-line via _wrap_text)
        - Blank line separator

        Args:
            segments: List of translated segments.

        Returns:
            Complete SRT-formatted string.
        """
        entries: list[str] = []

        for i, segment in enumerate(segments, start=1):
            start_ts = _format_timestamp(segment.start)
            end_ts = _format_timestamp(segment.end)
            wrapped_text = self._wrap_text(segment.translated_text)

            entry = f"{i}\n{start_ts} --> {end_ts}\n{wrapped_text}"
            entries.append(entry)

        return "\n\n".join(entries) + "\n"

    @staticmethod
    def parse_srt(srt_content: str) -> list[TranslatedSegment]:
        """Parse string SRT kembali menjadi daftar segmen.

        Since SRT doesn't contain original_text, uses translated_text
        as both original_text and translated_text (Req 6.4).

        Args:
            srt_content: SRT-formatted string to parse.

        Returns:
            List of TranslatedSegment objects parsed from the SRT content.

        Raises:
            SubtitleError: If the SRT content cannot be parsed.
        """
        if not srt_content or not srt_content.strip():
            raise SubtitleError("Empty SRT content")

        segments: list[TranslatedSegment] = []
        # Split into blocks separated by blank lines
        blocks = re.split(r"\n\n+", srt_content.strip())

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")
            if len(lines) < 3:
                raise SubtitleError(
                    f"Invalid SRT block (expected at least 3 lines): {block!r}"
                )

            # Line 0: index number (skip, we don't need it)
            # Line 1: timestamp line
            timestamp_line = lines[1]
            match = re.match(
                r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
                timestamp_line,
            )
            if not match:
                raise SubtitleError(
                    f"Invalid SRT timestamp line: {timestamp_line!r}"
                )

            start = _parse_timestamp(match.group(1))
            end = _parse_timestamp(match.group(2))

            # Lines 2+: subtitle text (may be multi-line from _wrap_text)
            text = "\n".join(lines[2:])

            # Rejoin wrapped lines into a single line for the segment text
            text_single_line = " ".join(text.split("\n"))

            segments.append(
                TranslatedSegment(
                    start=start,
                    end=end,
                    original_text=text_single_line,
                    translated_text=text_single_line,
                )
            )

        return segments


def _format_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm.

    Args:
        seconds: Time in seconds (non-negative).

    Returns:
        Formatted timestamp string.
    """
    if seconds < 0:
        seconds = 0.0

    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    remaining = total_ms % 3_600_000
    minutes = remaining // 60_000
    remaining = remaining % 60_000
    secs = remaining // 1000
    ms = remaining % 1000

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _parse_timestamp(ts: str) -> float:
    """Parse SRT timestamp string to seconds.

    Args:
        ts: Timestamp in format HH:MM:SS,mmm.

    Returns:
        Time in seconds.

    Raises:
        SubtitleError: If the timestamp format is invalid.
    """
    match = re.match(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", ts)
    if not match:
        raise SubtitleError(f"Invalid timestamp format: {ts!r}")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    secs = int(match.group(3))
    ms = int(match.group(4))

    return hours * 3600 + minutes * 60 + secs + ms / 1000.0
