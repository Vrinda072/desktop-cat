"""Turns the white-and-ginger cat into a white-and-grey cat with pink ears and brown eyes.

Reads Resources/Animations (the original art) and writes windows/assets/Animations.

- Ginger patches and tail become a cool silver grey of about the same brightness.
- The inside of her ears (a dull mauve in the original) becomes a clear pink.
- Her eyes get a brown iris under a dark pupil (the original eyes are black, teal or gold).
- White fur, outlines, the nose and mouth stay as they are.

The ears share their mauve with the darker shading along the tail, and the pupils share their
black with the outline, so both are found by shape: ears are solid patches of mauve, tail
shading is thin lines; pupils are solid blobs of black, the outline is 1-2 pixels wide.

    python windows/tools/recolor_grey.py
"""
import colorsys
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "Resources" / "Animations"
TARGET = REPO / "windows" / "assets" / "Animations"

# Grey for the patches: a little darker than the ginger it replaces, so the pattern stands out on
# the white fur, and a little blue, so she reads as silver rather than washed out.
DARKEN = 0.82
COOL_TINT = (-6, 0, 10)

# Pinks for the inside of her ears, from the shadow to the lightest fur.
EAR_PINKS = [(196, 92, 124), (228, 124, 152), (244, 167, 185), (250, 200, 210)]
# Browns for her eyes: pupil, iris, and the light catching the bottom of the iris.
PUPIL = (38, 22, 14)
IRIS = (120, 72, 36)
IRIS_LIGHT = (160, 104, 56)


def hsv(rgb):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return h * 360, s, v


def luminance(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def grey(rgb):
    lum = luminance(rgb) * DARKEN
    return tuple(max(0, min(255, round(lum + t))) for t in COOL_TINT)


def ramp(colors, t):
    """A colour along `colors` for t in 0...1."""
    t = min(max(t, 0), 1) * (len(colors) - 1)
    i = min(int(t), len(colors) - 2)
    f = t - i
    return tuple(round(a + (b - a) * f) for a, b in zip(colors[i], colors[i + 1]))


def is_ginger(h, s, v):
    return 0 <= h <= 45 and s >= 0.07


def is_mauve(h, s, v):
    """The colour of the inside of her ears (and, sadly, some tail shading)."""
    return h <= 15 and s >= 0.18 and v > 0.45


def is_iris(h, s, v):
    """The teal and gold irises some poses have."""
    return (150 <= h <= 200 and s > 0.3) or (30 <= h <= 55 and s > 0.5 and v < 0.6)


def components(mask: set, link: int = 1):
    """Groups of pixels in `mask` that touch (within `link` pixels)."""
    seen, groups = set(), []
    for start in mask:
        if start in seen:
            continue
        group, todo = [], deque([start])
        seen.add(start)
        while todo:
            x, y = todo.popleft()
            group.append((x, y))
            for dx in range(-link, link + 1):
                for dy in range(-link, link + 1):
                    n = (x + dx, y + dy)
                    if n in mask and n not in seen:
                        seen.add(n)
                        todo.append(n)
        groups.append(group)
    return groups


def mask_image(size, pixels):
    m = Image.new("L", size, 0)
    for p in pixels:
        m.putpixel(p, 255)
    return m


def find_ears(size, mauve: set) -> set:
    # Dense patches of mauve, grown back out over the mauve around them, keeping only patches big
    # enough to be an ear.
    density = mask_image(size, mauve).filter(ImageFilter.BoxBlur(4)).load()
    core = {p for p in mauve if density[p] >= 110}
    near = mask_image(size, core).filter(ImageFilter.MaxFilter(7)).load()
    grown = {p for p in mauve if near[p]}
    # Ears are the highest patches; the same mauve lower down is where the tail meets her body.
    groups = [g for g in components(grown, link=2) if len(g) >= 30]
    if not groups:
        return set()
    highest = min(min(y for _, y in g) for g in groups)
    ears = set()
    for group in groups:
        if min(y for _, y in group) <= highest + 60:
            ears.update(group)
    return ears


def find_pupils(size, dark: set) -> list:
    # Solid blobs of black: what survives shrinking the dark pixels by one pixel all round, grown
    # back over the dark pixels next to it.
    m = mask_image(size, dark)
    core = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MinFilter(3)).load()
    seeds = {p for p in dark if core[p]}
    near = mask_image(size, seeds).filter(ImageFilter.MaxFilter(7)).load()
    blobs = []
    for group in components({p for p in dark if near[p]}):
        ys = [y for _, y in group]
        xs = [x for x, _ in group]
        w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        # An eye is a compact blob; a thick corner of outline is long and thin.
        if 12 <= len(group) <= 250 and w <= 24 and h <= 24 and len(group) >= 0.35 * w * h:
            blobs.append(group)
    return blobs


def find_nose(pupils: list, colors: dict) -> set:
    """Her nose and its little shadow: the warm pixels just below and between her two eyes."""
    if len(pupils) < 2:
        return set()
    centers = sorted((sum(x for x, _ in b) / len(b), sum(y for _, y in b) / len(b), max(y for _, y in b))
                     for b in pupils)
    (lx, ly, lb), (rx, ry, rb) = centers[0], centers[-1]
    if not 8 <= rx - lx <= 70 or abs(ly - ry) > 15:
        return set()   # not a pair of eyes side by side
    top, bottom = max(lb, rb) + 1, max(lb, rb) + 22
    return {(x, y) for (x, y), (h, s, v) in colors.items()
            if lx + 3 <= x <= rx - 3 and top <= y <= bottom and h <= 45 and s >= 0.15 and v > 0.45}


def recolor(src: Path, dst: Path):
    im = Image.open(src).convert("RGBA")
    px = im.load()
    w, h = im.size
    colors = {}
    mauve, dark = set(), set()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if not a:
                continue
            hsv_ = hsv((r, g, b))
            colors[(x, y)] = hsv_
            if is_mauve(*hsv_):
                mauve.add((x, y))
            if hsv_[2] < 0.12:
                dark.add((x, y))

    ears = find_ears(im.size, mauve)
    pupils = find_pupils(im.size, dark)
    nose = find_nose(pupils, colors)
    eyes = {}
    for blob in pupils:
        top = min(y for _, y in blob)
        bottom = max(y for _, y in blob)
        for x, y in blob:
            # Dark at the top, brown lower down, a lighter brown at the very bottom.
            t = (y - top) / max(bottom - top, 1)
            eyes[(x, y)] = PUPIL if t < 0.45 else IRIS if t < 0.85 else IRIS_LIGHT

    # Boxes around her ears and eyes, grown to take in the rest of her face. Elsewhere the same
    # reddish colour is just shading where the tail meets her body.
    face = [(min(x for x, _ in g) - 45, min(y for _, y in g) - 20, max(x for x, _ in g) + 45, max(y for _, y in g) + 60)
            for g in components(ears, link=3) + pupils]

    def near_face(x, y):
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in face)

    for (x, y), (hue, s, v) in colors.items():
        r, g, b, a = px[x, y]
        if (x, y) in eyes:
            new = eyes[(x, y)]
        elif is_iris(hue, s, v) and near_face(x, y):
            new = ramp([PUPIL, IRIS, IRIS_LIGHT], v / 0.9)
        elif (x, y) in ears or (x, y) in nose:
            new = ramp(EAR_PINKS, (luminance((r, g, b)) - 110) / 120)
        elif hue <= 15 and s >= 0.33 and (x, y) not in mauve and near_face(x, y):
            continue   # the nose and mouth
        elif is_ginger(hue, s, v):
            new = grey((r, g, b))
        else:
            continue
        px[x, y] = (*new, a)

    dst.parent.mkdir(parents=True, exist_ok=True)
    # Back to a small palette PNG like the originals; transparency is all-or-nothing in this art.
    im.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(dst, optimize=True)


def main():
    frames = sorted(SOURCE.glob("*/frame_*.png"))
    if not frames:
        sys.exit(f"No frames found in {SOURCE}")
    for i, src in enumerate(frames, 1):
        recolor(src, TARGET / src.parent.name / src.name)
        if i % 50 == 0:
            print(f"{i}/{len(frames)}")
    print(f"Recoloured {len(frames)} frames into {TARGET}")


if __name__ == "__main__":
    main()
