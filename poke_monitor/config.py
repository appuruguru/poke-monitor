"""Static configuration for Poke Monitor."""
import os

APP_NAME = "Poke Monitor"
APP_ID = "Poke-Monitor"  # exe name, data folder, startup registry value

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Sprites are downloaded on first launch (see assets.py) rather than shipped,
# and live in a per-user folder so the packaged exe and a source checkout agree.
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_ID)
ASSETS_DIR = os.path.join(DATA_DIR, "assets")
# User-supplied animations (e.g. custom/pikachu/run.gif) that override the
# downloaded walking art. Kept apart from ASSETS_DIR so a re-download never touches them.
CUSTOM_DIR = os.path.join(DATA_DIR, "custom")

# National dex number by name; drives which sprites get downloaded and the tray menu.
PETS = {
    "pikachu": 25,
    "charmander": 4,
    "bulbasaur": 1,
    "squirtle": 7,
}

SPRITE_SCALE = 0.75  # the source sprites are ~40-56px; this renders them at roughly a quarter of that

# Transparent color key for the borderless window background. Chosen to be a
# color that won't appear in the sprites themselves.
TRANSPARENT_KEY = "#ab23ff"

TICK_MS = 40  # ~25 fps AI/physics tick
STAND_FRAME_MS = 45  # time between frames of the standing animation (~20-25fps loop)

EFFECT_COOLDOWN_MIN_MS, EFFECT_COOLDOWN_MAX_MS = 5000, 12000  # gap between special effects

WALK_SPEED = 2.0  # px per tick
RUN_SPEED = 5.0
CLIMB_SPEED = 2.5
GRAVITY = 0.6
TERMINAL_VELOCITY = 14.0
MAX_CLIMB_PX = 220

# Behavior timers, in ticks (TICK_MS each)
IDLE_MIN, IDLE_MAX = 25, 150
WALK_MIN, WALK_MAX = 50, 250
SLEEP_MIN, SLEEP_MAX = 300, 900
SLEEP_CHANCE = 0.05
RUN_CHANCE = 0.15
CLIMB_CHANCE = 0.3
FALL_OFF_CHANCE = 0.15

PET_SIZE_FALLBACK = 48  # used before a sprite is loaded
