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


def test_the_closed_waitlist_stays_disclosed_and_the_site_collects_nothing():
    """The waitlist form is gone, but addresses already collected are still held until the
    announcement goes out, so /privacy/ must keep naming the provider. The site itself must not
    regain a form endpoint without the notice being updated."""
    privacy = PRIVACY.read_text(encoding="utf-8")
    processor = re.search(r"export const WAITLIST_PROCESSOR = '(.+)'", privacy)
    assert processor, "WAITLIST_PROCESSOR must keep naming the provider holding existing entries"
    for source in sorted(SITE_SRC.rglob("*.js*")):
        assert "VITE_WAITLIST" not in source.read_text(encoding="utf-8"), (
            f"{source.relative_to(ROOT)} reads a waitlist endpoint again; update /privacy/ first"
        )


def test_the_privacy_page_quotes_the_waitlist_retention_promise():
    """The promise made to existing waitlist addresses lives once, in content/shared.jsx."""
    promise = re.search(r"export const RETENTION_PROMISE =\s*'([^']+)'", _collapsed(SHARED))
    assert promise, "RETENTION_PROMISE is no longer declared in content/shared.jsx"

    for path in (PRIVACY,):
        source = path.read_text(encoding="utf-8")
        assert "RETENTION_PROMISE" in source, (
            f"{path.relative_to(ROOT)} no longer quotes RETENTION_PROMISE. The privacy page and "
            "the FAQ have to say the same thing about an unconfirmed address."
        )
        assert promise.group(1) not in re.sub(r"\s+", " ", source), (
            f"{path.relative_to(ROOT)} writes the retention promise out by hand instead of "
            "quoting RETENTION_PROMISE, which is how the two drift apart."
        )


def test_the_notice_is_linked_where_data_is_handed_over():
    """Consent is informed only if the notice is reachable where people sign up and decide."""
    assert "/privacy/" in HOME.read_text(encoding="utf-8"), (
        "the FAQ answer about data no longer links to /privacy/"
    )
    onboarding = (ROOT / "web" / "src" / "components" / "ActivationJourney.jsx").read_text(
        encoding="utf-8"
    )
    assert "/privacy/" in onboarding, (
        "the dashboard's acknowledgement step no longer links to the privacy notice"
    )