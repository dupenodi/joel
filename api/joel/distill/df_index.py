"""Document-frequency index + the burst noise filter (§7.3) — the IDF signal
that decides whether a long, rare-vocabulary tangent survives distillation
even when the LLM didn't tag it question/answer/resolution.

One corpus pass builds `token -> doc count`; persisted as JSON to
`data/canonical/df.json` so it costs nothing to rebuild alongside the
canonical JSONL it's derived from.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from joel.models import Burst

RARE_THRESHOLD = 0.02  # <2% of corpus docs
MIN_WORDS_FOR_LENGTH_KEEP = 30

_WORD = re.compile(r"\w{4,}")
CODE_TOKEN = re.compile(r"[A-Z][A-Z0-9_]{3,}|\w+\(\)|[a-z_]+\.[a-z_]{2,}|ERR\w*|=\s*\d|--\w+")


class DocFrequencyIndex:
    """`token -> doc count`, plus the total doc count needed to turn that
    into a frequency. Tokens are lowercased, `\\w{4,}` — short/common words
    (the, and, for) are cheap to skip and never the signal we want anyway.
    """

    def __init__(self, doc_counts: Counter[str] | None = None, total_docs: int = 0):
        self.doc_counts: Counter[str] = doc_counts if doc_counts is not None else Counter()
        self.total_docs = total_docs

    def frequency(self, token: str) -> float:
        if self.total_docs == 0:
            return 0.0
        return self.doc_counts.get(token, 0) / self.total_docs

    def add_document(self, text: str) -> None:
        for token in {t.lower() for t in _WORD.findall(text)}:
            self.doc_counts[token] += 1
        self.total_docs += 1

    def to_dict(self) -> dict:
        return {"total_docs": self.total_docs, "doc_counts": dict(self.doc_counts)}

    @classmethod
    def from_dict(cls, data: dict) -> "DocFrequencyIndex":
        return cls(Counter(data.get("doc_counts", {})), int(data.get("total_docs", 0)))

    @classmethod
    def load(cls, path: Path) -> "DocFrequencyIndex":
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict()))


def has_rare_tokens(text: str, df: DocFrequencyIndex) -> bool:
    if CODE_TOKEN.search(text):
        return True
    tokens = [t.lower() for t in _WORD.findall(text)]
    return any(df.frequency(t) < RARE_THRESHOLD for t in tokens)


def keep_burst(b: Burst, df: DocFrequencyIndex) -> bool:
    """§7.3's rule, in priority order: the distiller's own role call wins,
    then human signal (reactions), then length + rare-vocabulary. Short,
    common, unreacted bursts ("sounds good, thanks!") are the ones this
    exists to drop.
    """
    if b.role in ("resolution", "answer", "question"):
        return True
    if b.has_reactions:
        return True
    if len(b.text.split()) >= MIN_WORDS_FOR_LENGTH_KEEP and has_rare_tokens(b.text, df):
        return True
    return False


__all__ = [
    "DocFrequencyIndex",
    "has_rare_tokens",
    "keep_burst",
    "RARE_THRESHOLD",
    "MIN_WORDS_FOR_LENGTH_KEEP",
    "CODE_TOKEN",
]
