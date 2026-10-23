testsuite global:
    before testcase:
        $ _test.transition_timeout = 0.05
        $ _test.timeout = 40.0

        if not screen "main_menu":
            run MainMenu(confirm=False)

    teardown:
        exit


# 完整跑通一条路线。主讲由 GAL_TEST_MENTOR 指定（claude/deepseek/gemini/grok/kimi/chatgpt），
# 剧情分叉由 TEST_FLOW 决定：gemini 多一道对照题，kimi 中途多一次复述。
testcase full_run:
    $ import os, json
    $ os.makedirs(os.path.join(renpy.config.basedir, "shots"), exist_ok=True)

    click "Start"

    # 问候（+ 角色专属开场旁白）
    advance
    $ renpy.screenshot(os.path.join(renpy.config.basedir, "shots", "00_%s_greet.png" % mentor_id))
    advance
    $ renpy.screenshot(os.path.join(renpy.config.basedir, "shots", "01_%s_intro.png" % mentor_id))
    advance
    advance
    $ renpy.screenshot(os.path.join(renpy.config.basedir, "shots", "01b_%s_teach.png" % mentor_id))

    if eval TEST_FLOW == "mid_reversal":
        $ _test_input_queue.extend(["反", "小步", "它先看脚下哪边最陡，然后往反方向迈一小步。", "它先找脚下最陡的那一边，然后往反方向迈一小步。这个动作它反复做很多次，位置越来越低，最后走到谷底、脚下平了就停住。步子太大会来回跳，太小又太慢。"])
    else:
        $ _test_input_queue.extend(["反", "小步", "它先找脚下最陡的那一边，然后往反方向迈一小步。这个动作它反复做很多次，位置越来越低，最后走到谷底、脚下平了就停住。步子太大会来回跳，太小又太慢。"])

    # 第一节末尾的难点选择题
    advance until screen "choice"
    $ renpy.screenshot(os.path.join(renpy.config.basedir, "shots", "02_%s_choice.png" % mentor_id))
    click "靠脚下这一点地面的倾斜，试探着走"

    # 第二节填空（队列自动填）→ 第三节选择题
    advance until screen "choice"
    click "因为脚下几乎平了，再走也低不了多少"

    # gemini 额外插了一道「对照」题
    if eval TEST_FLOW == "extra_choice":
        advance until screen "choice"
        click "一步一步走，每走一步重新看脚下"

    # 结尾反转（队列自动填）→ 结局
    advance until "错题本"
    $ renpy.screenshot(os.path.join(renpy.config.basedir, "shots", "03_%s_ending.png" % mentor_id))

    assert eval len(R.concepts) >= 5
    assert eval R.done == True
    assert eval len(R.nodes) >= 4

    # 假 LLM 模式：必须真的走了「人设生成 → 校验 → 采用」这条路径
    if eval os.environ.get("GAL_FAKE_LLM") == "1":
        assert eval R.stats.get("teach_llm", 0) > 0

    $ open(os.path.join(renpy.config.basedir, "shots", "state_%s.json" % mentor_id), "w", encoding="utf-8").write(json.dumps({"mentor": mentor_id, "flow": TEST_FLOW, "nodes": [n["id"] for n in R.nodes], "beats": R.stats["beats"], "teach_llm": R.stats.get("teach_llm", 0), "teach_lines": sum(len(n["teach"]) for n in R.nodes), "reversal_threshold": (R.variant.get("reversal_threshold") if R.variant else None), "concepts": R.concepts, "stuck": R.stuck, "stats": R.stats, "log": R.log}, ensure_ascii=False, indent=2))


