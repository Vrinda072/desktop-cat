"""Makes windows/assets/cat.ico (the .exe and window icon) from the grey cat's face.

    python windows/tools/make_icon.py
"""
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def main():
    frame = Image.open(ASSETS / "Animations" / "awake" / "frame_020.png").convert("RGBA")
    # Her head, squared up, with a little room around it.
    face = frame.crop((206, 2, 352, 148))
    canvas = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    canvas.alpha_composite(face, (7, 7))
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    canvas.resize((256, 256), Image.LANCZOS).save(ASSETS / "cat.ico", sizes=sizes)
    print(f"Wrote {ASSETS / 'cat.ico'}")


if __name__ == "__main__":
    main()
