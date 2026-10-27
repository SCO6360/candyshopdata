"""Helpers for believable free text: template filling and human typing noise."""
from __future__ import annotations

import string

from .world import World


class _Safe(dict):
    def __missing__(self, key):
        return ""


def fill(template: str, **kw) -> str:
    return string.Formatter().vformat(template, (), _Safe(kw))


def typo(w: World, text: str, p: float = 0.2) -> str:
    """Make text look typed by a busy shop owner: dropped caps, swapped letters, no punctuation."""
    if not text or not w.chance(p):
        return text
    r = w.rng.random()
    if r < 0.35:
        return text.lower().rstrip(".")
    words = text.split(" ")
    for _ in range(w.rng.randint(1, 2)):
        i = w.rng.randrange(len(words))
        word = words[i]
        if len(word) > 4 and word.isalpha():
            j = w.rng.randrange(1, len(word) - 2)
            words[i] = word[:j] + word[j + 1] + word[j] + word[j + 2:]
    return " ".join(words)
