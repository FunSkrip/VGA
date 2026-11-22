"""Validate that an uploaded file's real container matches its extension.

An extension and the browser-provided Content-Type are attacker-controlled.
Magic bytes are the first gate before OpenCV/imageio/ffmpeg parse untrusted data.
"""
from __future__ import annotations

import os

MAX_IMAGE_PIXELS = 50_000_000
MAX_GIF_PIXELS = 50_000_000
MAX_GIF_FRAMES = 1_000
MAX_VIDEO_SECONDS = 600
MAX_VIDEO_WIDTH = 7_680
MAX_VIDEO_HEIGHT = 4_320

_HEADER_BYTES = 32

_EXPECTED_KIND = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "gif": "gif",
    "mp4": "isobmff",
    "mov": "isobmff",
    "avi": "avi",
}


class UnsupportedMediaError(ValueError):
    """Raised when the uploaded bytes do not match a supported media format."""


def sniff_media_kind(path: str) -> str | None:
    with open(path, "rb") as media_file:
        header = media_file.read(_HEADER_BYTES)

    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "avi"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "isobmff"
    return None


def validate_media_signature(path: str, extension: str) -> str:
    """Verify the real format and return the detected kind."""
    normalized_extension = str(extension or "").lower().lstrip(".")
    expected_kind = _EXPECTED_KIND.get(normalized_extension)
    if expected_kind is None:
        raise UnsupportedMediaError("Недопустимое расширение файла")

    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise UnsupportedMediaError("Файл пуст или недоступен")

    actual_kind = sniff_media_kind(path)
    if actual_kind is None:
        raise UnsupportedMediaError("Не удалось определить реальный формат файла")
    if actual_kind != expected_kind:
        raise UnsupportedMediaError(
            "Содержимое файла не соответствует его расширению"
        )
    return actual_kind


def gif_dimensions(path: str) -> tuple[int, int]:
    with open(path, "rb") as media_file:
        header = media_file.read(10)
    if len(header) < 10 or not header.startswith((b"GIF87a", b"GIF89a")):
        raise UnsupportedMediaError("Некорректный GIF")
    width = int.from_bytes(header[6:8], "little")
    height = int.from_bytes(header[8:10], "little")
    if width <= 0 or height <= 0:
        raise UnsupportedMediaError("Некорректные размеры GIF")
    return width, height


def png_dimensions(path: str) -> tuple[int, int]:
    with open(path, "rb") as media_file:
        header = media_file.read(24)
    if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UnsupportedMediaError("Некорректный PNG")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width <= 0 or height <= 0:
        raise UnsupportedMediaError("Некорректные размеры PNG")
    return width, height


def enforce_gif_limits(path: str) -> None:
    width, height = gif_dimensions(path)
    if width * height > MAX_GIF_PIXELS:
        raise UnsupportedMediaError("GIF слишком большой по разрешению")


def enforce_image_pixel_limit(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise UnsupportedMediaError("Изображение слишком большое по разрешению")


def enforce_video_limits(width: int, height: int, fps: float, frame_count: float) -> None:
    if width <= 0 or height <= 0:
        raise UnsupportedMediaError("Некорректные параметры видео")
    if width > MAX_VIDEO_WIDTH or height > MAX_VIDEO_HEIGHT:
        raise UnsupportedMediaError("Видео слишком большое по разрешению")
    if fps and fps > 0 and frame_count and frame_count > 0:
        duration = frame_count / fps
        if duration > MAX_VIDEO_SECONDS:
            raise UnsupportedMediaError("Видео слишком длинное")
