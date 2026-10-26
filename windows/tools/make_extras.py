"""Makes the animations the Windows cat has on top of the original art:

- `blanket`: her sleeping frames with a black-and-white plaid blanket tucked over her (Sleep Mode).
- `paperPlay`, `paperChase`, `paperEnd`: she finds a crumpled paper ball, bats it about, chases
  it across the screen, and sits back pleased with herself on the other side.

They're drawn onto the grey frames in windows/assets/Animations, so run recolor_grey.py first:

    python windows/tools/recolor_grey.py
    python windows/tools/make_extras.py
"""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ANIMATIONS = Path(__file__).resolve().parents[1] / "assets" / "Animations"
GROUND = 350          # her paws rest on this row in every frame
PX = 3                # one "art pixel" of the drawings below, in frame pixels
INK = (43, 39, 51, 255)


def frame(folder, i):
    return Image.open(ANIMATIONS / folder / f"frame_{i:03d}.png").convert("RGBA")


def save(im, folder, i):
    path = ANIMATIONS / folder / f"frame_{i:03d}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    im.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(path, optimize=True)


# MARK: - Blanket

# Mostly black, so it stands right out against her white fur and grey patches, with crisp white
# checks; the hem is charcoal with white stitches so its edge shows against her white face.
PLAID_BASE = (24, 23, 29)
PLAID_BAND = (104, 102, 114)
PLAID_CROSS = (160, 158, 170)
PLAID_LINE = (245, 245, 248)
HEM = (52, 50, 60)
STITCH = (240, 240, 244)
REPEAT = 14   # art pixels


def plaid(x, y):
    """A black tartan: wide charcoal bands both ways (lighter where they cross), each with a thin
    white line down its middle."""
    cx, cy = (x // PX) % REPEAT, (y // PX) % REPEAT
    bx, by = cx < 7, cy < 7
    if cx == 3 or cy == 3:
        return PLAID_LINE
    if bx and by:
        return PLAID_CROSS
    if bx or by:
        return PLAID_BAND
    return PLAID_BASE


def bezier(a, b, c, t):
    return ((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * b[0] + t * t * c[0],
            (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * b[1] + t * t * c[1])


def blanket_mask(cat: Image.Image) -> Image.Image:
    """Her body, a little puffed out, from just behind her head to her tail, and down to the floor."""
    w, h = cat.size
    body = cat.getchannel("A").point(lambda a: 255 if a else 0).filter(ImageFilter.MaxFilter(7))
    # Leave her head and face out. The edge starts behind her ear, bows out round her cheek and
    # then sweeps under her chin, so the blanket is pulled up snug over her front paws.
    edge = [bezier((206, 100), (262, 250), (96, 362), t / 40) for t in range(41)]
    keep = Image.new("L", (w, h), 0)
    ImageDraw.Draw(keep).polygon(edge + [(w, h), (w, 0), (206, 0)], fill=255)
    mask = ImageChops.multiply(body, keep)
    # Let it pool on the floor a bit, like a real blanket.
    ImageDraw.Draw(mask).rectangle([0, GROUND - 2, w, GROUND + 2], fill=0)
    floor = ImageChops.multiply(body.filter(ImageFilter.MaxFilter(9)), keep)
    floor = floor.crop((0, GROUND - 14, w, GROUND + 3))
    mask.paste(floor, (0, GROUND - 14), floor)
    # Snap to the art-pixel grid so it looks drawn, not cut out.
    small = mask.resize((w // PX, h // PX), Image.BOX).point(lambda a: 255 if a > 110 else 0)
    return small.resize((w // PX * PX, h // PX * PX), Image.NEAREST).crop((0, 0, w, h))


def draw_blanket(cat: Image.Image) -> Image.Image:
    w, h = cat.size
    mask = blanket_mask(cat)
    m = mask.load()
    inside = lambda x, y: 0 <= x < w and 0 <= y < h and m[x, y]
    out = cat.copy()
    px = out.load()
    top = {}
    for x in range(w):
        for y in range(h):
            if m[x, y]:
                top.setdefault(x, y)
    for y in range(h):
        for x in range(w):
            if not m[x, y]:
                continue
            edge = not all(inside(x + dx, y + dy) for dx, dy in ((-PX, 0), (PX, 0), (0, -PX), (0, PX)))
            if edge:
                px[x, y] = INK
                continue
            near_left = not inside(x - 3 * PX, y)
            if near_left:
                # The hem, with a dashed row of white stitches down its middle.
                mid = not inside(x - 2 * PX, y) and inside(x - PX, y)
                r, g, b = STITCH if mid and (y // (2 * PX)) % 2 == 0 else HEM
            else:
                r, g, b = plaid(x, y)
            # Light on top, a little shadow underneath and on the far side, so it looks soft.
            depth = (y - top.get(x, y)) / 120
            shade = 1.0 - 0.18 * min(max(depth, 0), 1)
            if not inside(x + 4 * PX, y) or not inside(x, y + 3 * PX):
                shade *= 0.86
            px[x, y] = (min(255, round(r * shade)), min(255, round(g * shade)), min(255, round(b * shade)), 255)
    return out


def make_blanket():
    count = len(list((ANIMATIONS / "sleeping").glob("frame_*.png")))
    for i in range(count):
        save(draw_blanket(frame("sleeping", i)), "blanket", i)
    print(f"blanket: {count} frames")


# MARK: - Paper ball

# 10×10 art pixels. o outline, P paper, p light crease, c dark crease, s shadow.
PAPER = [
    "...oooo...",
    "..oPPpPo..",
    ".oPpPPcPo.",
    "oPPcPpPPso",
    "oPpPPPcPso",
    "ocPPpPPpso",
    "oPPPcPPsso",
    ".oPpPPsso.",
    "..osssso..",
    "...oooo...",
]
PAPER_COLORS = {"o": (74, 70, 82), "P": (246, 243, 234), "p": (216, 211, 198),
                "c": (176, 170, 156), "s": (206, 200, 186)}


def paper_ball(px=4) -> Image.Image:
    """Drawn a little chunkier than the cat's pixels, so it reads at desktop size."""
    im = Image.new("RGBA", (len(PAPER[0]) * px, len(PAPER) * px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y, row in enumerate(PAPER):
        for x, c in enumerate(row):
            if c != ".":
                d.rectangle([x * px, y * px, x * px + px - 1, y * px + px - 1], fill=(*PAPER_COLORS[c], 255))
    return im


BALL = paper_ball()
BALL_Y = GROUND - BALL.height / 2 + 1    # resting on the floor
BALL_X = 400                               # just in front of her paws


def put_ball(im, cx, cy, turns):
    ball = BALL.rotate(90 * (turns % 4))
    im.alpha_composite(ball, (round(cx - ball.width / 2), round(cy - ball.height / 2)))
    return im


def make_paper():
    w = 427
    # 1. She spots it rolling in, then bats it about.
    play = []
    for k, i in enumerate(range(9, 18)):
        t = k / 8
        x = w + BALL.width - (w + BALL.width - BALL_X) * (1 - (1 - t) ** 2)
        play.append(put_ball(frame("happy", i), x, BALL_Y, -int((w - x) / 10)))
    for k, i in enumerate(range(18, 35)):
        hop = abs(math.sin(k * math.pi / 4)) * (14 if k < 14 else 4)
        play.append(put_ball(frame("happy", i), BALL_X + (4 if k % 4 < 2 else 0), BALL_Y - hop, k // 2))
    # 2. Off she goes, nudging it along in front of her. Loops while she walks.
    chase = []
    count = len(list((ANIMATIONS / "walking").glob("frame_*.png")))
    for i in range(count):
        # It rolls a little ahead, she catches up and taps it on again: twice per loop.
        phase = (i % (count // 2)) / (count // 2)
        ahead = 6 * math.sin(phase * math.pi)   # kept small so the ball stays inside the frame
        tap = 3 if phase < 0.08 else 0
        chase.append(put_ball(frame("walking", i), BALL_X + ahead, BALL_Y - tap, i // 2))
    # 3. Got it! She sits back, very pleased, with the ball at her feet.
    end = [put_ball(frame("happy", i), BALL_X, BALL_Y, 0) for i in range(0, 9)]
    for name, frames in (("paperPlay", play), ("paperChase", chase), ("paperEnd", end)):
        for n, im in enumerate(frames):
            save(im, name, n)
        print(f"{name}: {len(frames)} frames")


if __name__ == "__main__":
    make_blanket()
    make_paper()
