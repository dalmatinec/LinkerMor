"""Генерация заданий проверки.

Задания намеренно простые: цель — отсечь автоматические входы, а не
затруднить вход человеку. Проверка, которую трудно пройти, отпугивает
настоящих участников быстрее, чем спамеров.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from mod_captcha.models import CaptchaKind

#: Символы для проверки с выбором. Намеренно различимые между собой.
EMOJI_POOL = ("🍎", "🚗", "⚽", "🌵", "🔔", "🎈", "🐱", "🌙")


@dataclass(frozen=True, slots=True)
class Challenge:
    """Задание и его правильный ответ."""

    kind: str
    #: Вопрос для подстановки в текст проверки. Для кнопочной пуст.
    question: str
    answer: str
    #: Варианты ответа: каждый станет кнопкой.
    options: tuple[str, ...]


def generate(kind: str, *, rng: random.Random | None = None) -> Challenge:
    """Собрать задание указанного вида."""
    random_source = rng or random

    if kind == CaptchaKind.MATH:
        left = random_source.randint(2, 9)
        right = random_source.randint(2, 9)
        answer = str(left + right)
        options = _options(answer, _nearby_numbers(left + right, random_source), random_source)
        return Challenge(kind=kind, question=f"{left} + {right}", answer=answer, options=options)

    if kind == CaptchaKind.EMOJI:
        answer = random_source.choice(EMOJI_POOL)
        others = [emoji for emoji in EMOJI_POOL if emoji != answer]
        options = _options(answer, random_source.sample(others, 3), random_source)
        return Challenge(kind=kind, question=answer, answer=answer, options=options)

    return Challenge(kind=CaptchaKind.BUTTON, question="", answer="ok", options=("ok",))


def _nearby_numbers(correct: int, rng: random.Random) -> list[str]:
    """Неправильные варианты рядом с верным: угадать наугад труднее."""
    candidates = {correct + shift for shift in (-3, -2, -1, 1, 2, 3) if correct + shift > 0}
    return [str(value) for value in rng.sample(sorted(candidates), 3)]


def _options(answer: str, wrong: list[str], rng: random.Random) -> tuple[str, ...]:
    options = [answer, *wrong]
    rng.shuffle(options)
    return tuple(options)
