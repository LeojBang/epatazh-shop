import pytest

from app.admin.uploads import MAX_UPLOAD_BYTES, save_upload


class _FakeUpload:
    """Минимальный аналог UploadFile: имя + async read()."""

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


class TestSaveUpload:
    @pytest.mark.asyncio
    async def test_rejects_bad_extension(self):
        f = _FakeUpload("evil.svg", b"<svg/>")
        assert await save_upload(f) is None

    @pytest.mark.asyncio
    async def test_rejects_oversized_file(self):
        f = _FakeUpload("big.jpg", b"x" * (MAX_UPLOAD_BYTES + 1))
        assert await save_upload(f) is None

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self):
        f = _FakeUpload("empty.jpg", b"")
        assert await save_upload(f) is None

    @pytest.mark.asyncio
    async def test_rejects_non_image_content(self):
        # Правильное расширение, но содержимое — не картинка
        f = _FakeUpload("fake.png", b"not really a png")
        assert await save_upload(f) is None
