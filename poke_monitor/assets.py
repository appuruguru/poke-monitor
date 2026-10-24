"""First-launch sprite download.

The sprites belong to their respective rights holders (and the
walking/sleeping ones are community fan art), so they are deliberately not
shipped in this repo or in the exe. Each pet's art is fetched once and
cached under ASSETS_DIR:

* standing animation  - PokeAPI/sprites (Gen V animated sprites)
* walking / sleeping  - PMDCollab/SpriteCollab (community Mystery Dungeon-style
                        sprites; non-commercial use with credit, see README)
"""
import io
import json
import os
import shutil
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image, ImageSequence

from .config import APP_ID, ASSETS_DIR, PETS, STAND_FRAME_MS

_STAND_DIR = "poke" + "mon"  # upstream's folder name for this sprite set
STAND_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/" + _STAND_DIR + "/"
    "versions/generation-v/black-white/animated/{id}.gif"
)
PMD_URL = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/sprite/{id:04d}/{file}"

META_VERSION = 3  # bump to make every install re-download its sprites
_ROW_EAST, _ROW_WEST = 2, 6  # PMD sheet rows: S, SE, E, NE, N, NW, W, SW
_PMD_TICK_MS = 1000 / 60  # PMD frame durations are in 1/60 s ticks


def _has_frames(name: str) -> bool:
    try:
        with open(os.path.join(ASSETS_DIR, name, "meta.json"), encoding="utf8") as f:
            return json.load(f).get("version") == META_VERSION
    except (OSError, ValueError):
        return False


def missing_sprites() -> list[str]:
    return [name for name in PETS if not _has_frames(name)]


def _get(url: str, optional: bool = False) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if optional and exc.code == 404:
            return None
        raise


def _anim_table(xml_bytes: bytes) -> dict[str, tuple[int, int, list[int]]]:
    """AnimData.xml -> {anim name: (frame_w, frame_h, [durations in ticks])}"""
    table = {}
    for anim in ET.fromstring(xml_bytes).iter("Anim"):
        name = anim.findtext("Name")
        width, height = anim.findtext("FrameWidth"), anim.findtext("FrameHeight")
        if name and width and height:
            table[name] = (int(width), int(height), [int(d.text) for d in anim.iter("Duration")])
    return table


def _slice_row(sheet: Image.Image, frame_w: int, frame_h: int, count: int, row: int) -> list[Image.Image]:
    count = min(count, sheet.width // frame_w)
    if count < 1 or sheet.height < (row + 1) * frame_h:
        return []
    return [
        sheet.crop((i * frame_w, row * frame_h, (i + 1) * frame_w, (row + 1) * frame_h))
        for i in range(count)
    ]


def _save_frames(folder: str, prefix: str, frames) -> None:
    for i, frame in enumerate(frames):
        frame.convert("RGBA").save(os.path.join(folder, f"{prefix}_{i}.png"))


def _fetch_pmd(dex_id: int, folder: str, meta: dict) -> None:
    """Walking + sleeping animations. All optional: a pet without them just
    keeps using its standing animation."""
    xml_bytes = _get(PMD_URL.format(id=dex_id, file="AnimData.xml"), optional=True)
    if xml_bytes is None:
        return
    table = _anim_table(xml_bytes)

    walk = table.get("Walk")
    walk_png = _get(PMD_URL.format(id=dex_id, file="Walk-Anim.png"), optional=True) if walk else None
    if walk and walk_png:
        frame_w, frame_h, durations = walk
        with Image.open(io.BytesIO(walk_png)) as sheet:
            right = _slice_row(sheet, frame_w, frame_h, len(durations), _ROW_EAST)
            left = _slice_row(sheet, frame_w, frame_h, len(durations), _ROW_WEST)
        if right and left:
            _save_frames(folder, "walk_right", right)
            _save_frames(folder, "walk_left", left)
            meta["walk_ms"] = [max(30, round(d * _PMD_TICK_MS)) for d in durations[: len(right)]]

    sleep = table.get("Sleep")
    sleep_png = _get(PMD_URL.format(id=dex_id, file="Sleep-Anim.png"), optional=True) if sleep else None
    if sleep and sleep_png:
        frame_w, frame_h, durations = sleep
        with Image.open(io.BytesIO(sleep_png)) as sheet:
            frames = _slice_row(sheet, frame_w, frame_h, len(durations), 0)
        if frames:
            _save_frames(folder, "sleep", frames)
            meta["sleep_ms"] = [max(30, round(d * _PMD_TICK_MS)) for d in durations[: len(frames)]]

    credits = _get(PMD_URL.format(id=dex_id, file="credits.txt"), optional=True)
    if credits:
        with open(os.path.join(folder, "credits.txt"), "wb") as f:
            f.write(credits)


def download_sprites(names, progress=None) -> None:
    """Download and slice each named pet. Raises OSError (incl. URLError) on failure."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    for i, name in enumerate(names, 1):
        if progress:
            progress(i, len(names), name)
        dex_id = PETS[name]
        stand_gif = _get(STAND_URL.format(id=dex_id))

        final = os.path.join(ASSETS_DIR, name)
        partial = final + ".partial"  # build aside, then swap in, so a failure never leaves half a sprite
        shutil.rmtree(partial, ignore_errors=True)
        os.makedirs(partial)

        meta = {"version": META_VERSION, "stand_ms": STAND_FRAME_MS}
        with Image.open(io.BytesIO(stand_gif)) as gif:
            _save_frames(partial, "stand", [f.copy() for f in ImageSequence.Iterator(gif)])
        _fetch_pmd(dex_id, partial, meta)
        with open(os.path.join(partial, "meta.json"), "w", encoding="utf8") as f:
            json.dump(meta, f)

        shutil.rmtree(final, ignore_errors=True)
        os.replace(partial, final)
