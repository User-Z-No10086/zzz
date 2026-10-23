default R = None
default MC = None
default mentor_id = "claude"
default route_key = "gradient-descent"

label start:
    scene bg corridor
    with fade

    if renpy.is_in_test():
        $ route_key = TEST_ROUTE
        $ mentor_id = TEST_MENTOR
        $ MC = mk_char(mentor_id)
        $ set_expr(mentor_id, "normal")
        $ renpy.say(MC, v("greet", fallback="……坐吧。今晚这节补课，我来带你走一遍。"))
    else:
        call course_select
        call choose_mentor

    if (not renpy.is_in_test()) or os.environ.get("GAL_TEST_SHOWMAP") == "1":
        call show_pathmap

    # AI 生成的课程没有角色分叉（分叉依赖手写节点 id）
    $ _variant = {} if ROUTES[route_key].get("generated") else variant_of(mentor_id)
    $ R = Runner(ROUTES[route_key], _variant)
    $ _intro = _variant.get("intro", "")
    if _intro:
        $ renpy.say(None, narration_of(_intro))
    show screen hud

    while not R.done:
        call node_teach
        call node_trigger

    call ending
    return


label course_select:
    $ _pick = renpy.call_screen("course_hub")
    if _pick == "__new__":
        $ _topic = renpy.input("你想学什么？（AI 会联网找资料，现场排一条路线）", length=30, default="").strip()
        if _topic:
            $ renpy.notify("正在联网找资料，生成路线…（约 10~30 秒）")
            $ _res = E_planner.plan_route(_topic)
            if _res.get("ok"):
                $ reload_routes()
                $ route_key = _res["route"]["id"]
                $ renpy.notify("课程已生成：%s" % _res["route"]["title"])
            else:
                $ renpy.notify(_res.get("error", "生成失败"))
                $ route_key = "gradient-descent"
        else:
            $ route_key = "gradient-descent"
    elif _pick == "__back__":
        $ route_key = "gradient-descent"
    else:
        $ route_key = _pick
    return


label show_pathmap:
    $ _go = renpy.call_screen("pathmap", route=ROUTES[route_key], current=0)
    if _go == "back":
        jump start
    return


label choose_mentor:
    $ mentor_id = renpy.call_screen("mentor_pick")
    $ MC = mk_char(mentor_id)
    $ set_expr(mentor_id, "normal")
    $ renpy.say(MC, v("greet", fallback="……坐吧。今晚这节补课，我来带你走一遍。"))
    return


label node_teach:
    $ nd = R.node
    $ set_expr(mentor_id, "normal")

    $ renpy.say(None, narration_of(nd["narration"]))

    if not ROUTES[route_key].get("generated"):
        $ renpy.say(MC, vline("lead", R.i, fallback=""))

    python:
        made = teach_of(nd)
        for line in made["lines"]:
            renpy.say(MC, line)
            R.stats["beats"] += 1

    return


label node_trigger:
    $ R.phase = "trigger"
    $ nd = R.node
    $ t = nd.get("trigger")

    if t is None:
        $ R.advance()
        return

    if t["type"] == "choice":
        call trig_choice
    elif t["type"] == "blank":
        call trig_blank
    elif t["type"] == "reversal":
        call trig_reversal
    else:
        $ R.advance()
        return

    $ R.credit(nd.get("covers"))
    $ R.advance()
    return


# —— 难点：选择题 ——
label trig_choice:
    $ set_expr(mentor_id, "angry")
    $ renpy.say(MC, v("badge", fallback="这里最容易错。先问一句。"))
    $ renpy.say(MC, t["q"])

    $ items = [(opt, i) for i, opt in enumerate(t["options"])]
    $ picked = False

    while not picked:
        $ choice = renpy.display_menu(items)
        $ R.stats["answers"] += 1

        if choice == t["answer"]:
            $ picked = True
        else:
            $ R.stats["wrong"] += 1
            $ set_expr(mentor_id, "angry")
            $ renpy.say(MC, v("wrong", fallback="不对。再看一眼题目。"))

    $ set_expr(mentor_id, "happy")
    $ renpy.say(MC, v("pass", fallback="对。"))
    $ renpy.say(MC, t.get("explain", "记住了。"))
    return


# —— 难点：填空 ——
label trig_blank:
    $ set_expr(mentor_id, "angry")
    $ renpy.say(MC, t["q"])

    $ picked = False

    while not picked:
        python:
            filled = []
            for idx in range(len(t["blanks"])):
                filled.append(ask_text(u"第 %d 空：" % (idx + 1), length=24))

        python:
            picked = True
            for got, blank in zip(filled, t["blanks"]):
                accepts = blank.get("accept") or [blank["answer"]]
                if not any(norm(got) == norm(a) or (norm(a) and norm(a) in norm(got)) for a in accepts):
                    picked = False

        if not picked:
            $ R.stats["wrong"] += 1
            $ renpy.say(MC, v("wrong", fallback="还差一点。再想想。"))

    $ set_expr(mentor_id, "happy")
    $ renpy.say(MC, v("pass", fallback="对。"))
    $ renpy.say(MC, t.get("explain", "对，就是这样。"))
    return


# —— 结尾：反转（用户讲给 AI 听） ——
label trig_reversal:
    $ set_expr(mentor_id, "shy")
    $ renpy.say(None, narration_of(t.get("narration", "")))
    $ renpy.say(MC, v("reversal", fallback=t.get("prompt", "")))

    $ passed = False
    $ tries = 0

    while not passed:
        python:
            spoken = ask_text(u"讲给%s听（这一轮要说完）：" % CHAR_BY_ID[mentor_id]["name"], length=800)

        if len(spoken) < 4:
            $ renpy.say(MC, "……你什么都没说。")
        else:
            python:
                tries += 1
                R.all_user_text += "\n" + spoken
                R.dialogue.append({"role": "user", "text": spoken})

                ai = E_novice.novice(
                    spoken,
                    R.dialogue,
                    R.route.get("banned", []),
                    R.known_terms(),
                    CHAR_BY_ID[mentor_id]["name"],
                    persona=CHAR_BY_ID[mentor_id].get("persona", ""),
                )
                j = E_checks.judge(R.route, t.get("rubric", []), R.all_user_text, spoken, R.all_user_text, ai)

                R.last_cov = j["coverage"]
                R.last_sim = j["restate_sim"]
                if j["verdict"] == "rejected":
                    R.stats["rejected"] += 1

                threshold = t.get("passCoverage", R.route.get("passCoverage", 0.6))
                # 分叉：某些角色对反转更严（比如 Grok）或更宽容（比如 DeepSeek）
                if R.i == len(R.nodes) - 1 and R.variant.get("reversal_threshold"):
                    threshold = R.variant["reversal_threshold"]
                passed = (
                    j["audit"]["ok"]
                    and j["restate_sim"] >= R.route.get("passRestateSim", 0.3)
                    and j["coverage"] >= threshold
                )

                R.log.append({
                    "verdict": j["verdict"],
                    "coverage": j["coverage"],
                    "restate": j["restate_sim"],
                    "missing": j["cov"]["missing"],
                })
                if not passed:
                    R.mark_stuck(j["cov"]["missing"])

            if passed:
                $ set_expr(mentor_id, "happy")
            else:
                $ set_expr(mentor_id, "normal")

            if not passed and j["verdict"] == "confused":
                $ renpy.say(MC, v("confused", fallback="……我没听清。"))

            $ renpy.say(MC, j["spoken"]["restate"])
            $ renpy.say(MC, j["spoken"]["question"])

            if not passed:
                $ renpy.say(MC, "（还没讲到：%s）" % "、".join(j["cov"]["missing_labels"]))

    $ R.stats["passes"] += 1
    $ set_expr(mentor_id, "happy")
    $ renpy.say(MC, t.get("passLine", ""))
    return


label ending:
    hide screen hud
    $ set_expr(mentor_id, "happy")

    $ renpy.say(None, "下课铃响了。走廊灯一盏一盏灭下去，值日生推着拖把从门口经过。")
    $ renpy.say(MC, v("ending1", fallback="下课了。你刚才讲的那些，我都记下来了。"))
    $ renpy.say(MC, v("ending2", fallback="而且这一次不是你听我讲——是你讲给我。所以它才是你的。"))

    $ renpy.say(None, "这次的错题本：%s" % ("、".join(R.concepts) if R.concepts else "（什么也没记下）"))

    if R.stuck:
        $ renpy.say(None, "你卡住过的地方：%s" % "、".join([R.route["knowledge"].get(k, {}).get("label", k) for k in R.stuck]))

    $ renpy.say(MC, "明天别忘了交作业。")
    return

