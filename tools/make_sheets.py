"""Assembles the QA frames rendered by blender/render_qa.py into contact sheets.

    python3 tools/make_sheets.py [frames_dir] [out_dir]
"""
import glob
import os
import re
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "renders", "frames")
DST = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "renders")


def sheet(paths, cols, out, labels=None, bg=(250, 246, 240)):
    ims = [Image.open(p).convert("RGB") for p in paths]
    if not ims:
        return
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    S = Image.new("RGB", (w * cols, h * rows), bg)
    d = ImageDraw.Draw(S)
    for i, im in enumerate(ims):
        x, y = (i % cols) * w, (i // cols) * h
        S.paste(im, (x, y))
        if labels:
            d.rectangle((x + 4, y + 4, x + 8 + 7 * len(labels[i]), y + 20), fill=(255, 255, 255))
            d.text((x + 7, y + 6), labels[i], fill=(20, 20, 20))
    S.save(out, optimize=True)
    print("wrote", out)


def main():
    os.makedirs(DST, exist_ok=True)
    turn = [os.path.join(SRC, f"turn_{n}.png") for n in ("front", "q34_left", "side", "back", "q34_right")]
    turn = [p for p in turn if os.path.exists(p)]
    sheet(turn, len(turn), os.path.join(DST, "turnaround.png"))

    poses = ["open", "relaxed", "fist", "wave", "phone", "point"]
    views = ["palm", "back", "thumb_side", "pinky_side"]
    hp = [os.path.join(SRC, f"hand_{p}_{v}.png") for p in poses for v in views]
    if all(os.path.exists(p) for p in hp):
        sheet(hp, 4, os.path.join(DST, "hand_poses.png"), [f"{p} / {v}" for p in poses for v in views])

    anims = sorted({re.match(r"anim_(\w+?)_\d+\.png", os.path.basename(p)).group(1)
                    for p in glob.glob(os.path.join(SRC, "anim_*.png"))})
    for a in anims:
        fr = sorted(glob.glob(os.path.join(SRC, f"anim_{a}_*.png")))
        sheet(fr, len(fr), os.path.join(DST, f"anim_{a}.png"),
              [f"{a} f{int(re.search(r'_(\d+)\.png', p).group(1))}" for p in fr])


if __name__ == "__main__":
    main()
