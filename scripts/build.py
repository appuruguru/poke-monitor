"""Build dist/Poke-Monitor.exe (single file, no console) with PyInstaller.

    pip install -r requirements.txt -r requirements-dev.txt
    python scripts/build.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from poke_monitor.config import APP_ID  # noqa: E402
from poke_monitor.icon import make_icon  # noqa: E402


def main():
    build_dir = os.path.join(ROOT, "build")
    os.makedirs(build_dir, exist_ok=True)

    ico = os.path.join(build_dir, "icon.ico")
    make_icon(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--noconsole",
        "--name", APP_ID,
        "--icon", ico,
        "--hidden-import", "pystray._win32",  # pystray picks its backend dynamically, which PyInstaller can't see
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(build_dir, "pyinstaller"),
        "--specpath", build_dir,
        os.path.join(ROOT, "run.py"),
    ])
    print(f"\nBuilt {os.path.join(ROOT, 'dist', APP_ID + '.exe')}")


if __name__ == "__main__":
    main()
