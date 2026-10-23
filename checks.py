"""四条硬校验的 Python 版：与 web 版 engine/checks.mjs 行为一致。

原则：模型每轮只拿到「对话 + 用户刚说的话 + 禁用术语表」，
教材、知识点、参考答案一个字都不发；输出必须挂回用户原话。
"""

import re

_PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)


def strip_all(s):
    """去掉空白与标点，只留实义字符，用于逐字比对。"""
    return _PUNCT.sub("", s or "").lower()


def _bigrams(s):
    return [s[i:i + 2] for i in range(len(s) - 1)]


def dice(a, b):
    """Sørensen–Dice 字符二元组相似度，零依赖、可复现。"""
    A, B = _bigrams(strip_all(a)), _bigrams(strip_all(b))
    if not A or not B:
        return 0.0
    bag = {}
    for x in A:
        bag[x] = bag.get(x, 0) + 1
    hit = 0
    for y in B:
        if bag.get(y, 0) > 0:
            hit += 1
            bag[y] -= 1
    return 2.0 * hit / (len(A) + len(B))


def coverage(knowledge, rubric_ids, text):
    """知识点覆盖度。只在我们这一侧算，永远不发给模型。"""
    t = strip_all(text)
    hits, missing = [], []
    for rid in rubric_ids:
        k = knowledge.get(rid, {})
        ok = any(strip_all(a) and strip_all(a) in t for a in k.get("aliases", []))
        (hits if ok else missing).append(rid)
    total = len(rubric_ids) or 1
    return {
        "ratio": len(hits) / total,
        "hits": hits,
        "missing": missing,
        "hit_labels": [knowledge.get(i, {}).get("label", i) for i in hits],
        "missing_labels": [knowledge.get(i, {}).get("label", i) for i in missing],
    }


def audit(ai, user_text, all_user_text, banned):
    """① 引用逐字命中 ② 不懂的词必须出自用户 ③ 术语不越界 ④ 复述相似度。"""
    issues = []
    quote = strip_all(ai.get("quote", ""))
    said_all = strip_all(all_user_text)
    said_now = strip_all(user_text)

    quote_ok = len(quote) >= 2 and quote in said_all
    if not quote_ok:
        issues.append("quote_not_verbatim")

    terms = ai.get("unknown_terms") or []
    terms_ok = all(strip_all(t) in said_now or strip_all(t) in said_all for t in terms)
    if not terms_ok:
        issues.append("unknown_term_not_from_user")

    out = (ai.get("restate") or "") + (ai.get("question") or "")
    leaks = [w for w in banned if w in out and strip_all(w) not in said_all]
    if leaks:
        issues.append("banned_term_leak")

    restate_sim = dice(ai.get("restate", ""), user_text)

    return {
        "ok": not issues,
        "issues": issues,
        "quote_ok": quote_ok,
        "terms_ok": terms_ok,
        "leaks": leaks,
        "restate_sim": restate_sim,
    }


def fallback_ask(user_text):
    """服务端兜底追问：不经过模型，因此不可能泄漏任何知识。"""
    clean = (user_text or "").strip()
    return {
        "restate": "……我努力想了一下，只抓住了一个模糊的影子。",
        "quote": clean[:24],
        "unknown_terms": [],
        "question": "你能不能用一件生活里的事，再讲一遍给我听？",
        "fallback": True,
    }


def judge(route, rubric_ids, scene_text, user_text, all_user_text, ai):
    """判定的单一实现：Ren'Py、web、测试共用同一套规则。"""
    cov = coverage(route.get("knowledge", {}), rubric_ids, scene_text if scene_text is not None else user_text)
    rep = audit(ai, user_text, all_user_text, route.get("banned", []))

    verdict = "partial"
    if not rep["ok"]:
        verdict = "rejected"
    elif rep["restate_sim"] < route.get("passRestateSim", 0.3):
        verdict = "confused"
    elif cov["ratio"] >= route.get("passCoverage", 0.6):
        verdict = "pass"

    return {
        "verdict": verdict,
        "coverage": cov["ratio"],
        "restate_sim": rep["restate_sim"],
        "cov": cov,
        "audit": rep,
        "spoken": ai if rep["ok"] else fallback_ask(user_text),
    }
