"""Guards on the site's single source of copy.

site/src/content/ holds every word the marketing site says, and src/content/meta.js holds the
per-page SEO. The point is that a person edits one file and every place that quotes it follows.
These tests fail when that stops being true — when copy is written out again inside a component,
or when a page ships without the meta that search engines and link unfurlers read.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CONTENT = SITE / "src" / "content"
META = CONTENT / "meta.js"
COMPONENTS = SITE / "src" / "components"

# Wrappers with no copy of their own. A component here renders whatever it is handed; everything
# else has to take its words from src/content/.
STRUCTURAL = {"Reveal.jsx"}


def _entry_html_files() -> list[Path]:
    """Every page entry in site/, ignoring build output and dependencies."""
    pages = [SITE / "index.html"]
    pages += [
        page
        for page in sorted(SITE.glob("*/index.html"))
        if page.parent.name not in {"dist", "node_modules"}
    ]
    return pages


def test_every_page_has_meta_and_every_meta_entry_has_a_page():
    """A page with no entry in meta.js ships with no title; an entry with no page builds nothing."""
    meta = META.read_text(encoding="utf-8")
    declared = set(re.findall(r"html: '([^']+)'", meta))
    on_disk = {page.relative_to(SITE).as_posix() for page in _entry_html_files()}

    assert declared == on_disk, (
        "src/content/meta.js and the HTML entries in site/ disagree.\n"
        f"  declared in meta.js but not on disk: {sorted(declared - on_disk) or 'none'}\n"
        f"  on disk but missing from meta.js:    {sorted(on_disk - declared) or 'none'}"
    )

    # Every page needs all of these: vite.config.js writes the head from them and throws if one
    # is missing, but failing here names the page instead of failing a build.
    for field in ("path", "title", "description", "image", "imageAlt"):
        found = len(re.findall(rf"^    {field}:", meta, flags=re.MULTILINE))
        assert found == len(declared), (
            f"meta.js declares {len(declared)} pages but only {found} have a '{field}'. "
            "Every page needs one."
        )


def test_entry_html_carries_the_placeholder_and_nothing_hand_written():
    """The head is generated. A hand-written tag here would silently compete with it."""
    for page in _entry_html_files():
        html = page.read_text(encoding="utf-8")
        name = page.relative_to(ROOT)

        assert "<!--seo-->" in html, (
            f"{name} has no <!--seo--> placeholder, so vite has nowhere to write its title, "
            "description and social card."
        )
        stale = re.findall(r"<title>|<meta name=\"description\"|<meta property=\"og:", html)
        assert not stale, (
            f"{name} hand-writes {stale}, which the generated head already provides. Edit "
            "src/content/meta.js instead — two copies is how they drift."
        )


def test_social_and_canonical_urls_are_absolute_and_match_the_deployed_domain():
    """Relative og:image is dropped by every unfurler, and a wrong canonical de-indexes a page."""
    origin = re.search(r"origin: '([^']+)'", META.read_text(encoding="utf-8"))
    assert origin, "meta.js no longer declares an origin"
    assert origin.group(1).startswith("https://"), (
        f"origin is {origin.group(1)!r}; og:image, og:url and canonical must be absolute https"
    )

    host = origin.group(1).removeprefix("https://").rstrip("/")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert re.search(rf"^\s*-\s*{re.escape(host)}\s*$", render, flags=re.MULTILINE), (
        f"meta.js publishes canonical URLs on {host}, but render.yaml does not serve the site "
        "there. One of the two is wrong, and the canonical tag is the one search engines obey."
    )


def test_seo_text_fits_where_it_is_displayed():
    """Titles and descriptions are truncated in results and previews. Say it inside the budget."""
    meta = META.read_text(encoding="utf-8")
    too_long = [
        title for title in re.findall(r"^    title: '([^']+)'", meta, flags=re.MULTILINE)
        if len(title) > 70
    ]
    assert not too_long, f"titles over 70 characters are cut off in search results: {too_long}"


def test_components_take_their_words_from_the_content_module():
    """One place to edit the copy only holds if components stop carrying their own."""
    offenders = []
    for component in sorted(COMPONENTS.glob("*.jsx")):
        if component.name in STRUCTURAL:
            continue
        if "content/" not in component.read_text(encoding="utf-8"):
            offenders.append(component.relative_to(ROOT).as_posix())

    assert not offenders, (
        "These components import nothing from src/content/, so any words in them are a second "
        f"copy nobody will remember to update: {offenders}. Move the copy into src/content/, or "
        "add the file to STRUCTURAL if it genuinely renders no text of its own."
    )
