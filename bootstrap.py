"""一键补齐本仓库缺的「非代码部分」，clone 下来直接能跑。

用法：
    python tools/bootstrap.py --sdk "D:/renpy-8.5.3-sdk"

它会做三件事：
1. 从 Ren'Py SDK 的 the_question 模板复制 gui.rpy / screens.rpy / options.rpy 和 gui/ 素材
   （只在文件不存在时才复制，不会覆盖你自己的改动）
2. 从 SDK 的 sdk-fonts 复制中文字体到 game/fonts/
3. 生成六位角色的占位立绘 + 背景（纯标准库画 PNG，不依赖 Pillow）
   之后你可以用自己的立绘覆盖 game/images/characters/<id>/normal.png
"""

import argparse
import os
import struct
import sys
import zlib

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "game")

TEMPLATE_FILES = ["gui.rpy", "screens.rpy", "options.rpy"]
CHARS = [
    ("deepseek", (77, 107, 254)),
    ("kimi", (124, 92, 255)),
    ("chatgpt", (16, 163, 127)),
    ("claude", (217, 119, 87)),
    ("gemini", (66, 133, 244)),
    ("grok", (156, 163, 175)),
]
W, H = 900, 1300


def write_png(path, width, height, pixels):
    """pixels: list of rows, each row is bytes RGBA"""
    raw = b"".join(b"\x00" + row for row in pixels)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def sprite_rows(accent):
    """画一个很简单的剪影：光晕 + 头 + 肩，够占位就行。"""
    ar, ag, ab = accent
    cx, head_cy, head_r = W // 2, 470, 165
    rows = []
    for y in range(H):
        row = bytearray()
        for x in range(W):
            r = g = b = a = 0
            dx, dy = x - cx, y - head_cy
            in_head = dx * dx + dy * dy <= head_r * head_r
            in_body = y > 760 and abs(x - cx) < 150 + (y - 760) * 0.55
            if in_head or in_body:
                r, g, b, a = 24, 30, 42, 255
                edge = (in_head and head_r - 3 < (dx * dx + dy * dy) ** 0.5) or (
                    in_body and abs(abs(x - cx) - (150 + (y - 760) * 0.55)) < 3
                )
                if edge:
                    r, g, b = ar, ag, ab
            else:
                glow = max(0.0, 1.0 - (((x - cx) ** 2 + (y - 620) ** 2) ** 0.5) / 620.0)
                if glow > 0:
                    r, g, b = int(ar * glow * 0.18), int(ag * glow * 0.18), int(ab * glow * 0.18)
                    a = int(200 * glow)
            row += bytes((r, g, b, a))
        rows.append(bytes(row))
    return rows


def bg_rows():
    rows = []
    for y in range(H):
        t = y / H
        base = (int(9 + 8 * (1 - t)), int(12 + 14 * (1 - t)), int(18 + 22 * (1 - t)))
        row = bytearray()
        for x in range(W):
            d = (((x - W / 2) ** 2 + (y - H * 0.35) ** 2) ** 0.5) / (W * 0.8)
            k = max(0.0, 1.0 - d)
            row += bytes((min(255, int(base[0] + 30 * k)), min(255, int(base[1] + 42 * k)), min(255, int(base[2] + 52 * k)), 255))
        rows.append(bytes(row))
    return rows


def copy_from_sdk(sdk):
    q = os.path.join(sdk, "the_question", "game")
    if not os.path.isdir(q):
        q = os.path.join(sdk, "templates", "english", "game")
    if not os.path.isdir(q):
        print("! 在 SDK 里找不到模板目录：", q)
        return False

    import shutil

    for name in TEMPLATE_FILES:
        src = os.path.join(q, name)
        dst = os.path.join(GAME, name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print("  复制模板文件:", name)

    gui_src = os.path.join(q, "gui")
    gui_dst = os.path.join(GAME, "gui")
    if os.path.isdir(gui_src) and not os.path.isdir(gui_dst):
        shutil.copytree(gui_src, gui_dst)
        print("  复制 gui/ 素材")

    font_src = os.path.join(sdk, "sdk-fonts", "SourceHanSansLite.ttf")
    font_dst_dir = os.path.join(GAME, "fonts")
    os.makedirs(font_dst_dir, exist_ok=True)
    font_dst = os.path.join(font_dst_dir, "SourceHanSansLite.ttf")
    if os.path.exists(font_src) and not os.path.exists(font_dst):
        shutil.copy2(font_src, font_dst)
        print("  复制中文字体")
    return True


def gen_art():
    for cid, accent in CHARS:
        outdir = os.path.join(GAME, "images", "characters", cid)
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, "normal.png")
        if os.path.exists(path) and os.path.getsize(path) > 200000:
            print("  已有立绘，跳过:", cid)
            continue
        write_png(path, W, H, sprite_rows(accent))
        print("  生成占位立绘:", cid)

    bgdir = os.path.join(GAME, "images", "bg")
    os.makedirs(bgdir, exist_ok=True)
    bg = os.path.join(bgdir, "corridor.png")
    if not os.path.exists(bg):
        write_png(bg, 1920, 1080, bg_rows())
        print("  生成背景: bg/corridor.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", help="Ren'Py SDK 目录（含 renpy.exe 的那一层）")
    ap.add_argument("--skip-art", action="store_true")
    args = ap.parse_args()

    print("== 从 SDK 复制模板与字体 ==")
    if args.sdk:
        if not copy_from_sdk(os.path.abspath(args.sdk)):
            print("  跳过（没找到模板）")
    else:
        print("  未指定 --sdk，跳过；请手动从 Ren'Py SDK 复制 gui.rpy / screens.rpy / options.rpy / gui/ / 字体")

    if not args.skip_art:
        print("== 生成占位立绘 ==")
        gen_art()

    print("\n完成。用 SDK 启动：")
    print('  renpy.exe "%s"' % ROOT)


if __name__ == "__main__":
    main()
