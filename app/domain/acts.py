"""Canonical registry of Indian statutes referenced by the system."""

from __future__ import annotations

import re

ACT_NAMES: dict[str, str] = {
    "IPC": "Indian Penal Code, 1860",
    "BNS": "Bharatiya Nyaya Sanhita, 2023",
    "CRPC": "Code of Criminal Procedure, 1973",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "IEA": "Indian Evidence Act, 1872",
    "BSA": "Bharatiya Sakshya Adhiniyam, 2023",
    "CPC": "Code of Civil Procedure, 1908",
    "CONSTITUTION": "Constitution of India",
}

# Alias -> canonical code. Longer aliases are matched first.
_ALIASES: dict[str, str] = {
    "indian penal code": "IPC",
    "penal code": "IPC",
    "i.p.c.": "IPC",
    "i.p.c": "IPC",
    "ipc": "IPC",
    "bharatiya nyaya sanhita": "BNS",
    "bns": "BNS",
    "code of criminal procedure": "CRPC",
    "criminal procedure code": "CRPC",
    "cr.p.c.": "CRPC",
    "cr.p.c": "CRPC",
    "crpc": "CRPC",
    "bharatiya nagarik suraksha sanhita": "BNSS",
    "bnss": "BNSS",
    "indian evidence act": "IEA",
    "evidence act": "IEA",
    "bharatiya sakshya adhiniyam": "BSA",
    "bsa": "BSA",
    "code of civil procedure": "CPC",
    "c.p.c.": "CPC",
    "cpc": "CPC",
    "constitution of india": "CONSTITUTION",
    "indian constitution": "CONSTITUTION",
    "constitution": "CONSTITUTION",
}

_ALIAS_PATTERN = "|".join(re.escape(a) for a in sorted(_ALIASES, key=len, reverse=True))
ACT_ALIAS_RE = re.compile(rf"(?<![a-z0-9])(?:{_ALIAS_PATTERN})(?![a-z0-9])", re.IGNORECASE)


def canonical_act(text: str | None) -> str | None:
    """Return the canonical code for an act name/alias, or None."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.upper() in ACT_NAMES:
        return stripped.upper()
    match = ACT_ALIAS_RE.search(stripped)
    return _ALIASES[match.group(0).lower()] if match else None


def act_display_name(code: str | None) -> str | None:
    if code is None:
        return None
    return ACT_NAMES.get(code.upper(), code)


def alias_to_code(alias: str) -> str:
    return _ALIASES[alias.lower()]
