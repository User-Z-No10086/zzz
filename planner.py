"""课程规划：用户说想学什么 → 联网检索 → 生成学习路径（节点+讲解+练习题+结尾反转）。

产物是 route JSON，格式和手写的 route-gradient.json 完全一致，游戏直接就吃。
"""

import io
import json
import os
import re

from . import llm

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(GAME, "content")

SYSTEM = """你是教学游戏《下山的人》的课程设计师。任务：为学习主题设计一条**能一节课上完**的路线。

硬性要求：
1. 3~4 节。前几节是讲解；**至少两节**要在真正的难点处插入检查：
   - type=choice（选择题，2 个选项，answer 用 0/1）
   - type=blank（填空，题干用 ＿＿ 挖空，blanks 给出标准答案和可接受变体）
2. **最后一节必须是 type=reversal**：NPC 把自己刚讲的删掉，请玩家讲给它听。rubric 覆盖前面所有知识点 id。
3. 讲解口语、短句、有画面感，每节 2~4 句；不要教科书腔。
4. knowledge 的 aliases 写「普通人会怎么说」，不要写术语定义。
5. banned 放本课术语表（反转时 NPC 不许用玩家没说过的术语）。
6. 每节给 must（该讲的要点，二维数组：每组任一命中即可）和 avoid（讲错时才会出现的错误说法）。
7. 事实必须准确；优先使用你检索到的资料。
8. **输出必须是合法 JSON**：字符串里不要出现英文双引号（要引号就用「」），不要换行符，不要注释。

只输出 JSON，不要解释文字：
{
  "id": "kebab-id", "title": "课程名", "topic": "一句话主题", "tagline": "一句话简介",
  "banned": ["术语1", "术语2", "术语3"],
  "knowledge": {"k1": {"label": "要点：…", "aliases": ["口语说法1", "口语说法2"]}},
  "passCoverage": 0.6, "passRestateSim": 0.3,
  "nodes": [
    {"id": "n1", "title": "第一节 · …", "goal": "…", "covers": ["k1"],
     "narration": "旁白，第二人称，有画面感",
     "teach": [{"who": "mentor", "text": "讲解句"}],
     "must": [["关键词", "同义词"]], "avoid": ["错误说法"],
     "trigger": {"type": "choice", "badge": "难点", "q": "…", "options": ["…","…"], "answer": 0, "explain": "…"}},
    {"id": "n2", "title": "第二节 · …", "goal": "…", "covers": ["k2"],
     "narration": "…", "teach": [{"who": "mentor", "text": "…"}],
     "trigger": {"type": "blank", "badge": "难点", "q": "题干 ＿＿", "blanks": [{"answer": "…", "accept": ["…"]}], "explain": "…"}},
    {"id": "n3", "title": "结尾 · 反转", "goal": "…", "covers": ["k1", "k2"],
     "narration": "…", "teach": [{"who": "mentor", "text": "最后一段"}],
     "trigger": {"type": "reversal", "badge": "反转", "title": "反转 · 现在轮到你讲",
                 "narration": "NPC 把刚讲的删掉了", "prompt": "我全忘了，你能讲给我听吗？",
                 "rubric": ["k1", "k2"], "passCoverage": 0.5, "hint": "…", "passLine": "…"}}
  ]
}"""


def slugify(topic):
    s = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", topic).strip("-").lower()
    return s[:40] or "course"


def _validate(route):
    if not isinstance(route, dict):
        return "不是对象"
    for key in ("id", "title", "knowledge", "nodes"):
        if not route.get(key):
            return "缺 %s" % key
    nodes = route["nodes"]
    if not isinstance(nodes, list) or len(nodes) < 2:
        return "nodes 少于 2 节"
    kinds = []
    for n in nodes:
        if not n.get("teach"):
            return "节点 %s 缺 teach" % n.get("id")
        t = n.get("trigger") or {}
        kinds.append(t.get("type"))
        if t.get("type") not in ("choice", "blank", "reversal", None):
            return "节点 %s trigger 非法" % n.get("id")
        if t.get("type") == "choice" and not isinstance(t.get("options"), list):
            return "节点 %s 选择题缺 options" % n.get("id")
        if t.get("type") == "blank" and not isinstance(t.get("blanks"), list):
            return "节点 %s 填空缺 blanks" % n.get("id")
    if kinds[-1] != "reversal":
        return "最后一节不是反转"
    if kinds.count("choice") + kinds.count("blank") < 1:
        return "没有任何难点检查"
    if not route.get("banned"):
        return "banned 为空"
    return None


def _prepare(route, topic, sources):
    route["id"] = route.get("id") or slugify(topic)
    route.setdefault("topic", topic)
    route.setdefault("passCoverage", 0.6)
    route.setdefault("passRestateSim", 0.3)
    route["generated"] = True
    route["_sources"] = [s[:300] for s in (sources or [])[:4]]
    for i, n in enumerate(route["nodes"]):
        n.setdefault("id", "n%d" % (i + 1))
        for b in (n.get("teach") or []):
            b.setdefault("who", "mentor")
    return route


def plan_route(topic):
    """返回 {"ok":bool,"route":...,"sources":[...],"error":...}；成功会写进 content/。"""
    topic = (topic or "").strip()
    if not topic:
        return {"ok": False, "error": "先说一个想学的主题吧。"}
    if len(topic) > 40:
        return {"ok": False, "error": "主题太长了，短一点。"}
    if llm.provider() not in ("zhipu", "deepseek"):
        return {"ok": False, "error": "生成课程需要模型 Key（ZHIPU_API_KEY 或 DEEPSEEK_API_KEY）。"}

    user = "学习主题：「%s」\n请先检索资料，再按结构输出课程 JSON。" % topic
    data, sources = None, []
    last_err = ""
    for attempt in range(3):
        note = "" if attempt == 0 else "\n\n上一次输出不是合法 JSON 或不合规（%s）。请修正后只输出完整 JSON。" % last_err
        try:
            data, sources = llm.chat_json_web(SYSTEM, user + note)
        except Exception as e:
            last_err = str(e)[:100]
            continue
        err = _validate(data)
        if not err:
            break
        last_err = err
        data = None
    if not data:
        return {"ok": False, "error": "生成失败：%s" % (last_err or "多次尝试未通过校验")}

    route = _prepare(data, topic, sources)
    path = os.path.join(CONTENT, "route-%s.json" % route["id"])
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(route, ensure_ascii=False, indent=2) + "\n")
    return {"ok": True, "route": route, "sources": sources, "path": path}


def list_routes():
    out = []
    if not os.path.isdir(CONTENT):
        return out
    for name in sorted(os.listdir(CONTENT)):
        if not (name.startswith("route-") and name.endswith(".json")):
            continue
        try:
            with io.open(os.path.join(CONTENT, name), encoding="utf-8") as f:
                r = json.load(f)
            out.append({
                "file": name,
                "id": r.get("id"),
                "title": r.get("title") or name,
                "tagline": r.get("tagline", ""),
                "nodes": len(r.get("nodes", [])),
                "generated": bool(r.get("generated")),
                "sources": len(r.get("_sources") or []),
            })
        except Exception:
            continue
    return out
