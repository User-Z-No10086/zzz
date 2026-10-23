screen hud():
    zorder 100

    if R is not None:
        frame:
            align (0.015, 0.02)
            padding (18, 12)
            background "#000000aa"

            vbox:
                spacing 6
                text "路线 [R.progress]" size 20 color "#cfe3ff"
                text "已听懂 [len(R.concepts)] 个概念" size 20 color "#9fe6c4"

                if R.last_cov is not None:
                    text "要点覆盖 [int(R.last_cov * 100)]%" size 20 color "#cfe3ff"

                if R.last_sim is not None:
                    text "复述相似 [int(R.last_sim * 100)]%" size 20 color "#ffd79a"


screen mentor_pick():
    modal True
    frame:
        align (0.5, 0.5)
        padding (28, 24)
        xmaximum 900

        vbox:
            spacing 10
            text "今晚谁来带这节补课" size 32
            text "同一间补习班：一位老师，一位学姐，两个同学，两个学妹。谁来讲，由你决定。" size 20 color "#c8d2e0"

            null height 10

            for c in CHARS["characters"]:
                textbutton "[c[name]]  ·  [c[role_cn]]  ·  [c[title]]":
                    action Return(c["id"])
                    text_size 22
