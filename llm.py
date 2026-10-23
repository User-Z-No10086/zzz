"""统一的模型调用层：智谱 / DeepSeek / 假响应用于测试。

两家都是 OpenAI 兼容协议，差别只在 base_url、key、model 名。
所有调用都要求 JSON 输出；返回解析好的 dict。失败抛异常，由上层决定回退。
"""

import json
import os
import re
import ssl
import urllib.error
import urllib.request

# Ren'Py 自带的 Python 没有系统 CA 库，HTTPS 会报 CERTIFICATE_VERIFY_FAILED。
# 所以把 Mozilla 的 CA 包随游戏一起发（game/engine/cacert.pem）。
_HERE = os.path.dirname(os.path.abspath(__file__))


def _ssl_context():
    cafile = os.environ.get("GAL_CA_BUNDLE")
    if not cafile:
        cand = os.path.join(_HERE, "cacert.pem")
        if os.path.exists(cand):
            cafile = cand
    if cafile and os.path.exists(cafile):
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def provider():
    if os.environ.get("GAL_FAKE_LLM") == "1":
        return "fake"
    if os.environ.get("ZHIPU_API_KEY"):
        return "zhipu"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    return "mock"


def _config():
    p = provider()
    if p == "zhipu":
        return (
            p,
            os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/"),
            os.environ.get("ZHIPU_API_KEY", ""),
            os.environ.get("ZHIPU_MODEL", "glm-4-flash"),
        )
    if p == "deepseek":
        return (
            p,
            os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            os.environ.get("DEEPSEEK_API_KEY", ""),
            os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    return (p, "", "", "")


def _strip_fence(text):
    text = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if m:
        text = m.group(1).strip()
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        text = text[i:j + 1]
    return text


def _lenient_lines(text):
    """JSON 解析失败时的兜底：把带引号的片段或列表项抠出来。"""
    m = re.search(r'"lines"\s*:\s*\[(.*?)\]', text, re.S)
    body = m.group(1) if m else text
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
    out = []
    for p in parts:
        p = p.encode("utf-8").decode("unicode_escape") if "\\u" in p else p
        p = p.replace('\\"', '"').strip()
        if p:
            out.append(p)
    return out


def chat_json_web(system, user, temperature=0.8, max_tokens=2400, model=None):
    """带联网检索的 JSON 调用（智谱支持 web_search 工具）。

    返回 (data, sources)：data 是解析好的 JSON；sources 是检索到的原文片段列表。
    不支持检索的provider会退化成普通调用。
    """
    p, base, key, mdl = _config()
    if not key:
        raise RuntimeError("没有配置模型 Key")

    payload = {
        "model": model or os.environ.get("ZHIPU_SEARCH_MODEL", "glm-4-plus"),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "tools": [{"type": "web_search", "web_search": {"enable": True, "search_result": True}}],
    }

    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=180, context=_ssl_context()) as r:
        data = json.loads(r.read().decode("utf-8"))

    text = data["choices"][0]["message"].get("content") or ""
    sources = []
    for item in (data.get("web_search") or []):
        c = (item.get("content") or "").strip()
        if c:
            sources.append(c[:1200])
    return json.loads(_strip_fence(text)), sources


def chat_json(system, user, temperature=0.9, max_tokens=700, model=None):
    """要求模型输出 JSON，返回 dict。"""
    p, base, key, mdl = _config()
    if not key:
        raise RuntimeError("没有配置模型 Key")

    payload = {
        "model": model or mdl,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }

    def once(body):
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=90, context=_ssl_context()) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    try:
        text = once(payload)
    except urllib.error.HTTPError as e:
        # 有的模型不支持 response_format，退一步再试
        if e.code in (400, 422):
            payload.pop("response_format", None)
            text = once(payload)
        else:
            raise

    body = _strip_fence(text)
    try:
        return json.loads(body)
    except ValueError:
        # 模型偶尔吐出非法 JSON（引号没转义），尽量把台词捞出来
        lines = _lenient_lines(body)
        if lines:
            return {"lines": lines}
        raise
