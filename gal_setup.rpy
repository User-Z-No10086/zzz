init -10 python:
    import copy
    import os
    import sys
    import json

    GAMEDIR = renpy.config.gamedir
    if GAMEDIR not in sys.path:
        sys.path.insert(0, GAMEDIR)

    from engine import checks as E_checks
    from engine import novice as E_novice
    from engine import planner as E_planner
    from engine import teacher as E_teacher
    from engine import teachcache as E_teachcache


    def _load(name):
        with open(os.path.join(GAMEDIR, "content", name), encoding="utf-8") as f:
            return json.load(f)


    CHARS = _load("characters.json")

    def _load_routes():
        """content/ 下所有 route-*.json 都是课程（手写的 + AI 生成的）"""
        out = {}
        folder = os.path.join(GAMEDIR, "content")
        for name in sorted(os.listdir(folder)):
            if not (name.startswith("route-") and name.endswith(".json")):
                continue
            try:
                r = _load(name)
                out[r.get("id") or name] = r
            except Exception as e:
                print("[routes] 跳过 %s：%s" % (name, e))
        return out

    ROUTES = _load_routes()

    def route_list():
        return [
            {
                "id": k,
                "title": v.get("title") or k,
                "tagline": v.get("tagline") or "",
                "nodes": len(v.get("nodes") or []),
                "generated": bool(v.get("generated")),
            }
            for k, v in ROUTES.items()
        ]

    ROUTE_LIST = route_list()

    def reload_routes():
        global ROUTES, ROUTE_LIST
        ROUTES = _load_routes()
        ROUTE_LIST = route_list()

    # 自动化测试时可以指定课程与主讲
    TEST_MENTOR = os.environ.get("GAL_TEST_MENTOR", "claude")
    TEST_ROUTE = os.environ.get("GAL_TEST_ROUTE", "gradient-descent")
    # 测试流程分支：gemini 多一道对照题；kimi 中途多一次复述
    TEST_FLOW = {"gemini": "extra_choice", "kimi": "mid_reversal"}.get(TEST_MENTOR, "base")

    # 立绘：image (角色id, 神态) -> png
    for _c in CHARS["characters"]:
        for _e in CHARS["expressions"]:
            renpy.image((_c["id"], _e), "images/characters/%s/%s.png" % (_c["id"], _e))

    renpy.image("bg corridor", "images/bg/corridor.png")


init -9 python:
    CHAR_BY_ID = {c["id"]: c for c in CHARS["characters"]}

    def mk_char(cid):
        c = CHAR_BY_ID[cid]
        return Character(
            c["name"],
            color=c["accent"],
            who_color=c["accent"],
            what_prefix="「",
            what_suffix="」",
        )

    def set_expr(cid, expr=None):
        """显示立绘（每人只有一张原图，expr 参数保留是为了兼容旧调用）"""
        renpy.show("%s normal" % cid, at_list=[mentor_at_right])

    def variant_of(cid):
        """取某个角色的剧情分叉配置"""
        return (CHAR_BY_ID.get(cid, {}) or {}).get("variant") or {}

    def norm(s):
        return E_checks.strip_all(s)

    def v(key, fallback=""):
        """取当前主讲角色的专属台词（字符串类）。"""
        c = CHAR_BY_ID.get(mentor_id, {})
        val = (c.get("voice") or {}).get(key)
        if not val:
            return fallback
        return val

    def vline(key, idx, fallback=""):
        """取当前主讲角色的第 idx 句台词（数组类，比如每节的引导语）。"""
        c = CHAR_BY_ID.get(mentor_id, {})
        val = (c.get("voice") or {}).get(key)
        if not val:
            return fallback
        return val[idx % len(val)]

    def narration_of(text):
        """把旁白里的 {who} 换成当前角色（老师/学姐/同学/学妹）"""
        role = CHAR_BY_ID.get(mentor_id, {}).get("role_cn", "老师")
        try:
            return text.format(who=role)
        except Exception:
            return text

    # 讲解生成缓存：同一个角色同一节只调一次模型
    _teach_cache = {}

    def teach_of(node):
        """返回 {"lines": [...], "source": llm|fake|fallback, "why": ...}"""
        key = (mentor_id, node.get("id"))
        if key not in _teach_cache:
            _teach_cache[key] = E_teacher.teach(
                CHAR_BY_ID[mentor_id],
                R.route,
                node,
                history=[d["text"] for d in R.dialogue if d.get("role") == "hero"],
            )
            src = _teach_cache[key]["source"]
            why = _teach_cache[key].get("why", "")
            if src != "fallback":
                R.stats["teach_llm"] = R.stats.get("teach_llm", 0) + 1
            else:
                print("[teacher] 退回静态讲稿：%s" % (why or "-"))
        return _teach_cache[key]


transform mentor_at_right:
    xalign 1.0
    yalign 1.0
    xoffset -18
    zoom 0.52


init -8 python:
    # 测试专用：Ren'Py 自动化测试用 keysym 打字，中文没有键码。
    # 测试时从队列取文本，生产路径仍然走 renpy.input。
    _test_input_queue = []

    def ask_text(prompt, length=800, default=""):
        if renpy.is_in_test() and _test_input_queue:
            return _test_input_queue.pop(0)
        return renpy.input(prompt, length=length, default=default).strip()


init -8 python:
    class Runner(object):
        """一条学习路线的运行状态：讲解 -> 难点触发 -> 结尾反转。"""

        def __init__(self, route, variant=None):
            self.route = route
            self.variant = variant or {}

            # —— 按角色做剧情分叉 ——
            # drop_nodes    去掉某几节
            # extra_teach   在某节多加几句讲解
            # insert_after  在某节后插入一节（小测 / 对照）
            nodes = []
            for n in route["nodes"]:
                if n["id"] in self.variant.get("drop_nodes", []):
                    continue
                nodes.append(copy.deepcopy(n))

            extra_teach = self.variant.get("extra_teach") or {}
            for n in nodes:
                for line in extra_teach.get(n["id"], []):
                    n["teach"].append({"who": "mentor", "text": line})

            for nid, extra in (self.variant.get("insert_after") or {}).items():
                pos = next((idx for idx, x in enumerate(nodes) if x["id"] == nid), None)
                if pos is not None:
                    nodes.insert(pos + 1, copy.deepcopy(extra))

            self.nodes = nodes
            self.i = 0
            self.phase = "teach"
            self.done = False
            self.concepts = []
            self.terms = []
            self.stuck = {}
            self.all_user_text = ""
            self.dialogue = []
            self.log = []
            self.stats = {"beats": 0, "answers": 0, "wrong": 0, "passes": 0, "rejected": 0, "teach_llm": 0}
            self.last_cov = None
            self.last_sim = None

        @property
        def node(self):
            return self.nodes[self.i]

        @property
        def progress(self):
            return "%d/%d" % (min(self.i + 1, len(self.nodes)), len(self.nodes))

        def known_terms(self):
            return [w for w in self.route.get("banned", []) if norm(w) in norm(self.all_user_text)]

        def credit(self, covers):
            for cid in covers or []:
                label = self.route["knowledge"].get(cid, {}).get("label", cid)
                short = label.split("：")[0]
                if short not in self.concepts:
                    self.concepts.append(short)

        def mark_stuck(self, missing):
            for mid in missing or []:
                self.stuck[mid] = min(self.stuck.get(mid, 0) + 1, 6)

        def advance(self):
            self.phase = "teach"
            self.i += 1
            if self.i >= len(self.nodes):
                self.i = len(self.nodes) - 1
                self.done = True
