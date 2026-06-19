from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class ThumbnailService:
    def generate_thumbnail(
        self,
        output_path: str,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(image)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            red = int(18 + ratio * 20)
            green = int(28 + ratio * 58)
            blue = int(68 + ratio * 82)
            draw.line([(0, y), (width, y)], fill=(red, green, blue))

        title_lines = ["TOP 3 AI TOOLS", "YOU NEED IN 2026"]
        font = self._load_font(92)
        line_height = 110
        total_height = line_height * len(title_lines)
        start_y = (height - total_height) // 2

        for index, line in enumerate(title_lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = start_y + index * line_height
            draw.text((x + 5, y + 6), line, font=font, fill=(0, 0, 0))
            draw.text((x, y), line, font=font, fill=(255, 255, 255))

        image.save(path, format="JPEG", quality=92)

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/Arial.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()
