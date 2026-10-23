"""小林：被清空课程知识的初学者。只准提问，必须引用玩家原话。

两种后端：
  mock     —— 零依赖规则版（无 API Key 也能跑完整流程）
  deepseek —— OpenAI 兼容接口，真实 LLM 扮演初学者
"""

import os
import re

from . import llm

SYSTEM = """你叫{name}，是一个刚刚被造出来的学习型机器人。

你的处境：
- 你对这个世界几乎一无所知。关于这门课的一切，你脑子里都是空的。
- 你是学生，玩家是老师。你唯一能做的是：努力听懂玩家说的话，然后提出你听不懂的地方。
- 你不许解释任何东西，不许讲课，不许给出答案，不许下结论。
- 保留下你原来的说话习惯（下面有描述），只是现在你什么都不会。
{persona}
必须遵守：
1. 每轮先复述你听懂的部分（用自己的话，可以很笨拙），再提一个问题。
2. 问题必须关于玩家刚说的某个具体词或某个地方。
3. 引用玩家的一句原话作为依据，逐字复制，不许改写。
4. 没从玩家那里听到解释的词，就老实说你不懂，不要假装懂。
5. 绝对不许使用这些词：{banned}。（除非玩家已经亲口用过）
6. 不要提到自己是 AI、模型、程序。
{known}
只输出 JSON：{{"restate": "...", "quote": "...", "unknown_terms": ["..."], "question": "..."}}"""


def _pick_quote(text):
    clean = (text or "").strip()
    first = re.split(r"[。！？!?\n]", clean)
    first = next((x for x in first if x.strip()), clean)
    q = first.strip()[:28]
    return q if len(q) >= 2 else clean[:2]


def mock_novice(user_text, banned, known_terms, name="小林"):
    clean = (user_text or "").strip()
    quote = _pick_quote(clean)

    if len(clean) < 8:
        return {
            "restate": "……我什么也没听清。",
            "quote": quote,
            "unknown_terms": [],
            "question": "你能再说一遍吗？慢一点也可以。",
        }

    tail = "……大概是这样吧？" if len(clean) > 48 else "我理解得对吗？"
    restate = "我听到的是：" + clean[:48] + tail

    term = next((w for w in banned if w in clean and w not in known_terms), None)
    ASK = [
        "你说的这些我好像能想象出一幅画面，但我不敢确定——能给我举一个具体的例子吗？",
        "等一下，我卡住了。如果换作是我，我大概第一步就不知道该做什么。第一步到底是什么？",
        "我能问一个很笨的问题吗？这件事，为什么不能直接一步走到最后？",
        "我好像抓住了点什么，又好像没有。能换一种说法再讲一次吗？",
    ]
    question = (
        f"你说的「{term}」，我脑子里完全没有这个东西。它到底指的是什么？"
        if term
        else ASK[len(clean) % len(ASK)]
    )
    return {"restate": restate, "quote": quote, "unknown_terms": [term] if term else [], "question": question}


def llm_novice(user_text, dialogue, banned, known_terms, name="小林", persona=""):
    known = f"6. 你已经学会的词：{'、'.join(known_terms)}。这些词你可以用。" if known_terms else ""
    persona_line = f"\n你原来的脾气：{persona}\n" if persona else ""
    sys = SYSTEM.format(name=name, banned="、".join(banned), known=known, persona=persona_line)

    history = "\n".join(
        f"{'玩家' if m['role'] == 'user' else name}：{m['text']}" for m in dialogue[-8:]
    )
    user = f"（对话记录）\n{history}\n\n（玩家刚刚说）\n{user_text}\n\n按 JSON 输出。"
    return llm.chat_json(sys, user, temperature=0.8, max_tokens=500)


def novice(user_text, dialogue=None, banned=None, known_terms=None, name="小林", backend=None, persona=""):
    banned = banned or []
    known_terms = known_terms or []
    # 自动化测试默认走规则版：不依赖网络，结果稳定
    if os.environ.get("GAL_NOVICE_MOCK") == "1":
        return mock_novice(user_text, banned, known_terms, name)
    prov = llm.provider()
    if prov in ("zhipu", "deepseek"):
        try:
            return llm_novice(user_text, dialogue or [], banned, known_terms, name, persona)
        except Exception as e:  # 任何失败都退回规则版，游戏不中断
            print(f"[novice] {prov} 失败，回退规则版：{e}")
    return mock_novice(user_text, banned, known_terms, name)
