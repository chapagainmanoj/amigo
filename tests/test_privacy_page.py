"""Guard tests tying the published privacy notice to what the site actually does.

A privacy page is only worth publishing if it stays true as the site changes. These tests fail
when the page and the code disagree, rather than when someone forgets to re-read the page.

The copy itself lives in site/src/content/ — see tests/test_site_content.py for the guards on
that layout.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_SRC = ROOT / "site" / "src"
CONTENT = SITE_SRC / "content"
PRIVACY = CONTENT / "legal.jsx"
SHARED = CONTENT / "shared.jsx"
HOME = CONTENT / "home.jsx"
META = CONTENT / "meta.js"

# Anything here would collect or leak visitor data, and the page states in as many words that
# none of it is present. Adding one means the page is now false.
TRACKING_TELLS = (
    "localStorage",
    "sessionStorage",
    "document.cookie",
    "gtag(",
    "googletagmanager",
    "plausible",
    "fathom",
    "posthog",
    "mixpanel",
    "sentry",
    "hotjar",
)


def _collapsed(path: Path) -> str:
    """JSX wraps prose across lines; compare the words, not the indentation."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_the_privacy_page_is_built_and_reachable():
    """A notice nobody can open is not a notice."""
    assert PRIVACY.exists(), "site/src/content/legal.jsx is missing"
    assert (SITE_SRC / "PrivacyApp.jsx").exists(), "PrivacyApp.jsx is missing"
    assert (ROOT / "site" / "privacy" / "index.html").exists(), "privacy entry point is missing"

    meta = META.read_text(encoding="utf-8")
    assert "privacy/index.html" in meta, (
        "src/content/meta.js has no privacy page, so vite builds no entry for it and /privacy/ "
        "would 404 in production"
    )

    shared = SHARED.read_text(encoding="utf-8")
    assert "'/privacy/'" in shared or '"/privacy/"' in shared, (
        "the footer links in content/shared.jsx no longer include /privacy/, so the notice is "
        "unreachable from the site"
    )


def test_the_site_collects_nothing_the_privacy_page_denies_collecting():
    """The page claims no cookies, no analytics and no third-party scripts. Hold it to that."""
    violations = []
    for source in sorted(SITE_SRC.rglob("*.js*")):
        content = source.read_text(encoding="utf-8")
        for tell in TRACKING_TELLS:
            if tell in content:
                violations.append(f"{source.relative_to(ROOT)} contains '{tell}'")

    # Source entry points only. dist/ is build output whose hashed bundles are this same
    # source, and node_modules is not ours.
    entries = [ROOT / "site" / "index.html"]
    entries += [
        page
        for page in sorted((ROOT / "site").glob("*/index.html"))
        if page.parent.name not in {"dist", "node_modules"}
    ]

    for page in entries:
        content = page.read_text(encoding="utf-8")
        # The page's own module entry is the only script the site is allowed to load.
        extra = [
            tag
            for tag in re.findall(r"<script[^>]*>", content)
            if 'type="module"' not in tag or "/src/" not in tag
        ]
        if extra:
            violations.append(f"{page.relative_to(ROOT)} loads a third-party script: {extra}")

    assert not violations, (
        "The privacy page says this site sets no cookies, runs no analytics and loads no "
        "third-party scripts. That is no longer true:\n" + "\n".join(violations)
    )


def test_the_waitlist_cannot_go_live_without_naming_its_processor():
    """Decision 04 requires every processor to be disclosed before it receives anything.

    The page is honest while WAITLIST_PROCESSOR is null — it says the provider has not been
    chosen. The moment a real endpoint ships, that sentence becomes a lie, so the two have to be
    changed together.
    """
    privacy = PRIVACY.read_text(encoding="utf-8")
    processor = re.search(r"export const WAITLIST_PROCESSOR = (.+)", privacy)
    assert processor, "WAITLIST_PROCESSOR is no longer declared in content/legal.jsx"
    named = processor.group(1).strip().rstrip(";") != "null"

    env_example = (ROOT / "site" / ".env.example").read_text(encoding="utf-8")
    endpoint_shipped = bool(
        re.search(r"^VITE_WAITLIST_ENDPOINT=\S+", env_example, flags=re.MULTILINE)
    )

    if endpoint_shipped and not named:
        raise AssertionError(
            "site/.env.example ships a waitlist endpoint but content/legal.jsx still says the "
            "email provider has not been chosen. Name it in WAITLIST_PROCESSOR before any "
            "address is collected."
        )


def test_the_faq_and_the_privacy_page_promise_the_same_retention():
    """Two pages, one answer.

    Both quote RETENTION_PROMISE from content/shared.jsx, so they cannot disagree. This fails if
    either writes the sentence out by hand again, which is how the two drifted apart before.
    """
    promise = re.search(r"export const RETENTION_PROMISE =\s*'([^']+)'", _collapsed(SHARED))
    assert promise, "RETENTION_PROMISE is no longer declared in content/shared.jsx"

    for path in (PRIVACY, HOME):
        source = path.read_text(encoding="utf-8")
        assert "RETENTION_PROMISE" in source, (
            f"{path.relative_to(ROOT)} no longer quotes RETENTION_PROMISE. The privacy page and "
            "the FAQ have to say the same thing about an unconfirmed address."
        )
        assert promise.group(1) not in re.sub(r"\s+", " ", source), (
            f"{path.relative_to(ROOT)} writes the retention promise out by hand instead of "
            "quoting RETENTION_PROMISE, which is how the two drift apart."
        )


def test_the_notice_is_linked_where_the_address_is_handed_over():
    """Consent is informed only if the notice is reachable at the point of collection."""
    shared = SHARED.read_text(encoding="utf-8")
    assert "consentLink" in shared and "/privacy/" in shared, (
        "the waitlist consent row no longer links to /privacy/"
    )
    assert "/privacy/" in HOME.read_text(encoding="utf-8"), (
        "the FAQ answer about email no longer links to /privacy/"
    )
