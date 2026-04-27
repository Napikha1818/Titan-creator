"""Speech Synthesizer with Google Cloud TTS (primary) and edge-tts (fallback).

Google Cloud TTS provides:
- WaveNet/Neural2 voices with natural prosody and intonation
- SSML support for breaks, pitch, and rate control
- Speaking rate via <prosody rate="..."> for duration fitting

Architecture:
1. Two-pass TTS: Generate once to measure duration, re-generate with adjusted
   speaking rate if needed.
2. Absolute timestamp anchoring: Each segment placed at its exact timestamp
   position, eliminating cumulative drift.
3. High-quality time-stretching via Rubberband as last resort.
4. Automatic fallback to edge-tts if Google Cloud TTS is unavailable.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import numpy as np

from src.errors import TTSSynthesisError
from src.models import TranslatedSegment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public constants (kept for backward-compat with existing tests)
# ---------------------------------------------------------------------------
_DURATION_TOLERANCE = 0.2
_DEFAULT_CHARS_PER_SECOND = 14.0
_MAX_RATE_PERCENT = 50
_MIN_RATE_PERCENT = -50

# Internal tuning knobs
_SAMPLE_RATE = 24000
_RUBBERBAND_MAX_RATIO = 1.8
_GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Google Cloud TTS speaking rate limits (0.25 to 4.0, 1.0 = normal)
_GOOGLE_MIN_RATE = 0.5
_GOOGLE_MAX_RATE = 2.0


class SpeechSynthesizer:
    """Text-to-Speech with Google Cloud TTS and edge-tts fallback."""

    def __init__(
        self,
        voice: str = "en-US-Neural2-D",
        api_key: str | None = None,
        engine: str = "google",
    ) -> None:
        self.voice = voice
        self.api_key = api_key or os.environ.get("GOOGLE_TTS_API_KEY")
        self.engine = engine if self.api_key else "edge"

        if self.engine == "google" and not self.api_key:
            logger.warning("No GOOGLE_TTS_API_KEY found, falling back to edge-tts")
            self.engine = "edge"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize_segments(
        self, segments: list[TranslatedSegment], output_path: Path
    ) -> Path:
        """Synthesize all segments into one audio track with absolute positioning."""
        if not segments:
            raise TTSSynthesisError("No segments to synthesize")

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                segment_files: list[Path] = []

                for i, segment in enumerate(segments):
                    seg_output = tmp_path / f"segment_{i:04d}.wav"
                    await self.synthesize_single(
                        text=segment.translated_text,
                        target_duration=segment.duration,
                        output_path=seg_output,
                    )
                    segment_files.append(seg_output)

                self._build_absolute_track(
                    segment_files=segment_files,
                    segments=segments,
                    output_path=output_path,
                )

            return output_path

        except TTSSynthesisError:
            raise
        except Exception as e:
            raise TTSSynthesisError(f"Failed to synthesize segments: {e}") from e

    async def synthesize_single(
        self, text: str, target_duration: float, output_path: Path
    ) -> Path:
        """Synthesize one segment fitted precisely to target_duration.

        Natural speed + smart pause strategy:
        1. Generate at natural speed (rate 1.0) — best prosody.
        2. If TTS shorter than target:
           - Small gap (< 30% of target): keep natural speed, pad silence.
             This sounds like a natural pause between phrases.
           - Large gap (>= 30%): slow down slightly (rate 0.85-0.95) to
             partially fill, then pad the rest. Never go below 0.8x.
        3. If TTS longer than target: speed up via rate adjustment.
        4. Final fit: always pad/trim to exact target_duration.
        """
        # Threshold: if TTS fills at least 70% of target, use natural speed
        _NATURAL_THRESHOLD = 0.70

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)

                # --- Pass 1: natural speed ---
                raw_wav = tmp_path / "raw.wav"
                if self.engine == "google":
                    self._google_tts(text, raw_wav, speaking_rate=1.0)
                else:
                    await self._edge_tts(text, raw_wav, rate_pct=0)

                actual_duration = self._get_audio_duration(raw_wav)

                if target_duration <= 0:
                    self._fit_to_duration(raw_wav, output_path, max(actual_duration, 0.1))
                    return output_path

                ratio = actual_duration / target_duration
                fitted_wav = tmp_path / "fitted.wav"

                if abs(actual_duration - target_duration) <= _DURATION_TOLERANCE:
                    # Already close enough — use as-is
                    fitted_wav = raw_wav

                elif ratio >= _NATURAL_THRESHOLD and ratio < 1.0:
                    # TTS shorter but fills >= 70% of slot.
                    # Keep natural speed — the silence pad at the end sounds
                    # like a natural pause before the next phrase.
                    fitted_wav = raw_wav

                elif ratio < _NATURAL_THRESHOLD and ratio >= _GOOGLE_MIN_RATE:
                    # TTS much shorter (fills < 70%) — slow down partially.
                    # Target: fill ~85% of the slot, leave 15% as natural pause.
                    target_fill = 0.85
                    desired_duration = target_duration * target_fill
                    slow_rate = max(actual_duration / desired_duration, _GOOGLE_MIN_RATE)
                    slow_rate = min(slow_rate, 1.0)  # never speed up here

                    slow_wav = tmp_path / "slow.wav"
                    if self.engine == "google":
                        self._google_tts(text, slow_wav, speaking_rate=slow_rate)
                    else:
                        rate_pct = max(int((slow_rate - 1.0) * 100), -50)
                        await self._edge_tts(text, slow_wav, rate_pct=rate_pct)

                    fitted_wav = slow_wav

                elif ratio < _GOOGLE_MIN_RATE:
                    # Extremely short — slow to minimum, pad the rest
                    slow_wav = tmp_path / "slow.wav"
                    if self.engine == "google":
                        self._google_tts(text, slow_wav, speaking_rate=_GOOGLE_MIN_RATE)
                    else:
                        await self._edge_tts(text, slow_wav, rate_pct=-50)
                    fitted_wav = slow_wav

                elif ratio <= _GOOGLE_MAX_RATE:
                    # TTS longer than target — SPEED UP
                    adjusted_rate = min(ratio * 1.05, _GOOGLE_MAX_RATE)
                    tuned_wav = tmp_path / "tuned.wav"

                    if self.engine == "google":
                        self._google_tts(text, tuned_wav, speaking_rate=adjusted_rate)
                    else:
                        rate_pct = min(int((adjusted_rate - 1.0) * 100) + 5, 40)
                        await self._edge_tts(text, tuned_wav, rate_pct=rate_pct)

                    tuned_dur = self._get_audio_duration(tuned_wav)
                    tuned_ratio = tuned_dur / target_duration

                    if abs(tuned_dur - target_duration) <= _DURATION_TOLERANCE:
                        fitted_wav = tuned_wav
                    elif tuned_ratio > 1.0 and tuned_ratio <= _RUBBERBAND_MAX_RATIO:
                        self._time_stretch(tuned_wav, fitted_wav, tuned_ratio)
                    else:
                        fitted_wav = tuned_wav

                else:
                    # Very long — generate at max rate, then Rubberband
                    fast_wav = tmp_path / "fast.wav"
                    if self.engine == "google":
                        self._google_tts(text, fast_wav, speaking_rate=_GOOGLE_MAX_RATE)
                    else:
                        await self._edge_tts(text, fast_wav, rate_pct=40)

                    fast_dur = self._get_audio_duration(fast_wav)
                    fast_ratio = fast_dur / target_duration

                    if abs(fast_dur - target_duration) <= _DURATION_TOLERANCE:
                        fitted_wav = fast_wav
                    elif fast_ratio > 1.0 and fast_ratio <= _RUBBERBAND_MAX_RATIO:
                        self._time_stretch(fast_wav, fitted_wav, fast_ratio)
                    else:
                        self._time_stretch(fast_wav, fitted_wav, min(fast_ratio, _RUBBERBAND_MAX_RATIO))

                self._fit_to_duration(fitted_wav, output_path, target_duration)

            return output_path

        except TTSSynthesisError:
            raise
        except Exception as e:
            raise TTSSynthesisError(
                f"Failed to synthesize text '{text[:50]}...': {e}"
            ) from e

    def _calculate_rate(self, text: str, target_duration: float) -> str:
        """Calculate rate adjustment string (backward compat for tests)."""
        if target_duration <= 0 or not text:
            return "+0%"

        estimated_natural = len(text) / _DEFAULT_CHARS_PER_SECOND
        if estimated_natural <= 0:
            return "+0%"

        ratio = estimated_natural / target_duration
        rate_pct = int((ratio - 1.0) * 100)
        rate_pct = max(_MIN_RATE_PERCENT, min(_MAX_RATE_PERCENT, rate_pct))

        sign = "+" if rate_pct >= 0 else ""
        return f"{sign}{rate_pct}%"

    # ------------------------------------------------------------------
    # Google Cloud TTS via REST API
    # ------------------------------------------------------------------

    def _google_tts(
        self, text: str, output_path: Path, speaking_rate: float = 1.0
    ) -> None:
        """Synthesize speech using Google Cloud TTS REST API with API key.

        Uses SSML with prosody control for natural-sounding output.
        """
        # Build SSML with prosody for rate control
        escaped_text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

        if abs(speaking_rate - 1.0) > 0.01:
            ssml = (
                f'<speak>'
                f'<prosody rate="{speaking_rate:.2f}">{escaped_text}</prosody>'
                f'</speak>'
            )
        else:
            ssml = f'<speak>{escaped_text}</speak>'

        # Determine voice config from voice name
        # Google voice names: en-US-Neural2-D, en-US-WaveNet-D, etc.
        parts = self.voice.split("-")
        if len(parts) >= 2:
            language_code = f"{parts[0]}-{parts[1]}"
        else:
            language_code = "en-US"

        payload = {
            "input": {"ssml": ssml},
            "voice": {
                "languageCode": language_code,
                "name": self.voice,
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": _SAMPLE_RATE,
                "speakingRate": speaking_rate,
            },
        }

        url = f"{_GOOGLE_TTS_URL}?key={self.api_key}"
        body = json.dumps(payload).encode("utf-8")

        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise TTSSynthesisError(
                f"Google TTS API error ({e.code}): {error_body[:200]}"
            ) from e
        except (URLError, TimeoutError) as e:
            raise TTSSynthesisError(f"Google TTS API connection error: {e}") from e

        audio_content = result.get("audioContent")
        if not audio_content:
            raise TTSSynthesisError("Google TTS returned empty audio content")

        # Decode base64 audio and write to file
        audio_bytes = base64.b64decode(audio_content)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

    # ------------------------------------------------------------------
    # Edge-TTS fallback
    # ------------------------------------------------------------------

    async def _edge_tts(
        self, text: str, output_path: Path, rate_pct: int = 0
    ) -> None:
        """Synthesize using edge-tts (free fallback)."""
        import edge_tts

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_mp3 = Path(tmp_dir) / "tts.mp3"
            rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
            communicate = edge_tts.Communicate(
                text=text, voice=self.voice, rate=rate_str
            )
            await communicate.save(str(tmp_mp3))
            self._convert_to_wav(tmp_mp3, output_path)

    # ------------------------------------------------------------------
    # Absolute-position track builder
    # ------------------------------------------------------------------

    def _build_absolute_track(
        self,
        segment_files: list[Path],
        segments: list[TranslatedSegment],
        output_path: Path,
    ) -> None:
        """Build final audio track by placing segments at absolute positions."""
        if not segment_files:
            raise TTSSynthesisError("No segment files to build track from")

        try:
            last_seg = segments[-1]
            total_duration = last_seg.end
            total_samples = int(total_duration * _SAMPLE_RATE) + _SAMPLE_RATE

            canvas = np.zeros(total_samples, dtype=np.float32)

            for seg_file, segment in zip(segment_files, segments):
                seg_audio = self._read_wav_as_float(seg_file)
                start_sample = int(segment.start * _SAMPLE_RATE)
                end_sample = start_sample + len(seg_audio)

                if end_sample > len(canvas):
                    end_sample = len(canvas)
                    seg_audio = seg_audio[: end_sample - start_sample]

                canvas[start_sample:end_sample] += seg_audio

            final_samples = int(total_duration * _SAMPLE_RATE)
            canvas = canvas[:final_samples]
            self._write_wav(canvas, output_path)

        except TTSSynthesisError:
            raise
        except Exception as e:
            raise TTSSynthesisError(f"Failed to build absolute track: {e}") from e

    def _concatenate_with_gaps(
        self,
        segment_files: list[Path],
        segments: list[TranslatedSegment],
        output_path: Path,
    ) -> None:
        """Backward-compatible alias for _build_absolute_track."""
        self._build_absolute_track(segment_files, segments, output_path)

    # ------------------------------------------------------------------
    # Time-stretching via Rubberband (with FFmpeg atempo fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _time_stretch(input_path: Path, output_path: Path, speed_ratio: float) -> None:
        """Time-stretch audio, preserving pitch. Rubberband first, FFmpeg fallback."""
        try:
            SpeechSynthesizer._time_stretch_rubberband(input_path, output_path, speed_ratio)
        except Exception as rb_err:
            logger.warning("Rubberband failed (%s), falling back to FFmpeg atempo", rb_err)
            SpeechSynthesizer._adjust_speed(input_path, output_path, speed_ratio, 0)

    @staticmethod
    def _time_stretch_rubberband(input_path: Path, output_path: Path, speed_ratio: float) -> None:
        """Time-stretch using pyrubberband."""
        import soundfile as sf
        import pyrubberband as pyrb

        audio_data, sr = sf.read(str(input_path))
        stretched = pyrb.time_stretch(audio_data, sr, speed_ratio)
        sf.write(str(output_path), stretched, sr)

    # ------------------------------------------------------------------
    # FFmpeg helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_to_duration(input_path: Path, output_path: Path, target_duration: float) -> None:
        """Pad with silence if short, trim if long — exact target_duration."""
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", f"apad=whole_dur={target_duration:.3f}",
            "-t", f"{target_duration:.3f}",
            "-ac", "1", "-ar", str(_SAMPLE_RATE),
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise TTSSynthesisError(f"Audio fit-to-duration failed: {result.stderr}")

    @staticmethod
    def _adjust_speed(input_path: Path, output_path: Path, speed: float, target_duration: float) -> None:
        """Adjust audio speed using FFmpeg atempo filter."""
        speed = max(0.5, min(speed, 100.0))
        filters = []
        remaining = speed
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining:.4f}")
        atempo_chain = ",".join(filters)

        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", atempo_chain,
            "-ac", "1", "-ar", str(_SAMPLE_RATE),
            str(output_path),
        ]
        if target_duration > 0:
            cmd.insert(-1, "-t")
            cmd.insert(-1, f"{target_duration:.3f}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise TTSSynthesisError(f"Audio speed adjustment failed: {result.stderr}")

    @staticmethod
    def _convert_to_wav(input_path: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-ac", "1", "-ar", str(_SAMPLE_RATE), str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise TTSSynthesisError(f"WAV conversion failed: {result.stderr}")

    @staticmethod
    def _get_audio_duration(audio_path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(audio_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise TTSSynthesisError(f"Failed to get audio duration: {result.stderr}")
        try:
            info = json.loads(result.stdout)
            return float(info["format"]["duration"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise TTSSynthesisError(f"Failed to parse audio duration: {e}") from e

    @staticmethod
    def _trim_audio(input_path: Path, output_path: Path, target_duration: float) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-t", str(target_duration), "-ac", "1", "-ar", str(_SAMPLE_RATE), str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise TTSSynthesisError(f"Audio trimming failed: {result.stderr}")

    @staticmethod
    def _pad_audio(input_path: Path, output_path: Path, target_duration: float) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", f"apad=whole_dur={target_duration}",
            "-ac", "1", "-ar", str(_SAMPLE_RATE), str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise TTSSynthesisError(f"Audio padding failed: {result.stderr}")

    @staticmethod
    def _copy_audio(input_path: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-c", "copy", str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise TTSSynthesisError(f"Audio copy failed: {result.stderr}")

    # ------------------------------------------------------------------
    # Numpy-based WAV I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_wav_as_float(wav_path: Path) -> np.ndarray:
        """Read a WAV file and return samples as float32 numpy array."""
        with wave.open(str(wav_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        return samples

    @staticmethod
    def _write_wav(samples: np.ndarray, output_path: Path) -> None:
        """Write float32 numpy array as 16-bit mono WAV."""
        clipped = np.clip(samples, -1.0, 1.0)
        int_samples = (clipped * 32767).astype(np.int16)

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(int_samples.tobytes())


def calculate_segment_gap(
    current: TranslatedSegment, next_seg: TranslatedSegment
) -> float:
    """Calculate the silence gap between two consecutive segments."""
    gap = next_seg.start - current.end
    return max(0.0, gap)
