"""Image operations."""

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


def invert(image: Image.Image) -> Image.Image:
    """Invert image colors."""
    if image.mode == "RGBA":
        r, g, b, a = image.split()
        rgb = Image.merge("RGB", (r, g, b))
        inverted = ImageOps.invert(rgb)
        r2, g2, b2 = inverted.split()
        return Image.merge("RGBA", (r2, g2, b2, a))
    elif image.mode == "RGB":
        return ImageOps.invert(image)
    else:
        return ImageOps.invert(image.convert("RGB"))


def grayscale(image: Image.Image) -> Image.Image:
    """Convert to grayscale."""
    return ImageOps.grayscale(image)


def blur(image: Image.Image, radius: float = 2.0) -> Image.Image:
    """Apply Gaussian blur."""
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def watermark(
    image: Image.Image,
    text: str,
    position: str = "bottom-right",
    opacity: float = 0.5,
    font_size: int | None = None,
) -> Image.Image:
    """Add text watermark."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    size = font_size or max(12, min(image.width, image.height) // 20)
    font = _load_font(size)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad = 10
    positions = {
        "top-left": (pad, pad),
        "top-right": (image.width - text_w - pad, pad),
        "bottom-left": (pad, image.height - text_h - pad),
        "bottom-right": (image.width - text_w - pad, image.height - text_h - pad),
        "center": ((image.width - text_w) // 2, (image.height - text_h) // 2),
    }
    pos = positions.get(position, positions["bottom-right"])

    draw.text(pos, text, font=font, fill=(255, 255, 255, int(255 * opacity)))
    return Image.alpha_composite(image, overlay)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font, falling back to default if necessary."""
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()
