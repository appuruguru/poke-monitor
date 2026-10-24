"""The app icon (a small pokeball drawn on the fly, so no icon asset is needed)."""
from PIL import Image, ImageDraw


def make_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, size // 21)
    line = max(1, size // 21)
    box = (pad, pad, size - pad, size - pad)
    draw.ellipse(box, fill="white", outline="black", width=line)
    draw.pieslice(box, 180, 360, fill="#e3350d", outline="black", width=line)
    mid = size // 2
    draw.rectangle((pad, mid - line, size - pad, mid + line), fill="black")
    r = size // 6
    draw.ellipse((mid - r, mid - r, mid + r, mid + r), fill="white", outline="black", width=line)
    return img
