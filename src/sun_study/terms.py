"""The licence terms a subscriber buys under, as plain text.

The terms live in one place, ``site/terms.html``: the page the checkout
links to and a buyer accepts. Two things need the same words as text rather
than as a web page. The folder a practice unzips carries them as
``LICENSE.txt`` (``scripts/build_app.py``), and the window's About box shows
them under *Read the full terms* in a build that takes licence keys. Both
read the page through ``text`` so they cannot drift from it, or from each
other.

The executable carries the page at the root of its bundle (``Loriini.spec``),
where ``page`` looks for it; a checkout has it under ``site/``.
"""

from __future__ import annotations

import sys
import textwrap
from html.parser import HTMLParser
from pathlib import Path

from sun_study import PRODUCT

#: Where the current wording is published. Named on the first line of the
#: text, because a copy on a disk goes stale and the page does not.
ADDRESS = "https://loriini.app/terms"

#: The privacy note the terms make part of themselves, spelt out because a
#: relative link means nothing in a text file.
PRIVACY_ADDRESS = "https://loriini.app/privacy"

#: The page's file name, in the repository's ``site/`` and in the bundle.
PAGE_NAME = "terms.html"

#: How wide the text is set: a text file opened in Notepad, read at a glance.
WIDTH = 76


def page() -> Path | None:
    """The terms page, wherever this is running from, or ``None``.

    Two places, as for the LICENSE file (``sun_study.licence.file``):
    PyInstaller unpacks what it was given beside ``sys._MEIPASS``, and a
    checkout keeps the site two levels above this module. ``None`` when it
    is in neither, because a build whose terms did not make it in should
    still run; the About box then loses one button and nothing else.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        found = Path(bundled) / PAGE_NAME
    else:
        found = Path(__file__).resolve().parents[2] / "site" / PAGE_NAME
    return found if found.is_file() else None


class _TermsText(HTMLParser):
    """The words of the terms page, as a text file reads: headings on their
    own lines, paragraphs wrapped, list items numbered, links spelt out.
    Only what is inside ``<article>`` counts; the page's header and footer
    are navigation."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str]] = []
        self._inside = False
        self._tag: str | None = None
        self._text: list[str] = []
        self._item = 0
        self._list: str | None = None
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "article":
            self._inside = True
        if not self._inside:
            return
        if tag in ("ol", "ul"):
            self._list, self._item = tag, 0
        elif tag in ("h1", "h2", "p", "li", "span"):
            self._tag, self._text = tag, []
            if tag == "li":
                self._item += 1
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if href == "privacy.html":
                href = PRIVACY_ADDRESS
            self._href = href if href.startswith("http") else None

    def handle_endtag(self, tag: str) -> None:
        if tag == "article":
            self._inside = False
        if tag == "a" and self._href:
            self._text.append(f" ({self._href})")
            self._href = None
        if not self._inside or tag != self._tag:
            return
        text = " ".join("".join(self._text).split())
        if tag == "li":
            text = f"{self._item}. {text}" if self._list == "ol" else f"- {text}"
        self.blocks.append((tag, text))
        self._tag, self._text = None, []

    def handle_data(self, data: str) -> None:
        if self._inside and self._tag is not None:
            self._text.append(data)


def render(html: str) -> str:
    """The terms page's HTML as plain text, under a line saying where the
    current wording lives."""
    parser = _TermsText()
    parser.feed(html)
    lines = [f"{PRODUCT}: the licence terms, as at {ADDRESS}", ""]
    for tag, words in parser.blocks:
        if tag == "h1":
            lines += [words.upper(), "=" * len(words), ""]
        elif tag == "h2":
            lines += [words, "-" * len(words), ""]
        elif tag == "li":
            lines += [*textwrap.wrap(words, WIDTH, subsequent_indent="   "), ""]
        else:
            lines += [*textwrap.wrap(words, WIDTH), ""]
    return "\n".join(lines).rstrip() + "\n"


def text(source: Path | None = None) -> str | None:
    """The terms as plain text, or ``None`` where the page is not there."""
    found = source if source is not None else page()
    if found is None:
        return None
    try:
        return render(found.read_text(encoding="utf-8"))
    except OSError:  # pragma: no cover - unreadable file on a locked profile
        return None
