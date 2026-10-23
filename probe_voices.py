"""用真实模型逐个角色生成前两节讲解，检查语气像不像、讲解清不清楚。

用法（PowerShell）：
  $env:ZHIPU_API_KEY = "..."
  python tools/probe_voices.py            # 默认 glm-4-flash
  $env:ZHIPU_MODEL = "glm-4-plus"; python tools/probe_voices.py
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game"))

from engine import llm, teacher  # noqa: E402

GAME = os.path.join(HERE, "..", "game")


def load(name):
    with io.open(os.path.join(GAME, "content", name), encoding="utf-8") as f:
        return json.load(f)


def main():
    chars = load("characters.json")["characters"]
    route = load("route-gradient.json")
    nodes = route["nodes"][:2]
    only = os.environ.get("ONLY")

    print("provider=%s model=%s\n" % (llm.provider(), os.environ.get("ZHIPU_MODEL", "glm-4-flash")))
    stats = {"llm": 0, "fallback": 0}

    for c in chars:
        if only and c["id"] != only:
            continue
        print("=" * 70)
        print("【%s】%s · %s" % (c["name"], c["role_cn"], c["title"]))
        for node in nodes:
            r = teacher.teach(c, route, node)
            stats["llm" if r["source"] == "llm" else "fallback"] += 1
            flag = "生成" if r["source"] == "llm" else "退回(%s)" % (r["why"] or "-")
            print("  ── %s  [%s]" % (node["title"], flag))
            for line in r["lines"]:
                print("     ·", line)
            print()

    total = stats["llm"] + stats["fallback"]
    print("=" * 70)
    print("生成成功 %d/%d，退回 %d" % (stats["llm"], total, stats["fallback"]))


if __name__ == "__main__":
    main()
