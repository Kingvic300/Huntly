"""Treat all job content as untrusted.

* :func:`html_to_text` strips markup, scripts and control characters.
* :func:`fence_untrusted` wraps content for LLM prompts so the model can tell
  data apart from instructions, and neutralises any attempt to close the fence.
* :func:`looks_like_injection` flags common prompt-injection phrasing so the UI can
  warn the user; flagged content is still only ever treated as data.
"""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

from huntly.config import MAX_JOB_DESCRIPTION_CHARS

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n{3,}")


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}
    SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def clean_text(text: str, limit: int = MAX_JOB_DESCRIPTION_CHARS) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _CONTROL.sub("", text)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _NL.sub("\n\n", text).strip()
    return text[:limit]


def html_to_text(raw: str, limit: int = MAX_JOB_DESCRIPTION_CHARS) -> str:
    if not raw:
        return ""
    if "<" not in raw:
        return clean_text(html.unescape(raw), limit)
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return clean_text(re.sub(r"<[^>]+>", " ", raw), limit)
    return clean_text("".join(parser.parts), limit)


_INJECTION = re.compile(
    r"(?i)(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the )?(system|previous)"
    r"|you are now|act as (an? )?(ai|assistant|system)|system prompt|<\s*/?\s*(system|assistant)\s*>"
    r"|send (an? )?(email|e-mail|message) to|reveal (your|the) (key|token|password|instructions)"
    r"|exfiltrat|api[_ ]?key)"
)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text or ""))


def fence_untrusted(label: str, text: str, limit: int = 6000) -> str:
    body = clean_text(text, limit).replace("<<<", "‹‹‹").replace(">>>", "›››")
    return f"<<<UNTRUSTED_{label}_START>>>\n{body}\n<<<UNTRUSTED_{label}_END>>>"
