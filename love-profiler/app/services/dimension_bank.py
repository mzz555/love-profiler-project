"""
Dimension bank -- 5-dimension question pools for Agent 1.
Each dimension has 4-6 scenario questions; AI picks from pool based on user status.
"""

from enum import Enum


class Dimension(str, Enum):
    SEPARATION_ANXIETY = "separation_anxiety"
    INTIMACY_COMFORT   = "intimacy_comfort"
    CONFLICT_PATTERN   = "conflict_pattern"
    NEEDS_EXPRESSION   = "needs_expression"
    ATTRIBUTION        = "attribution"


QUESTION_BANK: dict[Dimension, list[str]] = {
    Dimension.SEPARATION_ANXIETY: [
        "对方突然有一天回消息变得特别慢，跟平时不一样，你第一反应是？",
        "你发了一条很认真的消息给对方，但他只回了个“嗯”，那一刻你脑子里闪过的第一个念头是？",
        "你们在一起之后，对方第一次出差一周不在身边，你那一周是怎么过的？",
        "你给对方发了消息，两个小时了没回，你会怎么做——该干啸干啸，还是会忍不住做什么？",
        "有没有那种时候，你盯着他的头像，明明知道他在线却不回你，你当时在想什么？",
    ],
    Dimension.INTIMACY_COMFORT: [
        "你有没有遇到过一个人，一开始觉得特别好，但越走越近反而开始犹豫了？那时候是什么让你犹豫的？",
        "对方第一次对你说“我爱你”的时候，你的第一反应是什么？",
        "你身边有没有那种恋爱后什么事都跟对方说的人？你是那种吗，还是你更偏向于有些事自己消化？",
        "有没有那种时候，对方特别热情特别黏你，你反而有点想退一步的？当时什么感觉？",
        "你觉得在感情里，什么程度的依赖是让你舒服的？超过那个度你会什么感觉？",
    ],
    Dimension.CONFLICT_PATTERN: [
        "你跟对方吵得最凶的一次，是因为什么？你还记得你当时说了什么吗？",
        "吵完架之后，一般是谁先低头？如果对方不来找你，你能撑多久？",
        "有没有那种吵到一半，你突然就不想说了的时候？那个时候你在想什么？",
        '你吵架的时候，更容易说出“你总是……”“你从来不……”这种话，还是会选择沉默关机？',
        "你跟对方冷战过吗？冷战的时候你一般在干噸，心里在想什么？",
    ],
    Dimension.NEEDS_EXPRESSION: [
        "你心情不好需要对方陪的时候，你会怎么让他知道——是直接说，还是用什么方式暗示？",
        "你有没有说过那种话——嘴上说“没事”但其实心里很不好的？那一刻你希望对方怎么做？",
        "如果你很想对方但他正在忙，你会怎么办？",
        "你有没有因为对方没有“主动”做某件事而生气，但其实你从来没跟他说过你想要这个？",
        "你最近一次觉得“他根本不懂我”，是什么情况？你有没有告诉他你真正想要的是什么？",
    ],
    Dimension.ATTRIBUTION: [
        "你之前的感情为什么没走到最后？你现在回头看，觉得最主要的原因是什么？",
        "你有没有那种感觉——觉得“这个人什么都好但就是差了点什么”？那个差的到底是什么？",
        "感情里遇到问题，你第一反应更容易想“是不是我哪里不够好”，还是“他/她有问题”，还是“我们这件事没处理好”？",
        "你有没有觉得自己在感情里总是付出多一点的那个？那种感觉是什么时候开始的？",
    ],
}

# Round -> Dimension (round 1 = status selection, no dimension)
ROUND_DIMENSION: dict[int, Dimension | None] = {
    1: None,
    2: Dimension.SEPARATION_ANXIETY,
    3: Dimension.INTIMACY_COMFORT,
    4: Dimension.CONFLICT_PATTERN,
    5: Dimension.NEEDS_EXPRESSION,
}


def pick_question(dim: Dimension, used: list[str]) -> str:
    """Return the first unused question from the pool. Falls back to pool[0]."""
    pool = QUESTION_BANK[dim]
    for q in pool:
        if q not in used:
            return q
    return pool[0]


def get_dimension_for_round(round_num: int) -> Dimension | None:
    """Return the dimension to cover in the given round, or None for status round."""
    return ROUND_DIMENSION.get(round_num)
