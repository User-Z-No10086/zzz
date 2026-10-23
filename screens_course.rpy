## 课程选择 + 学习路径图
##
## 注意：Ren'Py 的字符串插值 [x] 只支持简单变量，不支持 [dict[key]] 或函数调用。
## 所以这里所有展示文本都先在 Python 里拼好，再交给 text 显示。

screen course_hub():
    modal True
    frame:
        align (0.5, 0.5)
        padding (30, 26)
        xmaximum 1000
        ymaximum 820

        vbox:
            spacing 12
            text "今晚补哪门课" size 34
            text "选一门现成的，或者告诉 AI 你想学什么——它会联网找资料，现场给你排一条路线。" size 20 color "#c8d2e0"

            null height 6

            viewport:
                ymaximum 480
                scrollbars "vertical"
                mousewheel True
                vbox:
                    spacing 8
                    for r in ROUTE_LIST:
                        $ _row = "【%s】%d 节 · %s" % (r["title"], r["nodes"], r["tagline"])
                        textbutton "[_row]":
                            action Return(r["id"])
                            text_size 21

            null height 6
            textbutton "＋ 新建课程（AI 联网生成）":
                action Return("__new__")
                text_size 22
                text_color "#ffd479"

            textbutton "返回":
                action Return("__back__")
                text_size 19


screen pathmap(route, current):
    modal True
    frame:
        align (0.5, 0.5)
        padding (30, 26)
        xmaximum 1080
        ymaximum 860
        background "#0d131fee"

        vbox:
            spacing 10
            $ _title = route.get("title") or ""
            $ _tag = route.get("tagline") or ""
            text "[_title]" size 32
            text "[_tag]" size 19 color "#a9b7c9"

            if route.get("generated"):
                $ _src = len(route.get("_sources") or [])
                text "AI 联网生成 · 参考 [_src] 条资料" size 17 color "#8fd9b6"

            null height 6

            viewport:
                ymaximum 520
                scrollbars "vertical"
                mousewheel True
                vbox:
                    spacing 4
                    $ idx = 0
                    for n in route["nodes"]:
                        $ _t = n.get("trigger") or {}
                        $ _badge = {"choice": "选择题", "blank": "填空", "reversal": "反转"}.get(_t.get("type"), "讲解")
                        $ _mark = "●" if idx == current else ("○" if idx > current else "✓")
                        $ _color = "#7fe3b0" if idx == current else "#d5deea"
                        $ _head = "%s %d. %s" % (_mark, idx + 1, n.get("title") or "")
                        $ _sub = "     目标：%s · 触发：%s" % (n.get("goal") or "", _badge)
                        text "[_head]" size 22 color _color
                        text "[_sub]" size 17 color "#8f9fb2"
                        $ idx += 1

            null height 8
            hbox:
                spacing 14
                textbutton "开始 / 继续":
                    action Return("go")
                    text_size 22
                textbutton "返回课程列表":
                    action Return("back")
                    text_size 19
