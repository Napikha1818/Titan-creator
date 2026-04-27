"""Google Drive file management — direct download using gdown (no API credentials needed)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import gdown

from src.config import GOOGLE_DRIVE_PATTERNS
from src.errors import DriveDownloadError

logger = logging.getLogger(__name__)


def download_from_drive(drive_url: str, output_path: Path) -> Path:
    """Download a public file from Google Drive using gdown.

    No API credentials needed — works for files shared as 'Anyone with the link'.
    Handles Google Drive's virus scan confirmation pages automatically.

    Args:
        drive_url: Google Drive URL containing the file ID.
        output_path: Local path where the downloaded file will be saved.

    Returns:
        Path to the downloaded file.

    Raises:
        DriveDownloadError: If the file ID cannot be extracted or download fails.
    """
    file_id = extract_file_id(drive_url)
    if file_id is None:
        raise DriveDownloadError(
            f"Could not extract file ID from URL: {drive_url}"
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # gdown handles virus scan confirmation automatically
        download_url = f"https://drive.google.com/uc?id={file_id}"
        result = gdown.download(download_url, str(output_path), quiet=False)

        if result is None or not output_path.exists():
            raise DriveDownloadError(
                "Download gagal. Pastikan file di-share sebagai 'Anyone with the link'."
            )

        file_size = output_path.stat().st_size
        if file_size < 10000:
            # Check if we got an HTML error page instead of actual video
            content_check = output_path.read_bytes()[:500]
            if b"<!DOCTYPE" in content_check or b"<html" in content_check:
                output_path.unlink(missing_ok=True)
                raise DriveDownloadError(
                    "File tidak dapat didownload. Pastikan file di-share sebagai 'Anyone with the link'."
                )

        logger.info(
            "Downloaded %s from Google Drive (%d bytes)",
            output_path.name,
            file_size,
        )
        return output_path

    except DriveDownloadError:
        raise
    except Exception as exc:
        raise DriveDownloadError(
            f"Failed to download file from Google Drive: {exc}"
        ) from exc


def extract_file_id(url: str) -> str | None:
    """Extract the file ID from a Google Drive URL.

    Supports URL formats:
    - https://drive.google.com/file/d/{id}/...
    - https://drive.google.com/open?id={id}

    Args:
        url: Google Drive URL string.

    Returns:
        The extracted file ID, or None if no match is found.
    """
    for pattern in GOOGLE_DRIVE_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_drive_url(text: str) -> bool:
    """Check whether the text contains a valid Google Drive URL.

    Args:
        text: Text string to check.

    Returns:
        True if the text contains a Google Drive URL matching a supported pattern.
    """
    return any(re.search(pattern, text) for pattern in GOOGLE_DRIVE_PATTERNS)
