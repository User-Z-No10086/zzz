"""反转环节评测：用真实模型扮演「初学者」，看它对好/坏讲解的判断是否可靠。

每个样本：用户讲一段 → 模型给出复述+追问 → 四条校验 + 覆盖度 → 判定。
用法：$env:ZHIPU_API_KEY="..."; python tools/eval_reversal.py
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game"))

from engine import checks, novice  # noqa: E402

GAME = os.path.join(HERE, "..", "game")

GOOD = "它先看脚下哪边最陡，然后往最陡的反方向迈一小步。这个动作反复做很多次，位置越来越低，最后到谷底、脚下平了就停住。步子太大会来回跳，太小又太慢。"
HALF = "它先看脚下哪边最陡，然后往反方向迈一小步。"
VAGUE = "就是这样慢慢走，走久了就到了。"
WRONG = "它每次都往最陡的方向往上爬一小步，越爬越高。"

CASES = [
    ("讲全了", GOOD, "pass"),
    ("只讲一半", HALF, "partial"),
    ("空泛", VAGUE, "confused"),
    ("讲反了", WRONG, "partial"),
]


def main():
    chars = json.load(io.open(os.path.join(GAME, "content", "characters.json"), encoding="utf-8"))["characters"]
    route = json.load(io.open(os.path.join(GAME, "content", "route-gradient.json"), encoding="utf-8"))
    node = route["nodes"][-1]
    trig = node["trigger"]

    print("provider=%s model=%s\n" % (os.environ.get("ZHIPU_MODEL", "glm-4-flash"), ""))
    hits = 0
    total = 0
    for c in chars[:3]:
        print("=" * 62)
        print("【%s】" % c["name"])
        for label, text, expect in CASES:
            ai = novice.novice(
                text,
                [],
                route.get("banned", []),
                [],
                c["name"],
                persona=c.get("persona", ""),
            )
            j = checks.judge(route, trig["rubric"], text, text, text, ai)
            total += 1
            ok = (j["verdict"] == expect) or (expect == "partial" and j["verdict"] in ("partial", "confused"))
            hits += 1 if ok else 0
            print("  %-6s 期望 %-8s 实际 %-8s 覆盖 %.2f 复述 %.2f %s"
                  % (label, expect, j["verdict"], j["coverage"], j["restate_sim"], "✓" if ok else "✗"))
            print("      复述：%s" % ai.get("restate", "")[:50])
            print("      追问：%s" % ai.get("question", "")[:50])
    print("=" * 62)
    print("判定符合预期 %d/%d" % (hits, total))


if __name__ == "__main__":
    main()
