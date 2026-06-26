from career_os.harness.explore_closure import explore_continuation_analyze, init_explore_closure


def _base_session() -> dict:
    """_base_session（内部函数 base session）的函数说明。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }


def test_continuation_none_when_gate_confirmed():
    """test_continuation_none_when_gate_confirmed（测试 continuation none when gate confirmed）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = {**_base_session(), "explore_gate_confirmed": True}
    assert explore_continuation_analyze(state) is None


def test_continuation_none_when_repeat_declined():
    """test_continuation_none_when_repeat_declined（测试 continuation none when repeat declined）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = _base_session()
    state["gates"] = {"flags": {"explore_repeat_declined": True}}
    assert explore_continuation_analyze(state) is None


def test_continuation_none_when_closure_completed():
    """test_continuation_none_when_closure_completed（测试 continuation none when closure completed）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    closure = init_explore_closure()
    closure["completed"] = True
    state = {**_base_session(), "explore_closure": closure}
    assert explore_continuation_analyze(state) is None


def test_continuation_dispatches_when_incomplete():
    """test_continuation_dispatches_when_incomplete（测试 continuation dispatches when incomplete）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = _base_session()
    result = explore_continuation_analyze(state)
    assert result is not None
    assert result["workers"] == ["identity"]
