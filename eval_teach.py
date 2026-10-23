"""批量评测：每个角色 × 每节 × N 轮，统计生成成功率、失败原因、口头禅重复。

用法：
  $env:ZHIPU_API_KEY="..."
  python tools/eval_teach.py            # 默认 3 轮
  $env:ROUNDS="5"; python tools/eval_teach.py
  $env:ONLY_IDS="claude,grok"; python tools/eval_teach.py
"""

import collections
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game"))

from engine import teacher  # noqa: E402

GAME = os.path.join(HERE, "..", "game")
ROUNDS = int(os.environ.get("ROUNDS", "3"))


def load(name):
    with io.open(os.path.join(GAME, "content", name), encoding="utf-8") as f:
        return json.load(f)


def main():
    chars = load("characters.json")["characters"]
    route = load("route-gradient.json")
    only = [x for x in (os.environ.get("ONLY_IDS", "").split(",")) if x]
    if only:
        chars = [c for c in chars if c["id"] in only]

    total = 0
    ok = 0
    reasons = collections.Counter()
    per_char = collections.defaultdict(lambda: [0, 0])
    conform = collections.defaultdict(lambda: [0, 0])
    phrases = collections.Counter()

    for rnd in range(ROUNDS):
        for c in chars:
            # 模拟游戏里逐节推进：把前面讲过的台词当作 history 传进去
            history = []
            for node in route["nodes"]:
                r = teacher.teach(c, route, node, history=history)
                history.extend(r["lines"])
                total += 1
                per_char[c["id"]][1] += 1
                if r["source"] == "llm":
                    ok += 1
                    per_char[c["id"]][0] += 1
                    # 人设符合度：这节台词是否带上了该角色的语言标记
                    conform[c["id"]][1] += 1
                    if not teacher.style_marks(c, r["lines"]):
                        conform[c["id"]][0] += 1
                    for line in r["lines"]:
                        for tail in ("随你", "你要是觉得", "敢不敢", "我记下来了", "记住"):
                            if tail in line:
                                phrases[(c["id"], tail)] += 1
                else:
                    reasons[(c["id"], r["why"].split("：")[0].split("（")[0])] += 1

    print("=" * 60)
    print("轮数 %d，总调用 %d，成功 %d（%.0f%%）" % (ROUNDS, total, ok, 100.0 * ok / max(total, 1)))
    for cid, (o, n) in per_char.items():
        print("  %-9s 生成 %2d/%2d" % (cid, o, n))
    print("\n人设符合度（台词里带上了该角色的语言标记）：")
    for cid, (good, n) in conform.items():
        print("  %-9s %2d/%2d  %s" % (cid, good, n, "%.0f%%" % (100.0 * good / max(n, 1))))
    print("\n失败原因 Top：")
    for (cid, why), n in reasons.most_common(12):
        print("  %-9s %-18s x%d" % (cid, why, n))
    if phrases:
        print("\n口头禅出现次数（跨轮，越多越机械）：")
        for (cid, p), n in phrases.most_common(10):
            print("  %-9s 「%s」 x%d" % (cid, p, n))


if __name__ == "__main__":
    main()
