"""讲解缓存：把模型生成的台词预先生成好，随游戏一起发。

这样即使玩家没有 API Key，也能看到符合人设的讲解，而不是退回写死的通用稿。
缓存带内容指纹：课程 JSON 一改，旧缓存自动失效。
"""

import hashlib
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
CACHE_PATH = os.path.join(GAME, "content", "teach-cache.json")

_cache = None


def fingerprint(route):
    """课程内容指纹：节点讲解、禁用词、知识点变了就换指纹。"""
    payload = {
        "id": route.get("id"),
        "banned": route.get("banned"),
        "knowledge": route.get("knowledge"),
        "nodes": [
            {"id": n.get("id"), "teach": n.get("teach"), "must": n.get("must"), "avoid": n.get("avoid")}
            for n in route.get("nodes", [])
        ],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def load():
    global _cache
    if _cache is None:
        try:
            with io.open(CACHE_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    return _cache


def lookup(route, char_id, node_id):
    data = load()
    entry = (data.get(route.get("id")) or {})
    if entry.get("fingerprint") != fingerprint(route):
        return None
    lines = ((entry.get("lines") or {}).get(char_id) or {}).get(node_id)
    return lines or None


def save(route, per_char):
    """per_char: {char_id: {node_id: [lines]}}"""
    data = load()
    data[route.get("id")] = {
        "fingerprint": fingerprint(route),
        "lines": per_char,
    }
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with io.open(CACHE_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    global _cache
    _cache = data
