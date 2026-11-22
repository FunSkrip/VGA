import pytest

from app.file_validation import (
    UnsupportedMediaError,
    enforce_gif_limits,
    enforce_image_pixel_limit,
    enforce_video_limits,
    gif_dimensions,
    png_dimensions,
    sniff_media_kind,
    validate_media_signature,
)


def test_jpeg_signature_accepts_matching_extension(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    assert sniff_media_kind(str(path)) == "jpeg"
    assert validate_media_signature(str(path), "jpg") == "jpeg"


def test_extension_mismatch_is_rejected(tmp_path):
    path = tmp_path / "fake.jpg"
    path.write_bytes(b"<html>not an image</html>")
    with pytest.raises(UnsupportedMediaError):
        validate_media_signature(str(path), "jpg")


def test_png_and_gif_and_video_signatures(tmp_path):
    png = tmp_path / "image.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (10).to_bytes(4, "big")
        + (20).to_bytes(4, "big")
        + b"\x00" * 8
    )
    gif = tmp_path / "image.gif"
    gif.write_bytes(b"GIF89a" + (30).to_bytes(2, "little") + (40).to_bytes(2, "little") + b"\x00" * 8)
    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16)
    avi = tmp_path / "video.avi"
    avi.write_bytes(b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 16)

    assert validate_media_signature(str(png), "png") == "png"
    assert validate_media_signature(str(gif), "gif") == "gif"
    assert validate_media_signature(str(mp4), "mp4") == "isobmff"
    assert validate_media_signature(str(avi), "avi") == "avi"


def test_dimensions_and_limits(tmp_path):
    gif = tmp_path / "image.gif"
    gif.write_bytes(b"GIF87a" + (30).to_bytes(2, "little") + (40).to_bytes(2, "little") + b"\x00" * 8)
    assert gif_dimensions(str(gif)) == (30, 40)
    enforce_gif_limits(str(gif))

    png = tmp_path / "image.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (30).to_bytes(4, "big")
        + (40).to_bytes(4, "big")
        + b"\x00" * 8
    )
    assert png_dimensions(str(png)) == (30, 40)

    with pytest.raises(UnsupportedMediaError):
        enforce_image_pixel_limit(100_000, 100_000)
    with pytest.raises(UnsupportedMediaError):
        enforce_video_limits(8000, 100, 25, 100)
    with pytest.raises(UnsupportedMediaError):
        enforce_video_limits(100, 100, 25, 25 * 601)
