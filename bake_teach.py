"""预生成讲解并写入 content/teach-cache.json（随游戏分发）。

用法：
  $env:ZHIPU_API_KEY="..."
  python tools/bake_teach.py            # 全部角色 × 全部节点
  $env:ONLY_IDS="claude,grok"; python tools/bake_teach.py
  $env:TRIES="4"; python tools/bake_teach.py     # 失败节点多试几次
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game"))

from engine import teachcache, teacher  # noqa: E402

GAME = os.path.join(HERE, "..", "game")
TRIES = int(os.environ.get("TRIES", "3"))


def load(name):
    with io.open(os.path.join(GAME, "content", name), encoding="utf-8") as f:
        return json.load(f)


def main():
    # 预先关掉缓存读取，否则读到旧缓存就永远不会真正生成
    os.environ["GAL_NO_CACHE"] = "1"

    chars = load("characters.json")["characters"]
    route = load("route-gradient.json")
    only = [x for x in os.environ.get("ONLY_IDS", "").split(",") if x]
    if only:
        chars = [c for c in chars if c["id"] in only]

    # 节点集合要包含角色分叉插入的节点（gemini 的 g1、kimi 的 k1）
    node_ids = [n["id"] for n in route["nodes"]]
    for c in chars:
        for extra in ((c.get("variant") or {}).get("insert_after") or {}).values():
            if extra.get("id") not in node_ids:
                node_ids.append(extra["id"])

    per_char = {}
    total = 0
    got = 0

    for c in chars:
        nodes = list(route["nodes"])
        for extra in ((c.get("variant") or {}).get("insert_after") or {}).values():
            nodes.append(extra)
        per_char[c["id"]] = {}
        print("【%s】" % c["name"])
        for node in nodes:
            total += 1
            last = ""
            for attempt in range(TRIES):
                r = teacher.teach(c, route, node, history=[])
                if r["source"] in ("llm", "fake"):
                    per_char[c["id"]][node["id"]] = r["lines"]
                    got += 1
                    print("  %-6s ✓ %d 句" % (node["id"], len(r["lines"])))
                    break
                last = r.get("why", "")
            else:
                print("  %-6s ✗ 放弃（%s）" % (node["id"], last))

    teachcache.save(route, per_char)
    print("\n写入 %s：%d/%d 个节点有缓存" % (os.path.basename(teachcache.CACHE_PATH), got, total))


if __name__ == "__main__":
    main()
