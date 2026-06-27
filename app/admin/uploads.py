import io
import logging
import uuid
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

UPLOAD_DIR = Path("app/static/uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
TARGET_SIZE = 1000  # итоговый квадрат, px
JPEG_QUALITY = 85
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 МБ — лимит на размер файла
# Защита от decompression bomb
Image.MAX_IMAGE_PIXELS = 50_000_000  # ~50 Мп


async def save_upload(file) -> str | None:
    """Сохраняет загруженный файл: приводит к квадрату TARGET_SIZE, сжимает в JPEG."""
    if not file or not getattr(file, "filename", None):
        log.warning("save_upload: файл не передан или нет имени")
        return None

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        log.warning(
            "save_upload: недопустимое расширение %r (файл: %s)", ext, file.filename
        )
        return None

    content = await file.read()

    if not content:
        log.warning("save_upload: пустое содержимое файла %s", file.filename)
        return None

    if len(content) > MAX_UPLOAD_BYTES:
        log.warning("save_upload: файл слишком большой %d байт", len(content))
        return None

    try:
        img = Image.open(io.BytesIO(content))
        # Загружаем полностью (без verify — он избыточен и ломает поток)
        img.load()
    except Exception as e:
        log.warning(
            "save_upload: не удалось открыть изображение %s: %s", file.filename, e
        )
        return None

    try:
        # Учитываем EXIF-ориентацию (фото с телефона иногда повёрнуты)
        img = ImageOps.exif_transpose(img)

        # Приводим к RGB (на случай PNG с прозрачностью или CMYK)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Обрезаем по центру до квадрата и масштабируем до TARGET_SIZE
        img = ImageOps.fit(img, (TARGET_SIZE, TARGET_SIZE), method=Image.LANCZOS)

        filename = f"{uuid.uuid4().hex}.jpg"
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        img.save(
            UPLOAD_DIR / filename, format="JPEG", quality=JPEG_QUALITY, optimize=True
        )

        log.info("save_upload: сохранён файл %s", filename)
        return filename

    except Exception as e:
        log.warning(
            "save_upload: ошибка обработки изображения %s: %s", file.filename, e
        )
        return None
