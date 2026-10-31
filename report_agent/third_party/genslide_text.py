"""Reused from mehdimo/GenSlide commit 3b847fc; license third_party/licenses/genslide-MIT.txt."""

import re


def _normalize(text: str) -> str:
    """
    Clean up extracted text:
        - Collapse runs of blank lines into a single blank line
        - Strip leading/trailing whitespace per line
        - Remove non-printable characters (except newlines and tabs)
    """
    # Remove non-printable chars except \n and \t
    text = re.sub(r"[^\x09\x0A\x20-\x7E\u00A0-\uFFFF]", "", text)
    # Strip each line
    lines = [line.strip() for line in text.splitlines()]
    # Collapse 3+ consecutive blank lines into 2
    cleaned: list[str] = []
    blank_count = 0
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def _parse_text(raw: str) -> str:
    return _normalize(raw)
