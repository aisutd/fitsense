"""Text clean-up applied before the food model, identically in training and at runtime."""

import re

_RULES = [
    (re.compile(r"(\d)\s*[x×]\b", re.I), r"\1"),           # "2x eggs" -> "2 eggs"
    (re.compile(r"(\d)([a-zA-Z])"), r"\1 \2"),             # "100ml" -> "100 ml", "1.5cups" -> "1.5 cups"
    (re.compile(r"\bw/\s*", re.I), "with "),               # "w/ rice" -> "with rice"
    (re.compile(r"[ \t]+"), " "),
]


def prepare_text(text: str) -> str:
    text = text.strip()
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text
