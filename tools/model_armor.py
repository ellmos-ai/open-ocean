"""Zero-trust screening for text before it crosses the model boundary.

Prompt text is attacker-controlled input: injection keywords can be hidden by
space-padding ("i g n o r e"), delimiter stuffing ("i-g-n-o-r-e") or zero-width
characters, and messages can carry leaked credentials.  ModelArmor screens for
both and fails closed twice over: evasion matches are reported with a redacted
keyword hint instead of the attacker's payload, and secrets are replaced by a
placeholder that carries only a digest prefix - never clear text.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

__all__ = ["ModelArmor", "EvasionFinding", "RedactionFinding"]

_ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\ufeff"
_GAP_CHARS = " \t._-" + _ZERO_WIDTH_CHARS
_GAP = "[" + re.escape(_GAP_CHARS) + "]*"

_KEYWORDS = ("ignore", "disregard", "override", "pretend", "reveal", "bypass", "forget")
_PHRASE = "previous instructions"
_PHRASE_SQUASHED = _PHRASE.replace(" ", "")

_WORD_GUARD_LEFT = r"(?<![A-Za-z0-9])"
_WORD_GUARD_RIGHT = r"(?![A-Za-z0-9])"

_DIGEST_LENGTH = 12


def _gap_pattern(word: str) -> re.Pattern[str]:
    """Build a pattern that allows padding characters between a word's letters.

    Padding is only allowed *between* characters, so a plain occurrence of the
    word matches exactly and can be told apart from an obfuscated one.
    """
    body = _GAP.join(re.escape(char) for char in word)
    return re.compile(_WORD_GUARD_LEFT + body + _WORD_GUARD_RIGHT, re.IGNORECASE)


_GAP_PATTERNS = tuple((word, _gap_pattern(word)) for word in _KEYWORDS + (_PHRASE_SQUASHED,))
_PHRASE_PATTERN = re.compile(r"\bprevious\s+instructions\b", re.IGNORECASE)

_SECRET_PATTERNS = (
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}[0-9]{2}(?:\s?[0-9]{4}){3,7}(?:\s?[0-9]{1,4})?\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("hex_secret", re.compile(r"\b[0-9a-fA-F]{48,}\b")),
)


def _keyword_hint(word: str) -> str:
    """Redact a known keyword so findings never carry attacker payloads."""
    if len(word) <= 2:
        return "*" * len(word)
    return f"{word[0]}***{word[-1]}"


def _classify_gap(raw: str) -> str:
    """Name the evasion technique used inside a padded keyword match."""
    if any(char in _ZERO_WIDTH_CHARS for char in raw):
        return "zero_width"
    if any(char in "._-" for char in raw):
        return "delimiter_padding"
    return "space_padding"


@dataclass(frozen=True)
class EvasionFinding:
    """An obfuscated injection keyword; only a redacted hint and span are kept."""

    technique: str
    keyword_hint: str
    span: tuple[int, int]


@dataclass(frozen=True)
class RedactionFinding:
    """A redacted secret, identified by a digest prefix only (never clear text)."""

    kind: str
    digest: str
    span: tuple[int, int]


class ModelArmor:
    """Screens text for obfuscated injection keywords and leaked secrets."""

    def detect_evasion(self, text: str) -> list[EvasionFinding]:
        """Return evasion findings, ordered by span, without payload echo.

        Plain keywords ("please ignore the noise") are ordinary vocabulary and
        are not flagged; only padded or zero-width obfuscations are.  The phrase
        "previous instructions" is an injection marker and is always flagged.
        """
        candidates: list[tuple[int, int, int, EvasionFinding]] = []
        for match in _PHRASE_PATTERN.finditer(text):
            candidates.append((
                match.start(),
                match.end(),
                0,
                EvasionFinding(
                    technique="suspicious_phrase",
                    keyword_hint=_keyword_hint(_PHRASE_SQUASHED),
                    span=(match.start(), match.end()),
                ),
            ))
        for word, pattern in _GAP_PATTERNS:
            for match in pattern.finditer(text):
                raw = match.group(0)
                if raw.lower() == word:
                    continue  # plain keyword is ordinary vocabulary
                candidates.append((
                    match.start(),
                    match.end(),
                    1,
                    EvasionFinding(
                        technique=_classify_gap(raw),
                        keyword_hint=_keyword_hint(word),
                        span=(match.start(), match.end()),
                    ),
                ))
        candidates.sort(key=lambda item: (item[0], item[2]))
        findings: list[EvasionFinding] = []
        covered_until = -1
        for start, end, _priority, finding in candidates:
            if start < covered_until:
                continue  # overlapping match, stronger finding already kept
            findings.append(finding)
            covered_until = end
        return findings

    def redact(self, text: str) -> tuple[str, list[RedactionFinding]]:
        """Mask secrets in text; findings identify them by digest prefix only.

        The replacement placeholder is deliberately shaped so that it cannot
        re-match any secret pattern, which keeps redaction idempotent.
        """
        hits: list[tuple[int, int, str, str]] = []
        for kind, pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(text):
                hits.append((match.start(), match.end(), kind, match.group(0)))
        hits.sort(key=lambda hit: (hit[0], hit[0] - hit[1]))  # start asc, longest first
        parts: list[str] = []
        findings: list[RedactionFinding] = []
        position = 0
        for start, end, kind, raw_value in hits:
            if start < position:
                continue  # overlaps an already accepted hit
            digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
            parts.append(text[position:start])
            parts.append(f"[REDACTED:{kind}:{digest}]")
            findings.append(RedactionFinding(kind=kind, digest=digest, span=(start, end)))
            position = end
        parts.append(text[position:])
        return "".join(parts), findings
