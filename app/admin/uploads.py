import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps

UPLOAD_DIR = Path("app/static/uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
TARGET_SIZE = 1000  # итоговый квадрат, px
JPEG_QUALITY = 85


async def save_upload(file) -> str | None:
    """Сохраняет загруженный файл: приводит к квадрату TARGET_SIZE, сжимает в JPEG."""
    if not file or not getattr(file, "filename", None):
        return None

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None

    content = await file.read()

    try:
        img = Image.open(io.BytesIO(content))
    except Exception:
        return None

    # Учитываем EXIF-ориентацию (фото с телефона иногда повёрнуты)
    img = ImageOps.exif_transpose(img)

    # Приводим к RGB (на случай PNG с прозрачностью или CMYK)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Обрезаем по центру до квадрата и масштабируем до TARGET_SIZE
    img = ImageOps.fit(img, (TARGET_SIZE, TARGET_SIZE), method=Image.LANCZOS)

    filename = f"{uuid.uuid4().hex}.jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    img.save(UPLOAD_DIR / filename, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    return filename