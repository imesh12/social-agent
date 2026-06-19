from pathlib import Path

from PIL import Image, ImageDraw


class ImageService:
    def ensure_default_background(self, path: str = "storage/backgrounds/default.jpg") -> str:
        background_path = Path(path)
        if background_path.exists():
            return str(background_path)

        background_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1080, 1920), color=(18, 24, 38))
        draw = ImageDraw.Draw(image)

        for y in range(1920):
            blue = 38 + int(y / 1920 * 72)
            green = 24 + int(y / 1920 * 36)
            draw.line([(0, y), (1080, y)], fill=(18, green, blue))

        image.save(background_path, format="JPEG", quality=92)
        return str(background_path)
