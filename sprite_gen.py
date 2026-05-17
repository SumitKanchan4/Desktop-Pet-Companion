"""
sprite_gen.py  —  Dog pixel art, 48x48 per frame, SCALE=2 -> 96x96 on screen.

Side-view golden retriever.  Key dog silhouette features:
  1. Rectangular SNOUT block sticking out from the face (7x6 px)
  2. Floppy OVAL EAR hanging DOWN alongside the face (not on top)
  3. HORIZONTAL elongated body
  4. Short stubby legs below body
  5. Blue collar + gold tag
"""

from pathlib import Path
from PIL import Image, ImageDraw

SPRITE_DIR = Path(__file__).parent / "assets" / "sprites"
FW, FH = 56, 48   # 56 wide gives tail room on left; SCALE=2 -> 112x96 on screen

# ── Palette ───────────────────────────────────────────────────────────────────
FUR  = (215, 135,  48, 255)   # main fur
HFU  = (242, 175,  82, 255)   # fur highlight
SFU  = (148,  82,  16, 255)   # fur shadow
CRE  = (252, 228, 160, 255)   # cream
CHI  = (255, 246, 200, 255)   # cream highlight
OTL  = ( 52,  24,   7, 255)   # dark outline
NOS  = ( 18,   8,   2, 255)   # nose
EYE  = ( 62,  33,   8, 255)   # iris
WTE  = (255, 255, 255, 255)   # eye shine
TNG  = (215,  62,  62, 255)   # tongue
BLU  = ( 65, 118, 222, 255)   # collar
GLD  = (222, 188,  52, 255)   # collar tag
EIN  = (182,  95,  24, 255)   # ear inner
ZZZ  = (150, 145, 215, 255)   # sleep z

# ── Canvas helpers ────────────────────────────────────────────────────────────
def _f():
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)

def _e(d, cx, cy, rx, ry, fill, ol=None, ow=1):
    d.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=fill, outline=ol, width=ow)

def _r(d, x0, y0, x1, y1, fill, ol=None, ow=1):
    x0, x1 = max(0,min(x0,x1)), min(FW-1,max(x0,x1))
    y0, y1 = max(0,min(y0,y1)), min(FH-1,max(y0,y1))
    if x1 > x0 and y1 > y0:
        d.rectangle([x0,y0,x1,y1], fill=fill, outline=ol, width=ow)

# ── Dog body parts (all drawn right-facing; left = FLIP_LEFT_RIGHT) ───────────

def _tail(d, bx, by, wag=0, droop=False):
    tx = max(1, bx - 15)
    ty = by - 3
    if droop:
        p1 = (max(0, tx-4+wag), ty+5)
        p2 = (max(0, tx-7+wag), ty+4)
    else:
        p1 = (max(0, tx-4+wag), ty-9)
        p2 = (max(0, tx-2+wag), ty-14)
    pts = [(tx, ty), p1, p2]
    d.line(pts, fill=OTL, width=7)
    d.line(pts, fill=FUR, width=5)
    d.line(pts, fill=HFU, width=2)
    _e(d, p2[0], p2[1], 5, 5, HFU, OTL)
    _e(d, p2[0], p2[1], 3, 3, CHI)


def _body(d, bx, by, sx=0):
    d.ellipse([bx-17-sx, by-10, bx+17+sx, by+10], fill=OTL)
    d.ellipse([bx-16-sx, by-9,  bx+16+sx, by+9],  fill=FUR)
    d.ellipse([bx-13-sx, by-12, bx+13+sx, by-1],  fill=HFU)
    d.ellipse([bx-11-sx, by+2,  bx+11+sx, by+11], fill=CRE)


def _collar(d, hx, by):
    _r(d, hx-7, by-4, hx+8, by+1, BLU, OTL)
    _e(d, hx+4, by-1, 3, 3, GLD, OTL)


def _ear(d, hx, hy):
    """
    Floppy ear: a TALL OVAL attached to the LEFT side of the head,
    hanging DOWN so the majority is BELOW and BESIDE the skull.
    Drawn BEFORE the head so the head naturally covers the top join.
    """
    ex = hx - 10       # 10 px left of head centre
    ey = hy + 9        # ear centre is BELOW head centre
    _e(d, ex, ey, 7, 12, OTL)
    _e(d, ex, ey, 6, 11, FUR)
    _e(d, ex, ey, 5, 10, SFU)           # darker - ear in shadow
    _e(d, ex, ey+2, 4,  7, EIN)         # inner ear warm tint
    _e(d, ex+4, hy+2, 5, 6, FUR)        # smooth join to skull


def _head(d, hx, hy, blink=False, mouth=False):
    # ── skull ─────────────────────────────────────────────────────────────────
    _e(d, hx,   hy,    12, 11, OTL)
    _e(d, hx,   hy,    11, 10, FUR)
    _e(d, hx-1, hy-4,   8,  6, HFU)     # forehead highlight

    # ── cream face panel (front portion of skull) ──────────────────────────────
    _e(d, hx+5, hy+2, 7, 8, CRE)

    # ── SNOUT / MUZZLE ─────────────────────────────────────────────────────────
    # This rectangular block is THE primary dog identifier.
    sx = hx + 9        # left edge of snout
    sy = hy + 3        # vertical centre of snout
    sw, sh = 6, 6      # 6 wide x 6 tall
    _r(d, sx-1, sy-sh//2-1, sx+sw+1, sy+sh//2+1, OTL)   # outline
    _r(d, sx,   sy-sh//2,   sx+sw,   sy+sh//2,   CRE)   # fill
    _r(d, sx+1, sy-sh//2+1, sx+sw-1, sy-1,       CHI)   # top highlight

    # ── nose at snout tip ──────────────────────────────────────────────────────
    _e(d, sx+sw-1, sy-1, 3, 2, NOS)
    d.point((min(FW-1, sx+sw), sy-2), WTE)               # nose shine

    # ── mouth ─────────────────────────────────────────────────────────────────
    if mouth:
        if sx+sw-2 > sx+1:
            d.arc([sx+1, sy+1, sx+sw-2, sy+sh//2+3], 0, 180, fill=OTL, width=1)
        _e(d, sx+sw//2, sy+sh//2+2, 3, 2, TNG)
    else:
        if sx+sw-2 > sx+2:
            d.arc([sx+2, sy+2, sx+sw-2, sy+sh//2+2], 10, 170, fill=OTL, width=1)

    # ── eye ───────────────────────────────────────────────────────────────────
    eyx, eyy = hx-2, hy-2
    if blink:
        d.line([eyx-3, eyy, eyx+3, eyy], fill=OTL, width=2)
    else:
        _e(d, eyx, eyy, 4, 4, EYE)
        _e(d, eyx, eyy, 2, 2, (20, 10, 3, 255))
        d.point((eyx+1, eyy-2), WTE)
        d.point((eyx+2, eyy-1), WTE)


def _legs(d, bx, by, phase=0):
    """4 short stubby legs. Alternating pairs move for walk cycle."""
    # (x-offset, bent-when-phase?)
    pairs = [
        (bx+11, phase==0),   # front-right
        (bx+7,  phase==1),   # front-left
        (bx-8,  phase==1),   # back-right
        (bx-12, phase==0),   # back-left
    ]
    for lx, bent in pairs:
        ax = lx + (4 if bent else 0)
        sy = by + 7
        ay = by + 14
        lx = max(0, min(FW-1, lx))
        ax = max(0, min(FW-1, ax))
        ay = min(FH-3, ay)
        d.line([(lx, sy), (ax, ay)], fill=OTL, width=5)
        d.line([(lx, sy), (ax, ay)], fill=SFU, width=3)
        _e(d, ax, ay+2, 4, 2, CRE, OTL)


# ── Frame factory ─────────────────────────────────────────────────────────────
BX0, BY0 = 24, 29          # shifted right 6px so tail never clips at x=0

def _mk(bx=BX0, by=BY0, phase=0, wag=0, droop=False,
        blink=False, mouth=False, sx=0, bob=0):
    img, d = _f()
    by2 = by + bob
    hx  = bx + 14
    hy  = by2 - 14
    _tail(d, bx, by2, wag=wag, droop=droop)
    _body(d, bx, by2, sx=sx)
    _ear(d, hx, hy)               # ear drawn BEFORE head
    _collar(d, hx, by2)
    _legs(d, bx, by2, phase=phase)
    _head(d, hx, hy, blink=blink, mouth=mouth)
    return img

_FL = Image.FLIP_LEFT_RIGHT

# ── Animations ────────────────────────────────────────────────────────────────

def make_walk_frames(fr=True):
    out = []
    for i in range(4):
        f = _mk(phase=i%2, wag=(i%2)*4-2, bob=(-1 if i%2==0 else 0))
        out.append(f if fr else f.transpose(_FL))
    return out


def make_run_frames(fr=True):
    out = []
    for i in range(4):
        f = _mk(phase=i%2, sx=(4 if i%2==0 else 0),
                mouth=(i%2==0), bob=(-3 if i%2==0 else 0))
        out.append(f if fr else f.transpose(_FL))
    return out


def make_idle_frames():
    # standing still, tail wagging, blink on frame 2
    return [_mk(phase=0, wag=(i%2)*3, droop=True, blink=(i==2))
            for i in range(4)]


def make_sleep_frames():
    frames = []
    for i in range(2):
        img, d = _f()
        bx, by = 22, 37
        # Very flat lying body
        d.ellipse([bx-18, by-5, bx+18, by+5], fill=OTL)
        d.ellipse([bx-17, by-4, bx+17, by+4], fill=FUR)
        d.ellipse([bx-14, by-7, bx+14, by-1], fill=HFU)
        d.ellipse([bx-12, by+1, bx+12, by+5], fill=CRE)
        # Head resting on a paw
        hx, hy = bx+15, by-5
        _e(d, hx,    hy,    9, 8, OTL)
        _e(d, hx,    hy,    8, 7, FUR)
        _e(d, hx-2,  hy-3,  6, 5, HFU)
        _e(d, hx+3,  hy+1,  5, 6, CRE)         # cream face
        _e(d, hx-2,  hy+7,  7, 3, FUR, OTL)    # paw under head
        _r(d, hx+5,  hy-1, hx+13, hy+4, CRE, OTL)  # snout
        _e(d, hx+11, hy,    2, 2, NOS)          # nose
        d.line([hx-4, hy-3, hx, hy-3], fill=OTL, width=2)   # closed eye
        # Ear draping down
        _e(d, hx-7, hy+4, 5, 9, OTL)
        _e(d, hx-7, hy+4, 4, 8, SFU)
        _e(d, hx-7, hy+4, 3, 6, EIN)
        # Floating Zs
        d.text((bx-2, by-21 - i*3), "zZ", fill=ZZZ)
        frames.append(img)
    return frames


def make_watch_frames():
    return [_mk(phase=0, wag=[0,-3,3][i], droop=True) for i in range(3)]


def make_excited_frames():
    return [_mk(phase=i%2, wag=(i%2)*8-4,
                bob=(-6 if i%2==0 else 0), mouth=(i%2==0))
            for i in range(4)]


def make_grabbed_frames():
    return [_mk(bx=18+(i*4-2), by=24, phase=i%2,
                wag=-4+i*8, droop=True, mouth=True)
            for i in range(2)]


def make_dance_frames():
    return [_mk(phase=i%2, wag=[-5,0,5,0][i],
                bob=[-3,0,-3,0][i], mouth=(i%2==0))
            for i in range(4)]


# ── Phase 1: new expressive animation frame makers ───────────────────────────

def make_sit_frames(fr=True):
    """6 frames: Buddy settling into a sit and holding, tail wagging."""
    out = []
    bx, by = BX0, BY0 + 2   # body sits slightly lower than standing
    for i in range(6):
        img, d = _f()
        hx, hy = bx + 14, by - 15   # head slightly higher (sitting upright)
        wag_v = [0, 2, 4, -2, -4, 1][i]

        # Tail curves upward over back when sitting (not drooped)
        tx = bx - 12
        ty = by - 1
        pts_t = [(tx, ty), (max(0, tx - 2), ty - 8), (tx + 2 + wag_v, by - 15)]
        d.line(pts_t, fill=OTL, width=7)
        d.line(pts_t, fill=FUR, width=5)
        d.line(pts_t, fill=HFU, width=2)
        _e(d, pts_t[-1][0], pts_t[-1][1], 5, 5, HFU, OTL)
        _e(d, pts_t[-1][0], pts_t[-1][1], 3, 3, CHI)

        # Compact body (slightly taller proportion for a sitting dog)
        d.ellipse([bx - 11, by - 10, bx + 13, by + 9], fill=OTL)
        d.ellipse([bx - 10, by - 9,  bx + 12, by + 8], fill=FUR)
        d.ellipse([bx -  7, by - 11, bx +  9, by - 2], fill=HFU)
        d.ellipse([bx -  7, by +  2, bx +  9, by + 9], fill=CRE)

        # Haunches on ground (rounded lump at rear-bottom)
        _e(d, bx - 12, by + 6, 7, 5, OTL)
        _e(d, bx - 12, by + 6, 6, 4, FUR)
        _e(d, bx - 12, by + 6, 4, 3, SFU)

        # Front legs straight down (sitting posture)
        for lx in [bx + 8, bx + 12]:
            lxc = min(FW - 2, lx)
            aye = min(FH - 3, by + 17)
            d.line([(lxc, by + 7), (lxc, aye)], fill=OTL, width=5)
            d.line([(lxc, by + 7), (lxc, aye)], fill=SFU, width=3)
            _e(d, lxc, min(FH - 3, aye), 4, 2, CRE, OTL)

        _collar(d, hx, by - 2)
        _ear(d, hx, hy)
        _head(d, hx, hy, blink=(i == 3), mouth=(i == 5))
        out.append(img if fr else img.transpose(_FL))
    return out


def make_jump_frames(fr=True):
    """8 frames: crouch → launch → airborne peak → descent → land → recover.
    PetWindow moves the actual window position as a parabola; the sprite shows
    the body pose at each stage.
    """
    # (bob, wag, mouth, sx, droop, phase)
    params = [
        ( 2,  0, False, 0, True,  0),  # 0: pre-jump crouch
        (-2,  4, True,  2, False, 1),  # 1: push-off (body stretching up)
        (-7,  6, True,  3, False, 0),  # 2: rising
        (-9,  8, True,  4, False, 1),  # 3: peak (max height in frame)
        (-9, -8, True,  4, False, 0),  # 4: peak hold (tail swings other way)
        (-5,  5, False, 2, False, 1),  # 5: descent
        (-1,  3, False, 0, False, 0),  # 6: about to land
        ( 3, -3, False, 0, True,  0),  # 7: land impact (legs compressed)
    ]
    out = []
    for bob, wag, mouth, sx, droop, phase in params:
        f = _mk(phase=phase, wag=wag, bob=bob, mouth=mouth, sx=sx, droop=droop)
        out.append(f if fr else f.transpose(_FL))
    return out


def make_paw_frames(fr=True):
    """6 frames: front right paw raised and batting at screen edge."""
    exts = [0, 3, 6, 8, 6, 3]   # reach extension per frame
    out = []
    for ext in exts:
        img, d = _f()
        bx, by = BX0, BY0
        hx, hy = bx + 14, by - 14
        _tail(d, bx, by, wag=3, droop=True)
        _body(d, bx, by)
        _ear(d, hx, hy)
        _collar(d, hx, by)

        # Front-left + both back legs — drawn normally
        for lx in [bx + 7, bx - 8, bx - 12]:
            d.line([(lx, by + 7), (lx, by + 14)], fill=OTL, width=5)
            d.line([(lx, by + 7), (lx, by + 14)], fill=SFU, width=3)
            _e(d, lx, by + 16, 4, 2, CRE, OTL)

        # Front-right paw raised and reaching forward
        lx_r  = bx + 11
        paw_x = min(FW - 3, lx_r + 4 + ext)
        paw_y = max(2, by + 7 - 5 - ext // 2)
        d.line([(lx_r, by + 7), (paw_x, paw_y)], fill=OTL, width=5)
        d.line([(lx_r, by + 7), (paw_x, paw_y)], fill=SFU, width=3)
        _e(d, min(FW - 3, paw_x + 3), paw_y, 5, 3, CRE, OTL)

        _head(d, hx, hy, blink=(ext == 8))
        out.append(img if fr else img.transpose(_FL))
    return out


def make_scratch_frames():
    """4 frames: back hind leg raised, scratching behind ear."""
    # (thigh x-offset, thigh y-offset) relative to hind leg base
    scratch_pts = [(6, -1), (8, -6), (9, -5), (7, -2)]
    out = []
    for i, (sx_off, sy_off) in enumerate(scratch_pts):
        img, d = _f()
        bx, by = BX0, BY0
        hx, hy = bx + 14, by - 14
        _tail(d, bx, by, wag=[2, 0, -2, 0][i], droop=True)
        _body(d, bx, by)
        _ear(d, hx, hy)
        _collar(d, hx, by)

        # Both front legs + back-right leg — normal
        for lx in [bx + 11, bx + 7, bx - 8]:
            d.line([(lx, by + 7), (lx, by + 14)], fill=OTL, width=5)
            d.line([(lx, by + 7), (lx, by + 14)], fill=SFU, width=3)
            _e(d, lx, by + 16, 4, 2, CRE, OTL)

        # Back-left leg raised and bent toward ear
        hx_b = bx - 12
        tip_x = hx_b + sx_off
        tip_y = by + sy_off
        d.line([(hx_b, by + 7), (tip_x, tip_y)], fill=OTL, width=5)
        d.line([(hx_b, by + 7), (tip_x, tip_y)], fill=SFU, width=3)
        _e(d, tip_x + 3, tip_y, 4, 2, CRE, OTL)   # paw near ear

        _head(d, hx, hy, blink=(i == 2))
        out.append(img)
    return out


def make_stretch_frames():
    """5 frames: waking body-stretch — front paws forward, back arched, big yawn."""
    # (body_sx, head_dip, mouth_open)
    params = [(0, 0, False), (2, 1, False), (5, 2, True), (5, 2, True), (1, 0, False)]
    out = []
    for sx, hdip, mouth in params:
        img, d = _f()
        bx = BX0 - sx // 2
        by = BY0 + 2
        hx = bx + 14 + sx // 2
        hy = by - 12 + hdip   # head dips slightly during stretch
        _tail(d, max(1, bx - sx // 2), by, wag=0, droop=True)
        _body(d, bx, by, sx=sx)

        # Front paws extended forward flat
        for lx_f in [bx + 12 + sx, bx + 8 + sx]:
            lx = min(FW - 3, lx_f)
            d.line([(lx, by + 5), (lx + 3, by + 14)], fill=OTL, width=5)
            d.line([(lx, by + 5), (lx + 3, by + 14)], fill=SFU, width=3)
            _e(d, min(FW - 3, lx + 6), by + 15, 6, 2, CRE, OTL)

        # Back legs (normal)
        for lx_b in [bx - 8, bx - 12]:
            d.line([(lx_b, by + 5), (lx_b, by + 14)], fill=OTL, width=5)
            d.line([(lx_b, by + 5), (lx_b, by + 14)], fill=SFU, width=3)
            _e(d, lx_b, by + 15, 4, 2, CRE, OTL)

        _collar(d, hx, by)
        _ear(d, hx, hy)
        _head(d, hx, hy, mouth=mouth)
        out.append(img)
    return out


# ── Sheet builder ─────────────────────────────────────────────────────────────

def _sheet(frames, name):
    s = Image.new("RGBA", (FW * len(frames), FH), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * FW, 0))
    s.save(SPRITE_DIR / f"{name}.png")
    print(f"  {name}.png  ({len(frames)}f)")


def generate_all():
    SPRITE_DIR.mkdir(parents=True, exist_ok=True)
    _sheet(make_walk_frames(True),   "walk_right")
    _sheet(make_walk_frames(False),  "walk_left")
    _sheet(make_run_frames(True),    "run_right")
    _sheet(make_run_frames(False),   "run_left")
    _sheet(make_idle_frames(),       "idle")
    _sheet(make_sleep_frames(),      "sleep")
    _sheet(make_watch_frames(),      "watch")
    _sheet(make_excited_frames(),    "excited")
    _sheet(make_grabbed_frames(),    "grabbed")
    _sheet(make_dance_frames(),      "dance")
    # Phase 1: new expressive animations
    _sheet(make_sit_frames(True),    "sit_right")
    _sheet(make_sit_frames(False),   "sit_left")
    _sheet(make_jump_frames(True),   "jump_right")
    _sheet(make_jump_frames(False),  "jump_left")
    _sheet(make_paw_frames(True),    "paw_right")
    _sheet(make_paw_frames(False),   "paw_left")
    _sheet(make_scratch_frames(),    "scratch")
    _sheet(make_stretch_frames(),    "stretch")
    print(f"\nDone -> {SPRITE_DIR}")


if __name__ == "__main__":
    generate_all()
