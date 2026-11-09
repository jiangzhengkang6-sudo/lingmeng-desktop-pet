from backend.app.voice_tool_planner import plan_voice_tool


def test_planner_maps_chinese_time_request() -> None:
    plan = plan_voice_tool("现在几点了？", session_id="s1")

    assert plan is not None
    assert plan.request.tool_name == "get_time"
    assert plan.request.arguments == {}
    assert plan.request.session_id == "s1"


def test_planner_maps_multilingual_time_requests() -> None:
    assert plan_voice_tool("What time is it?", session_id="s") is not None
    assert plan_voice_tool("今何時？", session_id="s") is not None
    assert plan_voice_tool("今天的日期是什么？", session_id="s") is not None


def test_planner_maps_whitelisted_application_request() -> None:
    plan = plan_voice_tool(
        "帮我打开记事本",
        session_id="s1",
        application_names=("记事本", "浏览器"),
    )

    assert plan is not None
    assert plan.request.tool_name == "open_application"
    assert plan.request.arguments == {"app_name": "记事本"}


def test_planner_ignores_unknown_application_and_normal_chat() -> None:
    assert plan_voice_tool("帮我打开记事本", session_id="s") is None
    assert plan_voice_tool("我们聊聊时间观念吧", session_id="s") is None


def test_planner_maps_music_intentions() -> None:
    play_commands = [
        "我想听音乐",
        "放首歌",
        "播放QQ音乐",
        "继续播放音乐",
        "帮我放一点歌",
    ]
    for command in play_commands:
        plan = plan_voice_tool(command, session_id="s")
        assert plan is not None, command
        assert plan.request.tool_name == "control_music", command
        assert plan.request.arguments == {"action": "play"}, command


def test_planner_maps_music_pause_intention() -> None:
    for command in ["暂停音乐", "停止播放歌曲", "先别放音乐了"]:
        plan = plan_voice_tool(command, session_id="s")
        assert plan is not None, command
        assert plan.request.tool_name == "control_music", command
        assert plan.request.arguments == {"action": "pause"}, command


def test_planner_does_not_treat_general_chat_as_music_control() -> None:
    assert plan_voice_tool("我们聊聊喜欢的音乐吧", session_id="s") is None
    assert plan_voice_tool("这首歌讲了什么故事", session_id="s") is None
