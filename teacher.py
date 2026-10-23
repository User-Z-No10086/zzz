"""「主讲」生成器：让模型用人设口吻讲这一节，但**不许改事实**。

设计要点（对应"接 Key 时要给 AI 提示词，使回答符合人设"）：
1. 人设写进 system prompt：名字、身份、性格、说话方式（从 voice 里取三条样例）。
2. 静态讲稿作为"事实底稿"一起给模型，只允许换说法，不允许改知识点。
3. 禁用术语表照旧生效：老师也不用教材词，保证反转时学生只能靠自己的话讲。
4. 输出强制 JSON {"lines": [...]}，过校验（句数/长度/禁用词/出戏词），不过就退回静态讲稿。
5. 没有 Key 或调用失败 → 静默退回静态讲稿，游戏不中断。
"""

import os
import re

from . import checks, llm, teachcache

# 出戏词：模型不能把自己是 AI 这件事说出来
OUT_OF_CHAR = [
    "作为一个AI", "作为人工智能", "作为AI", "语言模型", "AI助手", "AI 助手",
    "作为一个语言", "系统提示", "prompt", "我没有感情", "我只是模型",
]


# 每个角色的「口头标记」：至少要出现一个，否则重试一次
MUST_MARKS = {
    "deepseek": ["就像", "比方", "好比", "打个比方", "好比说", "你就当"],
    "kimi": ["笔记", "讲义", "看到", "写着", "抄", "记下", "翻到"],
    "chatgpt": ["首先", "其次", "最后", "第一点", "第二点", "总结"],
    "claude": ["取决于", "先别急", "记住", "先看", "我不确定", "严格说", "注意"],
    "gemini": ["一面", "另一面", "两种", "两边", "换个说法", "另一个角度"],
    "grok": ["随你", "你要是", "赌", "敢", "信不信", "笑你", "爱信"],
}


def _banned_hits(text, banned):
    return [w for w in banned if w in text]


# 念出结构性文字（行号、提示词）都算不合格
META_WORDS = ["第一句", "第二句", "第三句", "第四句", "本节要点", "参考句子", "目标：", "输出 JSON"]


def style_marks(char, lines):
    """返回该角色缺失的口头标记（空列表表示 OK）。"""
    marks = MUST_MARKS.get(char["id"], [])
    if not marks:
        return []
    blob = "".join(lines)
    return [] if any(m in blob for m in marks) else marks


def _normalize_lines(lines, max_n=5):
    """模型经常把一整段塞进一行。按句号切开，再合并到不超过 max_n 句。"""
    if not isinstance(lines, list):
        return lines
    out = []
    for l in lines:
        if not isinstance(l, str):
            out.append(l)
            continue
        l = l.strip()
        if len(l) <= 60:
            out.append(l)
            continue
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?；;])", l) if p.strip()]
        if not parts:
            parts = [l]
        # 超长单句：按逗号再切一次，尽量别让一句超过 60 字
        fixed = []
        for p in parts:
            if len(p) <= 60:
                fixed.append(p)
            else:
                buf = ""
                for seg in re.split(r"(?<=[，,、])", p):
                    if len(buf) + len(seg) > 60 and buf:
                        fixed.append(buf)
                        buf = seg
                    else:
                        buf += seg
                if buf:
                    fixed.append(buf)
        out.extend(fixed)

    while len(out) > max_n:
        tail = out.pop()
        out[-1] = out[-1] + tail

    # 模型只给了 1 句：按句末标点拆开，保证至少 2 句（不然就没法分条显示）
    if len(out) == 1 and isinstance(out[0], str):
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?；;])", out[0]) if p.strip()]
        if len(parts) > 1:
            out = parts[:max_n]
    return out


def validate(lines, banned, draft=None, samples=None, avoid=None, must=None, history=None):
    """返回 None 表示合格，否则返回不合格原因。"""
    if not isinstance(lines, list):
        return "不是数组"
    if not (2 <= len(lines) <= 5):
        return "句数 %d 不在 2~5" % len(lines)
    for line in lines:
        if not isinstance(line, str) or not line.strip():
            return "有空白句"
        if len(line) > 60:
            return "单句过长（%d 字）" % len(line)
        if any(w in line for w in OUT_OF_CHAR):
            return "出戏"
        if any(w in line for w in META_WORDS):
            return "念出了结构性文字"
        for s in samples or []:
            if len(s) >= 10 and checks.dice(line, s) >= 0.9:
                return "整句照抄了样例台词"
    blob = "".join(lines)
    if blob.count("？") + blob.count("?") > 1:
        return "问句太多（讲解不该追问）"
    # 句子之间自我重复（模型唠嗑、把同一句念三遍）
    clean = [l for l in lines if isinstance(l, str) and len(l) >= 8]
    for i in range(len(clean)):
        for j in range(i + 1, len(clean)):
            if checks.dice(clean[i], clean[j]) >= 0.6:
                return "句子重复"
    # 跟前面几节说过的话重复（口头禅刷屏）—— 交给 teach() 当软问题处理
    hits = _banned_hits(blob, banned)
    if hits:
        return "用了禁用术语：%s" % "、".join(hits)
    bad = [w for w in (avoid or []) if w in blob]
    if bad:
        return "讲错了关键结论：%s" % "、".join(bad)
    # must 是「每组的任一命中」：确保该节的关键点都讲到了
    for group in (must or []):
        if not any(w in blob for w in group):
            return "漏讲了要点：%s" % "/".join(group)
    if len(blob) < 24:
        return "内容太少"
    if draft:
        sim = checks.dice(blob, "".join(draft))
        if sim >= 0.72:
            return "照抄参考（相似度 %.2f）" % sim
    return None


def voice_samples(char):
    """从角色卡里取语气样例（只作语气参考，禁止整句复制）。"""
    voice = char.get("voice") or {}
    samples = []
    if voice.get("greet"):
        samples.append(voice["greet"])
    for line in (voice.get("lead") or [])[:2]:
        samples.append(line)
    for key in ("badge", "wrong"):
        if voice.get(key):
            samples.append(voice[key])
    # 供 prompt 提示「换个口头禅」
    return samples


def system_prompt(char, route):
    """把角色卡变成提示词。"""
    samples = voice_samples(char)

    style = char.get("style_prompt") or {
        "deepseek": "反应慢半拍，说话有停顿（用「……」「嗯……」）；每节先给一个生活化的比方。",
        "kimi": "安静温和，先复述一遍再往下讲；会提到笔记、讲义。",
        "chatgpt": "话密、热情，爱分点（首先/其次/最后），句子短促。",
        "claude": "克制、严谨，会加限定（「这取决于……」），不夸张、不煽情。",
        "gemini": "总把事情拆成两面（「一面是……另一面是……」）。",
        "grok": "直球、毒舌，爱呛人，句子短，带点挑衅，但不脏。",
    }.get(char["id"], "口语、自然、有画面感。")

    return """你是《下山的人》这部教学视觉小说里的角色【{name}】，身份是「{role_cn}」。

你的人设：{persona}

你说话的样子（样例，**只用来感受语气，绝对不要整句复制**）：
{samples}

现在的场景：放学后的补习班教室，你在给一个来补课的学生讲「{topic}」这节课。

写作要求：
1. 只用**口语短句**，一句不超过 45 个汉字；不要书面腔、不要小标题、不要编号。
2. 绝对不能出现这些词：{banned}。这节课故意不用术语，只用生活化的说法。
3. 不要提问（提问环节由剧情单独触发），不要布置作业，不要跳出教室场景。
4. 不要提到自己是 AI、模型、程序。
5. 语气必须像你这个人：{style}
6. **不要照抄给你的参考句子，也不要照抄上面的样例台词**。参考只是知识点，你要用**自己的说法重讲**；
   把参考里「本节要点：……」这类提示当成你的备忘，绝对不要念出来。
7. **不要替学生下结论**。如果这一节只是铺垫，就别直接给出「往哪边走」的答案；把判断留给他。
8. **不要每节都用同一句口头禅**。你之前说过的话不要再原样重复，换个说法。

改写示范（**只是让你看改写手法，这段示范本身与课程无关，不要出现在台词里**）：
  参考：{ex_from}
  改写：{ex_to}

只输出 JSON，不要任何其他文字：
{{"lines": ["第一句", "第二句", "第三句"]}}
2~4 句，按讲授顺序。""".format(
        name=char["name"],
        role_cn=char["role_cn"],
        persona=char.get("persona", ""),
        samples="\n".join("%d. %s" % (i + 1, s) for i, s in enumerate(samples)),
        topic=route.get("topic") or route.get("title", "这节课"),
        banned="、".join(route.get("banned", [])),
        style=style,
        ex_from=(char.get("example") or {}).get("from", "先把水烧开，再下面条。"),
        ex_to=(char.get("example") or {}).get("to", "「嗯……你先把水烧上——就当成给面烫个澡。」"),
    )


def user_prompt(node, fallback_lines, history, strict=False, marks=None, missing=None):
    draft = "\n".join("- " + l for l in fallback_lines)
    hist = ""
    if history:
        hist = "\n（你刚才已经讲过的话，不要重复）\n" + "\n".join("- " + h for h in history[-6:])
    strict_note = ""
    if strict:
        strict_note = "\n注意：上一版不合格。务必换成你自己的说法，不要照抄参考；至少 3 句。\n"
        if missing:
            strict_note += "并且这一次必须用上这些词里的至少一个：%s\n" % "、".join(missing)
    mark_note = ""
    if marks:
        mark_note = "\n语言标记（这段台词里必须至少出现一处）：%s\n" % "、".join(marks)
    avoid_note = ""
    if node.get("avoid"):
        avoid_note = "\n禁止出现的说法（出现就是讲错）：%s\n" % "、".join(node["avoid"])
    return """这一节的知识点（**这是给你看的备忘，不是台词，绝对不要念出来**）：
- 本节要点：{goal}

【参考句子】（只是知识点，措辞必须改写，不许逐句照抄）
{draft}
{hist}{mark_note}{avoid_note}{strict}
输出 JSON：{{"lines": [...]}}，2~4 句。""".format(
        goal=node.get("goal", ""),
        draft=draft,
        hist=hist,
        mark_note=mark_note,
        avoid_note=avoid_note,
        strict=strict_note,
    )


def teach(char, route, node, history=None, backend=None):
    """返回 {"lines": [...], "source": "cache"|"llm"|"fake"|"fallback", ...}

    顺序：预生成缓存 → 实时模型（有 Key）→ 静态讲稿。
    缓存优先的原因：没 Key 的玩家也能看到符合人设的台词。
    """
    fallback = [b["text"] for b in node.get("teach", [])]

    if os.environ.get("GAL_NO_CACHE") != "1":
        cached = teachcache.lookup(route, char["id"], node.get("id"))
        if cached:
            return {"lines": cached, "source": "cache", "why": "", "model": "cache"}

    prov = llm.provider()

    if prov == "fake":
        # 测试用：走同一条校验路径，只是不真的发请求
        cand = [("（%s）" % char["name"]) + fallback[0]] + fallback[1:]
        why = validate(cand, route.get("banned", []))
        if why:
            return {"lines": fallback, "source": "fallback", "why": "fake:" + why, "model": "fake"}
        return {"lines": cand, "source": "fake", "why": "", "model": "fake"}

    if prov == "mock":
        return {"lines": fallback, "source": "fallback", "why": "无 Key", "model": "mock"}

    banned = route.get("banned", [])
    samples = voice_samples(char)
    marks = MUST_MARKS.get(char["id"], [])
    sys_p = system_prompt(char, route)
    last = ""
    hint = None
    hist_lines = [h for h in (history or []) if isinstance(h, str) and len(h) >= 6]
    try:
        # 最多试三次：第三次只在小问题（漏讲/缺标记）时发生
        for attempt in range(3):
            user_p = user_prompt(
                node,
                fallback,
                history or [],
                strict=(attempt > 0),
                marks=marks,
                missing=hint,
            )
            data = llm.chat_json(sys_p, user_p, max_tokens=900)
            lines = _normalize_lines(data.get("lines") or [])
            # 硬规则：讲错 / 出戏 / 复读 / 抄样例 —— 必须重来，三次不过就退回静态稿
            hard = validate(
                lines,
                banned,
                draft=fallback,
                samples=samples,
                avoid=node.get("avoid"),
                history=hist_lines,
            )
            if hard:
                last = hard
                hint = marks
                print("[teacher] 第 %d 次不合格：%s" % (attempt + 1, hard))
                continue
            # 软规则：漏讲要点 / 缺口头标记 / 和前面重复 —— 重试一次，仍不行就接受
            blob = "".join(lines)
            miss_groups = [g for g in (node.get("must") or []) if not any(w in blob for w in g)]
            missing = style_marks(char, lines)
            dup = ""
            for l in lines:
                for h in hist_lines:
                    if len(l) >= 12 and len(h) >= 12 and checks.dice(l, h) >= 0.92:
                        dup = "和前面某句几乎一样"
                        break
                if dup:
                    break
            if not miss_groups and not missing and not dup:
                return {"lines": lines, "source": "llm", "why": "", "model": prov, "attempts": attempt + 1}
            if attempt > 0:
                notes = []
                if miss_groups:
                    notes.append("漏讲：" + "/".join(g[0] for g in miss_groups))
                if missing:
                    notes.append("缺标记：" + "/".join(missing))
                if dup:
                    notes.append(dup)
                return {"lines": lines, "source": "llm", "why": "；".join(notes), "model": prov, "attempts": attempt + 1}
            last = "漏讲/缺标记/重复"
            hint = (miss_groups[0][0] if miss_groups else None) or (missing[0] if missing else None)
            print("[teacher] 第 %d 次需重试（软）：%s" % (attempt + 1, hint or dup))
        return {"lines": fallback, "source": "fallback", "why": last, "model": prov}
    except Exception as e:
        return {"lines": fallback, "source": "fallback", "why": str(e)[:80], "model": prov}
