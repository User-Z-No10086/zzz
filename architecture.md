# 架构与设计取舍

## 一、分层的理由

```
剧本层（.rpy）      负责演出：谁在说话、什么时候考你、什么时候反转
   ↓ 只调函数，不写业务
引擎层（.py）       负责判定：讲解怎么生成、答得对不对、有没有胡说
   ↓ 纯标准库
内容层（.json）     负责数据：角色卡、课程、台词缓存
```

引擎层是纯 Python（无第三方依赖），可以直接`python tools/eval_*.py` 跑评测，
不需要启动 Ren'Py。改教学逻辑时不用碰剧本，改演出时不用碰判定。

## 二、一次「讲解」的完整链路

```
node_teach（script.rpy）
  └─ teach_of(node)                       gal_setup.rpy，同一角色同一节只算一次
       └─ teacher.teach(char, route, node)
            ├─ 1. 查缓存 teachcache.lookup()        命中 → source="cache"
            ├─ 2. 组装 system prompt              人设 + 语气样例 + 专属改写示范 + 硬性要求
            ├─ 3. 组装 user prompt                事实底稿 + 语言标记 + 禁止说法
            ├─ 4. 调模型 llm.chat_json()
            ├─ 5. 硬校验 validate()                讲错/出戏/复读/抄样例 → 重来
            ├─ 6. 软校验                           漏讲要点/缺口头标记/与前面重复 → 重试一次后接受
            └─ 7. 三次不过 → 退回 JSON 里写死的讲稿
```

**为什么硬软分开**：曾经把「口头禅只能出现一次」写成硬规则，结果 Gemini 的
「一面/另一面」是它的核心句式，直接被判重复，生成率掉到 68%。分开之后生成率回到 90%+，
人设也没丢。**漏讲比讲错轻**——漏讲可以接受，讲错必须拦。

## 三、反转判定：四条硬校验

反转时 NPC 变成初学者，输出必须挂回玩家原话：

| 校验 | 拦什么 | 实现 |
|---|---|---|
| `quote_not_verbatim` | 编一句你没说过的话当依据 | 去掉标点后做字符串包含 |
| `unknown_term_not_from_user` | 假装不懂一个你没提过的词 | 词必须出现在玩家发言里 |
| `banned_term_leak` | 说出你没亲口讲过的术语 | 术语表逐个比对 |
| 复述相似度 < 阈值 | 判定“没听懂” | 字符二元组 Dice 系数 |

全过之后才是 `partial / pass`，按要点覆盖度分流。任何一条不过 → `rejected` → 换成模板追问，
**绝不让模型用编造的引用糊弄过去**。

## 四、课程生成

`planner.plan_route(topic)`：

1. `llm.chat_json_web()` 调智谱并开 `web_search` 工具
2. 要求模型输出固定结构的 route JSON（节点/讲解/触发/知识点别名/术语表）
3. `_validate()` 检查：≥2 节、最后一节必须是 reversal、至少一道 choice/blank、
   banned 非空、每个节点有 teach
4. 不合规 → 把错误回灌给模型重试（最多 3 次）
5. 落盘 `content/route-<slug>.json`，`reload_routes()` 后出现在课程列表

生成课程**不走角色分叉**（分叉配置里写的是手写节点 id，如 n1/n2），
也不会进台词缓存，所以每节都会实时调模型。

## 五、缓存与指纹

`teachcache` 把模型生成好的讲解按 `课程id → 角色id → 节点id` 存成 JSON，
并记录课程内容的 SHA1 指纹（节点讲解、must/avoid、知识点、术语表）。
课程 JSON 一改，指纹变化，旧缓存自动失效——避免“改了课但还在用旧台词”。

用途：让没有 API Key 的玩家也能看到符合人设的讲解，而不是退回通用稿。

## 六、角色分叉（仅手写课程）

在 `characters.json` 的 `variant` 里配置：

| 字段 | 作用 | 例子 |
|---|---|---|
| `extra_teach` | 某节多讲几句 | DeepSeek 每节多一个比方 |
| `insert_after` | 某节后插一整节 | Gemini 插「对照·两种说法」，Kimi 插「小测·讲一半」 |
| `reversal_threshold` | 改反转通过门槛 | Grok 0.7（苛刻）/ DeepSeek 0.5（宽容） |
| `intro` | 角色专属开场旁白 | 六人各一句 |

## 七、扩展点

- **加一门手写课**：复制 `content/route-gradient.json`，改节点与知识点，丢进 `content/`
- **加一位角色**：`characters.json` 里加条目（人设/台词/`style_prompt`/`example`），
  放立绘到 `images/characters/<id>/normal.png`
- **换模型**：`engine/llm.py` 支持任何 OpenAI 兼容端点，加一组环境变量即可
- **改判分口径**：`engine/checks.py` 里 `coverage()` / `dice()`，纯函数，改完跑评测脚本对比
