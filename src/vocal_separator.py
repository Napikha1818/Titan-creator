"""Vocal separation using Demucs to split audio into vocals and background/SFX."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from src.errors import AudioExtractionError

logger = logging.getLogger(__name__)


class VocalSeparator:
    """Separate vocals from background audio (SFX, music) using Demucs."""

    def __init__(self, model: str = "htdemucs") -> None:
        """Initialize VocalSeparator.

        Args:
            model: Demucs model name. 'htdemucs' is the default hybrid model.
        """
        self.model = model

    def separate(
        self, audio_path: Path, output_dir: Path
    ) -> tuple[Path, Path]:
        """Separate audio into vocals and non-vocals (SFX/background).

        Args:
            audio_path: Path to the input audio file (WAV).
            output_dir: Directory where separated tracks will be saved.

        Returns:
            Tuple of (vocals_path, background_path).

        Raises:
            AudioExtractionError: If separation fails.
        """
        if not audio_path.exists():
            raise AudioExtractionError(
                f"Audio file not found: {audio_path}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "python3.11", "-m", "demucs",
            "--two-stems", "vocals",
            "-n", self.model,
            "--out", str(output_dir),
            "--device", "cpu",
            str(audio_path),
        ]

        logger.info("Running Demucs vocal separation on %s", audio_path.name)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout for CPU processing
            )
        except FileNotFoundError:
            raise AudioExtractionError(
                "Demucs not found. Make sure it's installed: pip install demucs"
            )
        except subprocess.TimeoutExpired:
            raise AudioExtractionError(
                "Vocal separation timed out (exceeded 10 minutes)."
            )

        if result.returncode != 0:
            raise AudioExtractionError(
                f"Demucs separation failed: {result.stderr[-500:]}"
            )

        # Demucs outputs to: output_dir/{model}/{stem_name}/vocals.wav and no_vocals.wav
        stem_name = audio_path.stem
        demucs_out = output_dir / self.model / stem_name

        vocals_path = demucs_out / "vocals.wav"
        no_vocals_path = demucs_out / "no_vocals.wav"

        if not vocals_path.exists() or not no_vocals_path.exists():
            # Try alternative naming
            possible_dirs = list((output_dir / self.model).iterdir()) if (output_dir / self.model).exists() else []
            logger.error(
                "Expected Demucs output not found. Available: %s",
                [str(p) for p in possible_dirs]
            )
            raise AudioExtractionError(
                f"Demucs output files not found at {demucs_out}. "
                f"Expected vocals.wav and no_vocals.wav"
            )

        logger.info(
            "Vocal separation complete: vocals=%s, background=%s",
            vocals_path, no_vocals_path
        )

        return vocals_path, no_vocals_path
