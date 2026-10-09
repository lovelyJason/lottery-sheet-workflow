"""Declarative play and rule choices shared by persistence and the GUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayOption:
    key: str
    label: str
    help_text: str


PLAY_OPTIONS = (
    PlayOption(
        "play1",
        "玩法一",
        "使用现有模板：A 列匹配期号，B 列补录特码。\n\n"
        "模板预警触发后，按 H1 尾数和 I1 生肖排除号码并执行投注。",
    ),
    PlayOption(
        "play2",
        "玩法二",
        "使用六平码模板：开奖号码第 1 至第 6 位依次补录到 B 至 G 列，"
        "特码补录到 H 列（合计 B:H）。\n\n"
        "玩法二可在逻辑一和逻辑二之间选择一种预警及投注规则。",
    ),
)

PLAY2_LOGIC_OPTIONS = (
    PlayOption(
        "logic1",
        "逻辑一",
        "由 J 列预警触发，投注参数读取 O / P 列。\n\n"
        "选号规则与玩法一一致。",
    ),
    PlayOption(
        "logic2",
        "逻辑二",
        "由 K 列预警触发。\n\n"
        "触发后读取同一期 R 列预测生肖（业务规则中的“R1生肖”），"
        "排除该生肖对应的所有号码，其余号码全部投注。",
    ),
)


PLAY_TEMPLATE_KINDS = {
    "play1": "play_one",
    "play2": "play_two",
}


def template_kind(play_mode: object) -> str:
    """Return the workbook layout required by a GUI play selection."""
    try:
        return PLAY_TEMPLATE_KINDS[play_mode]
    except (KeyError, TypeError):
        raise ValueError("玩法无效") from None


def normalize_play_selection(play: object, logic: object) -> tuple[str, str]:
    plays = {option.key for option in PLAY_OPTIONS}
    logics = {option.key for option in PLAY2_LOGIC_OPTIONS}
    return (
        play if isinstance(play, str) and play in plays else PLAY_OPTIONS[0].key,
        logic if isinstance(logic, str) and logic in logics else PLAY2_LOGIC_OPTIONS[0].key,
    )
