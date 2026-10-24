"""A single desktop pet: a borderless always-on-top Tk window with a small
state machine (idle / walk / sleep / fall / climb / drag) driven by the
app's shared tick loop.
"""
import random
import tkinter as tk

from . import effects, sprites, winutils
from .config import (
    CLIMB_CHANCE,
    CLIMB_SPEED,
    EFFECT_COOLDOWN_MAX_MS,
    EFFECT_COOLDOWN_MIN_MS,
    FALL_OFF_CHANCE,
    GRAVITY,
    IDLE_MAX,
    IDLE_MIN,
    MAX_CLIMB_PX,
    RUN_CHANCE,
    RUN_SPEED,
    SLEEP_CHANCE,
    SLEEP_MAX,
    SLEEP_MIN,
    TERMINAL_VELOCITY,
    TRANSPARENT_KEY,
    WALK_MAX,
    WALK_MIN,
    WALK_SPEED,
)
from .settings import settings

IDLE, WALK, SLEEP, FALL, CLIMB, DRAG = "idle", "walk", "sleep", "fall", "climb", "drag"

_LEADING_MARGIN = 3


class Pet:
    def __init__(self, name: str, root: tk.Tk, on_remove=None):
        self.name = name
        self.sprite = sprites.get_sprite_set(name, settings.scale)
        self._on_remove = on_remove

        # (self.x, self.y) is the top-left of the sprite's standing-size box and
        # self.width/height its size; the window extends `pad` beyond that on
        # every side, leaving room for effects (sparks, vines, water).
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg=TRANSPARENT_KEY)
        self.win.wm_attributes("-transparentcolor", TRANSPARENT_KEY)

        self.canvas = tk.Canvas(self.win, bg=TRANSPARENT_KEY, highlightthickness=0)
        self.canvas.pack()
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.z_item = self.canvas.create_text(
            0, 0, text="Z z", fill="white", anchor="sw", font=("Segoe UI", 9, "bold"), state="hidden"
        )
        self._layout()

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", self._on_right_click)

        work_left, _work_top, work_right, _work_bottom = winutils.get_work_area()
        virtual_top = winutils.get_virtual_screen()[1]
        # Spawn above the screen and fall in, eSheep-style, so it can land on
        # whatever window (or the ground) happens to be below it.
        self.x = float(random.randint(work_left, max(work_left, work_right - self.width)))
        self.y = float(virtual_top - self.height)
        self.current_surface = None

        self.facing_dir = random.choice([-1, 1])
        self.speed = WALK_SPEED * settings.speed_multiplier
        self.vy = 0.0
        self.state = FALL
        self.state_timer = 0
        self.anim_index = 0
        self._anim_accum_ms = 0.0
        self._anim_key_now = "stand"
        self.effect = None
        self._effect_cooldown_ms = random.uniform(EFFECT_COOLDOWN_MIN_MS, EFFECT_COOLDOWN_MAX_MS)
        self.climb_target_hwnd = None
        self._drag_offset = (0, 0)
        self.alive = True

        self._render()

    @property
    def hwnd(self):
        return self.win.winfo_id()

    def _layout(self):
        self.width, self.height = self.sprite.width, self.sprite.height
        self.pad = round(0.9 * max(self.width, self.height))
        size_w, size_h = self.width + 2 * self.pad, self.height + 2 * self.pad
        self.win.geometry(f"{size_w}x{size_h}")
        self.canvas.config(width=size_w, height=size_h)
        self.canvas.coords(self.z_item, self.pad + self.width * 0.62, self.pad + self.height * 0.18)

    def rescale(self):
        """Pick up a new settings.scale in place, keeping the pet's feet and centre where they are."""
        feet_y = self.y + self.height
        center_x = self.x + self.width / 2
        self.sprite = sprites.get_sprite_set(self.name, settings.scale)
        self._layout()
        self.x = center_x - self.width / 2
        self.y = feet_y - self.height
        self.anim_index = 0
        self._stop_effect()
        self._render()

    def destroy(self):
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ tick

    def tick(self, surfaces, dt_ms):
        if not self.alive:
            return
        self._advance_animation(dt_ms)
        if self.state == DRAG:
            self._render(dt_ms)
            return
        if self.state == FALL:
            self._update_fall(surfaces)
        elif self.state == CLIMB:
            self._update_climb(surfaces)
        else:
            self._update_grounded(surfaces)
        self._render(dt_ms)

    def _anim_key(self):
        """Which animation to show: walk/sleep art when it exists, else the standing one."""
        if self.state == SLEEP and self.sprite.has("sleep"):
            return "sleep"
        if self.state == WALK:
            key = "walk_left" if self.facing_dir < 0 else "walk_right"
            if self.sprite.has(key):
                return key
        return "stand"

    def _advance_animation(self, dt_ms):
        key = self._anim_key()
        if key != self._anim_key_now:
            self._anim_key_now = key
            self.anim_index = 0
            self._anim_accum_ms = 0.0
        if self.state == SLEEP and key == "stand":
            self.anim_index = 0  # no sleeping art for this pet: hold the first frame
            return
        anim = self.sprite.anims[key]
        rate = 1.0
        if key.startswith("walk_"):  # step faster when running
            rate = min(2.5, max(1.0, self.speed / (WALK_SPEED * settings.speed_multiplier)))
        self._anim_accum_ms += dt_ms * rate
        while self._anim_accum_ms >= anim.durations[self.anim_index % anim.count]:
            self._anim_accum_ms -= anim.durations[self.anim_index % anim.count]
            self.anim_index = (self.anim_index + 1) % anim.count

    # --------------------------------------------------------------- states

    def _enter_state(self, state):
        self.state = state
        if state == IDLE:
            self.state_timer = random.randint(IDLE_MIN, IDLE_MAX)
        elif state == WALK:
            self.state_timer = random.randint(WALK_MIN, WALK_MAX)
        elif state == SLEEP:
            self.state_timer = random.randint(SLEEP_MIN, SLEEP_MAX)

    def _find_current_surface(self, surfaces):
        target_hwnd = self.current_surface.hwnd if self.current_surface else None
        return next((s for s in surfaces if s.hwnd == target_hwnd), None)

    def _update_grounded(self, surfaces):
        match = self._find_current_surface(surfaces)
        vtop = winutils.get_virtual_screen()[1]
        if match is None or match.y - self.height < vtop:
            # Surface vanished, got covered, or moved (e.g. maximized) so that
            # standing on it would put us out of view: drop off it.
            self.state = FALL
            self.vy = 0.0
            return
        self.current_surface = match
        self.y = float(match.y - self.height)
        if self.x + self.width < match.left or self.x > match.right:
            self.state = FALL
            self.vy = 0.0
            return

        self.state_timer -= 1
        if self.state_timer <= 0:
            self._choose_next_grounded_state()
            return

        if self.state == WALK:
            self._walk_step(surfaces, match)

    def _choose_next_grounded_state(self):
        if settings.sleep_enabled and random.random() < SLEEP_CHANCE:
            self._enter_state(SLEEP)
            return
        base_speed = RUN_SPEED if random.random() < RUN_CHANCE else WALK_SPEED
        self.speed = base_speed * settings.speed_multiplier
        if random.random() < 0.5:
            self.facing_dir *= -1
        self._enter_state(WALK if random.random() < 0.7 else IDLE)

    def _leading_x(self, direction):
        return self.x + self.width if direction > 0 else self.x

    def _find_wall(self, surfaces, direction):
        if not settings.climbing_enabled:
            return None
        cur = self._leading_x(direction)
        nxt = cur + direction * self.speed
        lo, hi = (cur, nxt) if direction > 0 else (nxt, cur)
        vtop = winutils.get_virtual_screen()[1]
        best = None
        for s in surfaces:
            if s.hwnd == self.current_surface.hwnd:
                continue
            if s.y >= self.y - 4:
                continue
            if self.y - s.y > MAX_CLIMB_PX:
                continue
            if s.y - self.height < vtop:  # no room to stand fully in view up there
                continue
            edge_x = s.left if direction > 0 else s.right
            if lo - _LEADING_MARGIN <= edge_x <= hi + _LEADING_MARGIN:
                if best is None or s.y < best.y:
                    best = s
        return best

    def _walk_step(self, surfaces, surface):
        wall = self._find_wall(surfaces, self.facing_dir)
        if wall is not None:
            if random.random() < CLIMB_CHANCE:
                self._start_climb(wall)
            else:
                self.facing_dir *= -1
            return

        next_leading = self._leading_x(self.facing_dir) + self.facing_dir * self.speed
        if next_leading < surface.left or next_leading > surface.right:
            if surface.hwnd is None:
                # Walked off the side of the screen along the ground: come
                # back in from the opposite side, still heading the same way.
                if self.facing_dir > 0:
                    self.x = float(surface.left - self.width + 1)
                else:
                    self.x = float(surface.right - 1)
            elif random.random() < FALL_OFF_CHANCE:
                self.state = FALL
                self.vy = 0.0
            else:
                self.facing_dir *= -1
            return

        self.x += self.facing_dir * self.speed

    def _start_climb(self, target):
        edge_x = target.left if self.facing_dir > 0 else target.right
        self.x = edge_x - self.width if self.facing_dir > 0 else float(edge_x)
        self.climb_target_hwnd = target.hwnd
        self.state = CLIMB

    def _update_climb(self, surfaces):
        match = next((s for s in surfaces if s.hwnd == self.climb_target_hwnd), None)
        if match is None:
            self.state = FALL
            self.vy = 0.0
            return
        self.y -= CLIMB_SPEED * settings.speed_multiplier
        target_y = match.y - self.height
        if self.y <= target_y:
            self.y = float(target_y)
            self.current_surface = match
            self._enter_state(WALK)

    def _update_fall(self, surfaces):
        prev_feet = self.y + self.height
        self.vy = min(self.vy + GRAVITY, TERMINAL_VELOCITY)
        self.y += self.vy
        feet_y = self.y + self.height
        center_x = self.x + self.width / 2

        _vleft, vtop, _vright, vbottom = winutils.get_virtual_screen()
        candidates = [
            s for s in surfaces
            if s.left <= center_x <= s.right
            and prev_feet <= s.y <= feet_y
            and s.y - self.height >= vtop  # must leave room to stand fully in view
        ]
        if candidates:
            landing = min(candidates, key=lambda s: s.y)
            self.y = float(landing.y - self.height)
            self.vy = 0.0
            self.current_surface = landing
            self._enter_state(IDLE)
            return

        if feet_y > vbottom:
            ground = min(surfaces, key=lambda s: 0 if s.hwnd is None else 1)
            self.y = float(ground.y - self.height)
            self.vy = 0.0
            self.current_surface = ground
            self._enter_state(IDLE)

    # ---------------------------------------------------------------- mouse

    def _on_press(self, event):
        self.state = DRAG
        self._drag_offset = (event.x, event.y)
        self.win.lift()

    def _on_drag(self, event):
        win_x = self.win.winfo_x() + event.x - self._drag_offset[0]
        win_y = self.win.winfo_y() + event.y - self._drag_offset[1]
        self.x, self.y = float(win_x + self.pad), float(win_y + self.pad)
        self.win.geometry(f"+{win_x}+{win_y}")

    def _on_release(self, _event):
        self.vy = 0.0
        self.state = FALL

    def _on_right_click(self, event):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label=f"Remove {self.name.capitalize()}", command=self._request_remove)
        menu.add_separator()
        menu.add_command(label="Cancel")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _request_remove(self):
        if self._on_remove:
            self._on_remove(self.name)

    # -------------------------------------------------------------- render

    def _render(self, dt_ms=0):
        key = self._anim_key()
        mirror = key == "stand" and self.facing_dir > 0  # the standing sprites face left
        rotate = 0
        if self.state == CLIMB:
            # PIL rotates counter-clockwise for positive angles.
            rotate = 90 if self.facing_dir > 0 else -90
        img = self.sprite.get_image(key, self.anim_index, mirror, rotate)
        self.canvas.itemconfig(self.image_item, image=self.sprite.get_photo(key, self.anim_index, mirror, rotate))

        # Feet stay on the box's bottom edge (centre for the rotated climbing pose).
        origin_x = round(self.pad + self.width / 2 - img.width / 2)
        if rotate:
            origin_y = round(self.pad + self.height / 2 - img.height / 2)
        else:
            origin_y = round(self.pad + self.height - img.height)
        self.canvas.coords(self.image_item, origin_x, origin_y)

        self.win.geometry(f"+{int(self.x) - self.pad}+{int(self.y) - self.pad}")
        self.canvas.itemconfig(self.z_item, state="normal" if self.state == SLEEP else "hidden")
        self._update_effect(img, (origin_x, origin_y), dt_ms)

    # ------------------------------------------------------------- effects

    def _stop_effect(self):
        self.effect = None
        self.canvas.delete("fx")
        self._effect_cooldown_ms = random.uniform(EFFECT_COOLDOWN_MIN_MS, EFFECT_COOLDOWN_MAX_MS)

    def _update_effect(self, img, origin, dt_ms):
        can_play = (
            settings.effects_enabled and self.state in (IDLE, WALK) and self.name in effects.EFFECTS
        )
        if self.effect is None:
            if can_play:
                self._effect_cooldown_ms -= dt_ms
                if self._effect_cooldown_ms <= 0:
                    self.effect = effects.EFFECTS[self.name]()
            return
        if not can_play:
            self._stop_effect()
            return

        prims = self.effect.step(dt_ms, effects.Ctx(img, origin, self.facing_dir))
        self.canvas.delete("fx")
        for kind, data, color, extra in prims:  # extra: line width, or a polygon's outline colour
            if kind == "line":
                self.canvas.create_line(
                    *[c for point in data for c in point], fill=color, width=extra,
                    capstyle="round", joinstyle="round", tags="fx",
                )
            elif kind == "poly":
                self.canvas.create_polygon(*[c for point in data for c in point], fill=color, outline=extra, tags="fx")
            else:
                self.canvas.create_oval(*data, fill=color, outline="", tags="fx")
        if self.effect.done:
            self._stop_effect()
