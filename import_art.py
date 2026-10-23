"""把源立绘导入成 Ren'Py 可用的角色图。

输入：art-source/*.PNG（编号从小到大对应 characters.json 里 art_src 字段）
输出：game/images/characters/<id>/{normal,happy,angry,shy}.png（900x1300 透明底）

做四件事：
1. 去白底（从四边泛洪填充，容差内视为背景），保留原有 alpha
2. 裁掉透明边，按高度缩放到 1300，居中留白到 900x1300
3. 由同一张底图生成 4 种神态：normal 原样；happy 提亮加暖；angry 压暗加红；
   shy 加粉（模拟脸红）。这是没有多张立绘时的降级方案——真要神态请补图。
"""

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, "..", "game")
ART = os.path.join(HERE, "..", "art-source")
OUT_W, OUT_H = 900, 1300


def strip_white(img, tol=14):
    """从边缘泛洪去掉接近白色的背景。"""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    # 背景色取四角中最亮的
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg = max(corners, key=lambda c: c[0] + c[1] + c[2])

    def is_bg(c):
        return (
            abs(c[0] - bg[0]) <= tol
            and abs(c[1] - bg[1]) <= tol
            and abs(c[2] - bg[2]) <= tol
        )

    if bg[3] < 200:  # 已经是透明底，直接用
        return img

    # 用 BFS 从边框泛洪（限制在背景色附近），避免把人物内部的白衣服打掉
    seen = bytearray(w * h)
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            stack.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            stack.append((x, y))

    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        i = y * w + x
        if seen[i]:
            continue
        if not is_bg(px[x, y]):
            continue
        seen[i] = 1
        px[x, y] = (bg[0], bg[1], bg[2], 0)
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    return img


def fit(img):
    """裁边 + 等比缩放 + 居中到 900x1300。"""
    bbox = img.split()[3].getbbox()
    if bbox:
        img = img.crop(bbox)

    scale = min(OUT_W / img.width, OUT_H / img.height)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)

    canvas = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((OUT_W - img.width) // 2, OUT_H - img.height))
    return canvas


def grade(img, mode):
    """用同一张底图做神态差异（降级方案）。"""
    if mode == "normal":
        return img

    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base.alpha_composite(img)
    rgb = base.convert("RGB")
    alpha = base.split()[3]

    if mode == "happy":
        r, g, b = rgb.split()
        r = r.point(lambda v: min(255, int(v * 1.06 + 8)))
        g = g.point(lambda v: min(255, int(v * 1.03 + 5)))
        b = b.point(lambda v: min(255, int(v * 0.98 + 2)))
        rgb = Image.merge("RGB", (r, g, b))
    elif mode == "angry":
        r, g, b = rgb.split()
        r = r.point(lambda v: min(255, int(v * 1.10 + 6)))
        g = g.point(lambda v: int(v * 0.92))
        b = b.point(lambda v: int(v * 0.92))
        rgb = Image.merge("RGB", (r, g, b))
    elif mode == "shy":
        r, g, b = rgb.split()
        r = r.point(lambda v: min(255, int(v * 1.08 + 10)))
        g = g.point(lambda v: int(v * 0.97))
        b = b.point(lambda v: min(255, int(v * 1.02 + 4)))
        rgb = Image.merge("RGB", (r, g, b))

    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def main():
    cfg = json.load(open(os.path.join(GAME, "content", "characters.json"), encoding="utf-8"))
    srcs = sorted(f for f in os.listdir(ART) if f.upper().endswith(".PNG"))
    print("源图:", len(srcs), srcs)

    used = []
    for c in cfg["characters"]:
        name = c.get("art_src")
        if not name:
            continue
        path = os.path.join(ART, name)
        if not os.path.exists(path):
            print("  缺图:", name, "->", c["id"])
            continue
        img = fit(strip_white(Image.open(path)))
        outdir = os.path.join(GAME, "images", "characters", c["id"])
        os.makedirs(outdir, exist_ok=True)
        img.save(os.path.join(outdir, "normal.png"))
        used.append(name)
        print(f"  {c['id']:9s} <- {name}")

    leftover = [s for s in srcs if s not in used]
    if leftover:
        print("未使用:", leftover)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
