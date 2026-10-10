"""Validate, strip metadata, and re-encode uploaded images."""

from __future__ import annotations

import uuid
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 8_000_000


class ImageError(ValueError):
    pass


def save_upload(file_storage, upload_dir: str | Path) -> str:
    raw = file_storage.read()
    if not raw:
        raise ImageError("The photo file is empty.")
    if len(raw) > MAX_BYTES:
        raise ImageError("Photos must be 5 MB or smaller.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # Opening only reads the header, so format and size are checked before decoding.
            image = Image.open(BytesIO(raw))
            fmt = image.format
            width, height = image.size
            if fmt not in ALLOWED_FORMATS:
                raise ImageError("Use JPEG, PNG, WebP or GIF photos.")
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise ImageError("The image dimensions are too large (limit about 8 megapixels).")
            image.load()
            rgb = image.convert("RGB")
    except ImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageError("The image dimensions are too large (limit about 8 megapixels).") from exc
    except UnidentifiedImageError as exc:
        raise ImageError("The file is not a supported image.") from exc
    except (OSError, SyntaxError, ValueError, EOFError, MemoryError) as exc:
        raise ImageError("The photo appears to be corrupt or truncated. Please choose another file.") from exc

    filename = f"{uuid.uuid4().hex}.jpg"
    dest = Path(upload_dir) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Re-encode without EXIF/metadata.
    rgb.save(dest, format="JPEG", quality=85, optimize=True)
    return filename


def write_demo_jpeg(path: Path, color: tuple[int, int, int], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (640, 400), color)
    img.save(path, format="JPEG", quality=80)
