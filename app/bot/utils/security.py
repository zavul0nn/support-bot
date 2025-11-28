from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "SuspicionResult",
    "analyze_user_message",
    "sanitize_display_name",
    "SENSITIVE_PLACEHOLDER",
]

SENSITIVE_PLACEHOLDER = "[filtered]"

SEPARATOR_CHARS = " ._-/\\|•●‧·﹒٫＿‿⁃–—~`'\"()[]{}<>:,;!?*+=“”«»‹›"
SEPARATOR_CLASS = f"[{re.escape(SEPARATOR_CHARS)}\\s]"
SEPARATOR_RE = SEPARATOR_CLASS + "*"

HOMOGLYPHS = {
    "а": "a",
    "à": "a",
    "á": "a",
    "â": "a",
    "ä": "a",
    "å": "a",
    "ɑ": "a",
    "е": "e",
    "ё": "e",
    "ę": "e",
    "є": "e",
    "ӏ": "l",
    "Ӏ": "l",
    "ⅼ": "l",
    "ı": "i",
    "і": "i",
    "ї": "i",
    "ӏ": "l",
    "１": "1",
    "ᛕ": "k",
    "к": "k",
    "ｍ": "m",
    "м": "m",
    "о": "o",
    "ο": "o",
    "ө": "o",
    "р": "p",
    "ᴘ": "p",
    "с": "c",
    "ş": "s",
    "ѕ": "s",
    "ṡ": "s",
    "т": "t",
    "ᴛ": "t",
    "Ꞇ": "t",
    "у": "y",
    "ў": "y",
    "ӳ": "y",
    "г": "r",
    "ɢ": "g",
    "ԛ": "q",
    "п": "n",
    "ԋ": "b",
    "ь": "b",
    "ъ": "b",
}

HOMOGLYPH_TABLE = str.maketrans(HOMOGLYPHS)

INVITE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bt\.me/\+", re.IGNORECASE), "инвайт t.me/+"),
    (re.compile(r"\bt\.me/joinchat", re.IGNORECASE), "t.me/joinchat"),
    (re.compile(r"\bjoinchat\b", re.IGNORECASE), "ключевое слово joinchat"),
    (re.compile(r"\btg://", re.IGNORECASE), "протокол tg://"),
    (re.compile(r"\btelegram\.me\b", re.IGNORECASE), "домен telegram.me"),
)

GENERIC_TME_PATTERN = re.compile(r"\bt\.me/", re.IGNORECASE)
URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
OBF_TME_PATTERN = re.compile(r"\bt[\\s._\\-\\/|]*me\\b", re.IGNORECASE)
OBF_TELEGRAM_PATTERN = re.compile(r"te" + SEPARATOR_RE + r"le" + SEPARATOR_RE + r"gram", re.IGNORECASE)

SERVICE_KEYWORDS = (
    "telegram",
    "teleqram",
    "telegrarn",
    "teiegram",
    "teieqram",
    "support",
    "service",
    "notification",
    "system",
    "security",
    "safety",
    "moderation",
    "review",
    "compliance",
    "abuse",
    "spam",
    "report",
    "helpdesk",
    "admin",
    "official",
    "botfather",
    "телеграм",
    "служебн",
    "уведомлен",
    "поддержк",
    "безопасн",
    "модерац",
    "жалоб",
    "абуз",
)

SENSITIVE_SANITIZERS = (
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"\btg://\S*", re.IGNORECASE),
    re.compile(r"\bt\s*[\.\-]?\s*me\S*", re.IGNORECASE),
    re.compile(r"\bjoinchat\b", re.IGNORECASE),
    re.compile(OBF_TELEGRAM_PATTERN.pattern, re.IGNORECASE),
)


@dataclass(slots=True)
class SuspicionResult:
    high: list[str]
    medium: list[str]

    @property
    def triggered(self) -> bool:
        return bool(self.high or self.medium)

    @property
    def should_block(self) -> bool:
        return bool(self.high or len(self.medium) >= 2)

    def reasons(self) -> list[str]:
        return [*self.high, *self.medium]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return normalized.translate(HOMOGLYPH_TABLE)


def collapse_text(value: str) -> str:
    return re.sub(r"[^a-z0-9@а-яё]+", "", value)


def _check_patterns(
    value: str,
    patterns: Sequence[tuple[re.Pattern[str], str]],
    *,
    bucket: list[str],
    source: str,
) -> None:
    for pattern, description in patterns:
        if pattern.search(value):
            bucket.append(f"{source}: {description}")


def _check_keywords(
    collapsed: str,
    keywords: Iterable[str],
    *,
    bucket: list[str],
    source: str,
    severity: str,
) -> None:
    for keyword in keywords:
        if keyword in collapsed:
            bucket.append(f"{source}: ключевое слово «{keyword}» ({severity})")


def _append_if(condition: bool, reason: str, bucket: list[str], source: str) -> None:
    if condition:
        bucket.append(f"{source}: {reason}")


def analyze_user_message(
    *,
    full_name: str,
    username: str | None,
    message_text: str | None,
    entities_contains_link: bool = False,
) -> SuspicionResult:
    high: list[str] = []
    medium: list[str] = []

    def process_field(value: str, source: str, allow_url_medium: bool = False) -> None:
        normalized = normalize_text(value)
        collapsed = collapse_text(normalized)

        # Проверяем только t.me и связанные паттерны, остальные URL разрешены
        _check_patterns(normalized, INVITE_PATTERNS, bucket=high, source=source)
        _append_if(bool(OBF_TME_PATTERN.search(normalized)), "обфускация t.me", high, source)
        _append_if(bool(OBF_TELEGRAM_PATTERN.search(normalized)), "обфускация telegram", high, source)

        if GENERIC_TME_PATTERN.search(normalized):
            high.append(f"{source}: ссылка на t.me")

        if allow_url_medium and URL_PATTERN.search(value):
            pass

        if source in {"username", "full_name"}:
            _check_keywords(collapsed, SERVICE_KEYWORDS, bucket=high, source=source, severity="high")
            if source == "full_name" and "@" in value:
                medium.append(f"{source}: символ @ в имени")
        else:
            _check_keywords(collapsed, SERVICE_KEYWORDS, bucket=medium, source=source, severity="medium")

    if full_name:
        process_field(full_name, "full_name")

    if username:
        process_field(username, "username")

    if message_text:
        process_field(message_text, "text", allow_url_medium=True)

    if entities_contains_link:
        medium.append("text: обнаружена ссылка в сущностях")

    return SuspicionResult(high=high, medium=medium)


def sanitize_display_name(value: str | None, *, placeholder: str = SENSITIVE_PLACEHOLDER) -> str:
    if not value:
        return placeholder

    sanitized = value
    for pattern in SENSITIVE_SANITIZERS:
        sanitized = pattern.sub(" ", sanitized)

    sanitized = sanitized.replace("@", " ")
    sanitized = re.sub(SEPARATOR_CLASS + "+", " ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    if not sanitized:
        return placeholder

    return sanitized[:64]
