"""Loads a pet's animations from ASSETS_DIR/<name>/ and hands out cached
frames: PIL images (for effects) and ImageTk.PhotoImage (for drawing).

Animation keys: "stand" (always present, faces left), "walk_left",
"walk_right" and "sleep" (optional).
"""
import json
import math
import os
import re
import statistics

from PIL import Image, ImageDraw, ImageOps, ImageSequence, ImageTk

from .config import ASSETS_DIR, CUSTOM_DIR, STAND_FRAME_MS

_FRAME_FILE = re.compile(r"^(?P<prefix>.+)_(?P<index>\d+)\.png$")
_WALK_KEYS = ("walk_left", "walk_right")


class Animation:
    def __init__(self, frames, durations_ms):
        self.frames = frames
        self.durations = [max(1, int(d)) for d in durations_ms]
        self.count = len(frames)
        self.size = frames[0].size


def _load_groups(folder: str) -> dict[str, list[Image.Image]]:
    found: dict[str, list[tuple[int, str]]] = {}
    for filename in os.listdir(folder):
        m = _FRAME_FILE.match(filename)
        if m:
            found.setdefault(m["prefix"], []).append((int(m["index"]), filename))
    return {
        prefix: [Image.open(os.path.join(folder, f)).convert("RGBA") for _, f in sorted(files)]
        for prefix, files in found.items()
    }


def _union_bbox(frames):
    boxes = [b for b in (f.getchannel("A").getbbox() for f in frames) if b]
    if not boxes:
        return (0, 0, *frames[0].size)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _mass(frame: Image.Image) -> int:
    return sum(frame.getchannel("A").histogram()[1:])


def _scaled(frames, scale: float, smooth: bool = False):
    """Resize frames. Pixel-art sprites use NEAREST to stay crisp; `smooth` (for
    large drawn artwork being shrunk a lot) uses a proper filter, then snaps
    alpha to 0/255 so no half-transparent fringe gets blended into the window's
    transparent colour key."""
    if scale == 1:
        return frames
    out = []
    for f in frames:
        size = (max(1, round(f.width * scale)), max(1, round(f.height * scale)))
        if smooth:
            r, g, b, a = f.resize(size, Image.LANCZOS).split()
            f = Image.merge("RGBA", (r, g, b, a.point(lambda v: 255 if v >= 128 else 0)))
        else:
            f = f.resize(size, Image.NEAREST)
        out.append(f)
    return out


def _key_background(frame: Image.Image) -> Image.Image:
    """Make a flat, opaque background transparent by flood-filling in from the corners."""
    img = frame.convert("RGBA")
    w, h = img.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if img.getpixel(corner)[3] == 255:
            ImageDraw.floodfill(img, corner, (0, 0, 0, 0), thresh=40)
    return img


def _load_custom_run(name: str):
    """A user-supplied moving animation: CUSTOM_DIR/<name>/run.gif, facing right.
    Returns (frames, durations_ms) or None if absent or unreadable."""
    path = os.path.join(CUSTOM_DIR, name, "run.gif")
    if not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as gif:
            frames = [_key_background(f) for f in ImageSequence.Iterator(gif)]
            durations = []
            for i in range(len(frames)):
                gif.seek(i)
                durations.append(gif.info.get("duration") or 60)
    except (OSError, ValueError, EOFError):
        return None
    return (frames, durations) if frames else None


class SpriteSet:
    def __init__(self, name: str, scale: float):
        self.name = name
        folder = os.path.join(ASSETS_DIR, name)
        groups = _load_groups(folder)
        if "stand" not in groups:
            raise FileNotFoundError(f"No sprite frames for '{name}' in {folder}; the first-launch download hasn't run.")
        with open(os.path.join(folder, "meta.json"), encoding="utf8") as f:
            meta = json.load(f)

        # Crop each animation to its tight bounding box, so "bottom of the
        # image" really is the feet and frames don't jitter against each other.
        stand = [f.crop(_union_bbox(groups["stand"])) for f in groups["stand"]]
        self.anims: dict[str, Animation] = {
            "stand": Animation(_scaled(stand, scale), [meta.get("stand_ms", STAND_FRAME_MS)] * len(stand))
        }

        # The walking/sleeping art is drawn at a different size from the
        # standing sprite, so each source is scaled to about the same body mass.
        def size_factor(frames):  # median: robust to crouch/stretch frames
            return math.sqrt(_mass(stand[0]) / max(1, statistics.median(_mass(f) for f in frames)))

        pmd_walk = groups.get("walk_right") or groups.get("walk_left")
        pmd_factor = size_factor(pmd_walk) if pmd_walk else None
        walk_factor, smooth_walk = pmd_factor, False

        custom_run = _load_custom_run(name)  # the user's own run animation replaces the downloaded walk
        if custom_run is not None:
            frames, durations = custom_run
            groups["walk_right"] = frames
            groups["walk_left"] = [ImageOps.mirror(f) for f in frames]
            meta["walk_ms"] = durations
            walk_factor, smooth_walk = size_factor(frames), True

        for key in (*_WALK_KEYS, "sleep"):
            is_walk = key in _WALK_KEYS
            factor = walk_factor if is_walk else pmd_factor
            frames = groups.get(key)
            if not frames or factor is None:
                continue
            cropped = [f.crop(_union_bbox(frames)) for f in frames]
            durations = meta.get("walk_ms" if is_walk else "sleep_ms", [120] * len(cropped))
            durations = (durations + [durations[-1]] * len(cropped))[: len(cropped)]
            self.anims[key] = Animation(_scaled(cropped, scale * factor, is_walk and smooth_walk), durations)

        self.width, self.height = self.anims["stand"].size
        self._images: dict[tuple, Image.Image] = {}
        self._photos: dict[tuple, ImageTk.PhotoImage] = {}

    def has(self, key: str) -> bool:
        return key in self.anims

    def get_image(self, key: str, frame_idx: int, mirror: bool = False, rotate: int = 0) -> Image.Image:
        anim = self.anims[key]
        frame_idx %= anim.count
        cache_key = (key, frame_idx, mirror, rotate)
        img = self._images.get(cache_key)
        if img is None:
            img = anim.frames[frame_idx]
            if mirror:
                img = ImageOps.mirror(img)
            if rotate:
                img = img.rotate(rotate, expand=True, resample=Image.BICUBIC)
            self._images[cache_key] = img
        return img

    def get_photo(self, key: str, frame_idx: int, mirror: bool = False, rotate: int = 0) -> ImageTk.PhotoImage:
        cache_key = (key, frame_idx % self.anims[key].count, mirror, rotate)
        photo = self._photos.get(cache_key)
        if photo is None:
            photo = ImageTk.PhotoImage(self.get_image(key, frame_idx, mirror, rotate))
            self._photos[cache_key] = photo
        return photo


_sprite_sets: dict[tuple[str, float], SpriteSet] = {}


def get_sprite_set(name: str, scale: float) -> SpriteSet:
    key = (name, scale)
    sprite_set = _sprite_sets.get(key)
    if sprite_set is None:
        sprite_set = SpriteSet(name, scale)
        _sprite_sets[key] = sprite_set
    return sprite_set
