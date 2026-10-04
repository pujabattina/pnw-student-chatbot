from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class ParsedFragment:
    locator: str
    text: str
    excerpt: str
    extraction_status: str = "interpretable"


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_html(raw_html: str) -> str:
    class _HTMLTextExtractor(HTMLParser):
        _ignored_tags = {
            "head",
            "footer",
            "iframe",
            "nav",
            "noscript",
            "script",
            "style",
            "template",
        }
        _void_tags = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
        _boundary_tags = {
            "article",
            "div",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "main",
            "ol",
            "p",
            "section",
            "td",
            "th",
            "tr",
            "ul",
        }
        _boilerplate_marker = re.compile(
            r"(?:^|[-_\s])(?:"
            r"ad-banner|advertisement|analytics|breadcrumb|breadcrumbs|"
            r"cookie-banner|cookie-consent|cookie-notice|cookie-preferences|"
            r"footer|navigation|navbar|tracking|tracking-pixel|tracker"
            r")(?:$|[-_\s])"
        )

        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.ignored_stack: list[str] = []

        def handle_data(self, data: str) -> None:
            if data and not self.ignored_stack:
                self.parts.append(data)

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if self.ignored_stack:
                if tag not in self._void_tags:
                    self.ignored_stack.append(tag)
                return

            attributes = dict(attrs)
            role = (attributes.get("role") or "").lower()
            style = (attributes.get("style") or "").lower()
            markers = " ".join(
                (attributes.get(name) or "").lower() for name in ("class", "id", "aria-label")
            )
            is_hidden = (
                "hidden" in attributes
                or (attributes.get("aria-hidden") or "").lower() == "true"
                or bool(
                    re.search(
                        r"(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))",
                        style,
                    )
                )
            )
            is_boilerplate = role in {"contentinfo", "navigation"} or bool(
                self._boilerplate_marker.search(markers)
            )
            if tag in self._ignored_tags or is_hidden or is_boilerplate:
                if tag not in self._void_tags:
                    self.ignored_stack.append(tag)
                return

            if tag == "br":
                self.parts.append("\n")
            elif tag in self._boundary_tags:
                self.parts.append("\n")

        def handle_endtag(self, tag: str) -> None:
            if self.ignored_stack:
                for index in range(len(self.ignored_stack) - 1, -1, -1):
                    if self.ignored_stack[index] == tag:
                        del self.ignored_stack[index:]
                        break
                return

            if tag in self._boundary_tags:
                self.parts.append("\n")

    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    parser.close()
    return _normalize_whitespace("\n".join(parser.parts))


def _detect_locator(value: str) -> str:
    lowered = value.lower()
    if "table" in lowered:
        return "table"
    if "pdf" in lowered:
        return "pdf"
    if "attachment" in lowered:
        return "attachment"
    if "section" in lowered:
        return "section"
    return "document"


def _split_with_sections(value: str) -> list[tuple[str, str]]:
    if not value:
        return []

    normalized = _normalize_whitespace(value)
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    if len(sentences) <= 1:
        return [("document", normalized)]

    sections: list[tuple[str, str]] = []
    current: list[str] = []
    current_name = "document"
    for sentence in sentences:
        if len(sentence) < 120 and sentence.lower().startswith(("section ", "table ", "appendix ")):
            if current:
                sections.append((current_name, " ".join(current)))
            current_name = _detect_locator(sentence)
            current = [sentence]
            continue
        current.append(sentence)
    if current:
        sections.append((current_name, " ".join(current)))
    return sections or [("document", normalized)]


def parse_document(
    content: str,
    *,
    media_type: str | None = None,
    source_url: str | None = None,
) -> list[ParsedFragment]:
    """Parse a source document into a small set of interpretable fragments."""
    if not content or not content.strip():
        return [
            ParsedFragment(
                locator="document", text="", excerpt="", extraction_status="uninterpretable"
            )
        ]

    kind = (media_type or "").lower()
    source = (source_url or "").lower()

    if "html" in kind or source.endswith(".html") or source.endswith(".htm"):
        cleaned = _strip_html(content)
        if not cleaned:
            return [
                ParsedFragment(
                    locator="document", text="", excerpt="", extraction_status="uninterpretable"
                )
            ]
        candidates: list[ParsedFragment] = []
        for locator, text in _split_with_sections(cleaned):
            excerpt = text[:220]
            candidates.append(ParsedFragment(locator=locator, text=text, excerpt=excerpt))
        return candidates or [
            ParsedFragment(locator="document", text=cleaned, excerpt=cleaned[:220])
        ]

    if "pdf" in kind or source.endswith(".pdf"):
        cleaned = _normalize_whitespace(content)
        return [ParsedFragment(locator="pdf", text=cleaned, excerpt=cleaned[:220])]

    if "text" in kind or "json" in kind or source.endswith(".txt") or source.endswith(".json"):
        cleaned = _normalize_whitespace(content)
        return [ParsedFragment(locator="document", text=cleaned, excerpt=cleaned[:220])]

    cleaned = _normalize_whitespace(content)
    return [ParsedFragment(locator=_detect_locator(cleaned), text=cleaned, excerpt=cleaned[:220])]


def chunk_text(
    text: str,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 200,
) -> list[str]:
    """Split long text into overlapping chunks suitable for lexical and embedding search."""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    if overlap_chars < 0:
        raise ValueError("overlap_chars cannot be negative.")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars.")

    normalized = _normalize_whitespace(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    step = max_chars - overlap_chars
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start += step
    return chunks


def chunk_fragments(fragments: list[ParsedFragment]) -> list[ParsedFragment]:
    """Chunk any large parsed fragment and preserve the parent locator."""
    chunked: list[ParsedFragment] = []
    for fragment in fragments:
        if not fragment.text:
            continue
        parts = chunk_text(fragment.text)
        if len(parts) == 1:
            chunked.append(fragment)
            continue
        for index, part in enumerate(parts):
            chunked.append(
                ParsedFragment(
                    locator=f"{fragment.locator}#chunk-{index + 1}",
                    text=part,
                    excerpt=part[:220],
                    extraction_status=fragment.extraction_status,
                )
            )
    return chunked


__all__ = [
    "ParsedFragment",
    "chunk_fragments",
    "chunk_text",
    "parse_document",
]
