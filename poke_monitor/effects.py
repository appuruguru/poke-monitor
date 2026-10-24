"""Occasional special effects that show off a pet's powers: electric cheek
sparks, whipping vines and a water squirt. (The fire pet's tail flame is
already animated in its sprite.)

An effect is stepped once per tick with the pet's current frame and returns
drawing primitives in canvas coordinates:

    ("line", [(x, y), ...], color, width)
    ("oval", (x0, y0, x1, y1), color, 0)
    ("poly", [(x, y), ...], fill_color, outline_color)

Keeping them as plain data means they can be drawn on a Tk canvas by the pet
(and rendered with PIL for offline checks).
"""
import math
import random
from dataclasses import dataclass

from PIL import Image

from .config import TICK_MS


@dataclass
class Ctx:
    image: Image.Image  # RGBA frame currently on screen
    origin: tuple[int, int]  # canvas position of that image's top-left corner
    facing: int  # -1: looking left, +1: looking right


def _clusters(img: Image.Image, pred):
    """Connected blobs of opaque pixels matching pred(r, g, b): [(size, cx, cy)]."""
    px = img.load()
    w, h = img.size
    seen = set()
    out = []
    for y in range(h):
        for x in range(w):
            if (x, y) in seen:
                continue
            r, g, b, a = px[x, y]
            if a < 128 or not pred(r, g, b):
                continue
            stack = [(x, y)]
            seen.add((x, y))
            pts = []
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen:
                            r2, g2, b2, a2 = px[nx, ny]
                            if a2 >= 128 and pred(r2, g2, b2):
                                seen.add((nx, ny))
                                stack.append((nx, ny))
            n = len(pts)
            out.append((n, sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n))
    return out


class Effect:
    duration_ms = 1200

    def __init__(self):
        self.t = 0.0
        self.done = False

    def step(self, dt_ms: float, ctx: Ctx) -> list:
        self.t += dt_ms
        if self.t >= self.duration_ms:
            self.done = True
            return []
        return self._prims(dt_ms, ctx)

    def _prims(self, dt_ms: float, ctx: Ctx) -> list:
        raise NotImplementedError


class Sparks(Effect):
    """Little flickering lightning bolts jumping off Pikachu's red cheeks."""

    duration_ms = 1300
    # A lightning-bolt outline in a unit box (y down); its point is at the bottom.
    _BOLT = [(0.55, 0.0), (0.10, 0.58), (0.42, 0.58), (0.22, 1.0), (0.90, 0.36), (0.56, 0.36), (0.84, 0.0)]

    def __init__(self):
        super().__init__()
        self._cheek_cache = {}

    @staticmethod
    def _is_cheek_red(r, g, b):
        return r >= 170 and g <= 110 and b <= 110 and r - g >= 80

    def _cheeks(self, img):
        cached = self._cheek_cache.get(id(img))
        if cached is None:
            found = sorted(_clusters(img, self._is_cheek_red), key=lambda c: c[1])
            if not found:
                chosen = []
            elif len(found) == 1 or found[-1][1] - found[0][1] < 0.25 * img.width:
                chosen = [max(found, key=lambda c: c[0])]
            else:
                chosen = [found[0], found[-1]]  # outermost two; anything between is the mouth
            mid = img.width / 2
            px = img.load()
            cached = []
            for _n, x, y in chosen:
                side = -1 if x < mid else 1
                # Start the bolt where the sprite's edge is, just outside the cheek.
                edge = x
                for _ in range(max(1, round(0.2 * max(img.size)))):
                    nxt = edge + side
                    if not 0 <= int(nxt) < img.width or px[int(nxt), min(int(y), img.height - 1)][3] < 128:
                        break
                    edge = nxt
                cached.append((edge, y, side))
            self._cheek_cache[id(img)] = cached
        return cached

    def _prims(self, _dt_ms, ctx):
        flash = int(self.t // 60)
        if flash % 3 == 2:  # blink off every third flash
            return []
        u = max(ctx.image.size)
        rng = random.Random(flash)
        ox, oy = ctx.origin
        size = 0.30 * u
        prims = []
        for x, y, side in self._cheeks(ctx.image):
            # The bolt's point aims up and away from the face; it flickers between orientations.
            aim = math.radians(rng.uniform(40, 75))
            tip_x, tip_y = side * math.cos(aim), -math.sin(aim)
            rot = math.atan2(tip_y, tip_x) - math.pi / 2  # from "point down" to "point at tip"
            cos_r, sin_r = math.cos(rot), math.sin(rot)
            cx = ox + x + tip_x * (0.5 * size + 0.02 * u)
            cy = oy + y + tip_y * (0.5 * size + 0.02 * u)
            pts = []
            for px, py in self._BOLT:
                dx, dy = (px - 0.5) * size, (py - 0.5) * size
                pts.append((cx + dx * cos_r - dy * sin_r, cy + dx * sin_r + dy * cos_r))
            prims.append(("poly", pts, "#ffee3a", "#2b1c00"))
        return prims


class Vines(Effect):
    """Two vines whip out of Bulbasaur's bulb, sway, then pull back in."""

    duration_ms = 1700
    _SEGMENTS = 8

    def __init__(self):
        super().__init__()
        self._anchor_cache = {}

    def _anchor(self, img):
        cached = self._anchor_cache.get(id(img))
        if cached is None:
            left, top, right, bottom = img.getchannel("A").getbbox()
            band = top + max(2, 0.12 * (bottom - top))
            px = img.load()
            xs = [x for y in range(top, int(band) + 1) for x in range(left, right) if px[x, y][3] >= 128]
            cached = (sum(xs) / len(xs) if xs else (left + right) / 2, top + 0.2 * (bottom - top))
            self._anchor_cache[id(img)] = cached
        return cached

    def _prims(self, _dt_ms, ctx):
        u = max(ctx.image.size)
        grow = min(1.0, self.t / (0.25 * self.duration_ms))
        retract = min(1.0, (self.duration_ms - self.t) / (0.25 * self.duration_ms))
        progress = min(grow, retract)
        ax, ay = self._anchor(ctx.image)
        ax, ay = ax + ctx.origin[0], ay + ctx.origin[1]
        width = max(2, round(0.07 * u))
        seg_len = 0.55 * u * progress / self._SEGMENTS
        prims = []
        for side, phase in ((-1, 0.0), (1, 1.9)):
            x, y = ax + side * 0.06 * u, ay
            pts = [(x, y)]
            for i in range(1, self._SEGMENTS + 1):
                angle = -math.pi / 2 + side * (0.35 + 0.10 * i)  # up, then curling outward and down
                angle += math.sin(self.t / 150 + i * 0.7 + phase) * 0.45 * (i / self._SEGMENTS)
                x += math.cos(angle) * seg_len
                y += math.sin(angle) * seg_len
                pts.append((x, y))
            prims.append(("line", pts, "#1d5a2a", width + 2))
            prims.append(("line", pts, "#4cbd5a", width))
            lx, ly = pts[-1]
            leaf = max(2, 0.07 * u)
            prims.append(("oval", (lx - leaf, ly - leaf, lx + leaf, ly + leaf), "#8be58f", 0))
        return prims


class Squirt(Effect):
    """Squirtle spits little arcs of water out of its mouth."""

    duration_ms = 1500
    _EMIT_FRACTION = 0.6

    def __init__(self):
        super().__init__()
        self._drops = []  # [x, y, vx, vy, life]
        self._rng = random.Random()

    @staticmethod
    def _mouth(img, facing):
        left, top, right, bottom = img.getchannel("A").getbbox()
        w, h = right - left, bottom - top
        return (left + 0.06 * w if facing < 0 else right - 0.06 * w), top + 0.42 * h

    def _prims(self, dt_ms, ctx):
        u = max(ctx.image.size)
        k = u / 38.0
        for _ in range(max(1, round(dt_ms / TICK_MS))):
            for d in self._drops:
                d[0] += d[2]
                d[1] += d[3]
                d[3] += 0.18 * k
                d[4] -= 1
            self._drops = [d for d in self._drops if d[4] > 0]
        if self.t < self._EMIT_FRACTION * self.duration_ms:
            mx, my = self._mouth(ctx.image, ctx.facing)
            for _ in range(1 if self._rng.random() < 0.6 else 2):
                self._drops.append([
                    ctx.origin[0] + mx, ctx.origin[1] + my,
                    ctx.facing * self._rng.uniform(1.4, 2.3) * k, -self._rng.uniform(0.7, 1.5) * k, 14,
                ])
        r = max(1.5, 0.045 * u)
        return [("oval", (x - r, y - r, x + r, y + r), "#4fb4ff", 0) for x, y, *_ in self._drops]


EFFECTS = {"pikachu": Sparks, "bulbasaur": Vines, "squirtle": Squirt}
