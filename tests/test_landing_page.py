"""Guard tests for the marketing landing page under site/ and the brand palette it
shares with the dashboard under web/."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_SRC = ROOT / "site" / "src"
TOKENS_CSS = SITE_SRC / "styles" / "tokens.css"
DASHBOARD_CSS = ROOT / "web" / "src" / "index.css"

# The approved palette from docs/landing-page-spec.md section 4.1. The contrast table in that
# section was computed against exactly these values; changing one here without recomputing it
# can silently drop a pair below WCAG AA.
APPROVED_PALETTE = {
    "--oat": "#FBF8F2",
    "--sand": "#F1E9DC",
    "--rule": "#E5DCCB",
    "--ink": "#1F1A17",
    "--ink-2": "#6F655C",
    "--signal": "#EA5A2D",
    "--signal-ink": "#1F1A17",
    "--signal-deep": "#A33A0B",
    "--band": "#241E1A",
    "--band-soft": "#A99E93",
}

# Section 4.2 bans these outright: they are what made the first draft look like every other
# machine-generated landing page. Depth comes from hairlines and field changes instead.
BANNED_CSS_PROPERTIES = ("box-shadow", "backdrop-filter", "gradient(")

FORBIDDEN_PHRASES = [
    "coming soon",
    "early access",
    "join the beta",
    "your ai friend",
    "remembers you",
    "learns your habits",
    "therapy",
    "therapist",
    "coach you",
    "mental health",
    "checks in on you",
    "whatsapp",
    "voice",
    "mobile app",
]

# Whole strings that are allowed to contain a forbidden phrase because they negate or scope it.
# These are removed from the text before scanning, so a forbidden phrase smuggled onto the same
# line as an exemption is still caught.
ALLOWED_EXEMPTION_STRINGS = [
    "it is not therapy, diagnosis, treatment, or a crisis service",
]


def _extract_css_variables(css_text: str) -> dict[str, str]:
    root_match = re.search(r":root\s*\{([^}]+)\}", css_text, re.MULTILINE)
    if not root_match:
        return {}
    variables = {}
    for line in root_match.group(1).splitlines():
        line = re.sub(r"/\*.*?\*/", "", line).strip()
        match = re.match(r"^(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);", line)
        if match:
            variables[match.group(1).strip()] = match.group(2).strip()
    return variables


def test_landing_palette_is_the_approved_one():
    """site/src/styles/tokens.css declares exactly the approved palette.

    Catches both failures that actually happen: a token deleted (every var() referencing it
    silently resolves to nothing) and a hex edited by hand without recomputing contrast.
    """
    declared = _extract_css_variables(TOKENS_CSS.read_text(encoding="utf-8"))
    colors = {name: value for name, value in declared.items() if value.startswith("#")}

    missing = set(APPROVED_PALETTE) - set(colors)
    extra = set(colors) - set(APPROVED_PALETTE)
    assert not missing, f"Palette tokens missing from tokens.css: {sorted(missing)}"
    assert not extra, f"Undeclared palette tokens in tokens.css: {sorted(extra)}"

    for name, approved in APPROVED_PALETTE.items():
        assert colors[name].upper() == approved.upper(), (
            f"{name} is {colors[name]}, approved value is {approved}. "
            "Recompute the contrast table in docs/landing-page-spec.md before changing it."
        )


def test_dashboard_shares_the_brand_palette():
    """web/src/index.css declares the same ten brand tokens as the marketing page.

    A participant crosses from the marketing page into the dashboard mid-activation, so the two
    surfaces are one product and must not drift apart. The dashboard may declare extra tokens of
    its own (status colours, fonts); it may not redefine a brand token to a different value.

    Note that --ink means the opposite thing in the palette this replaced: it was the dark page
    background, and it is now dark text on a light ground. Any reintroduced token would be a
    silent visual break rather than an error, which is why this is pinned.
    """
    dashboard = _extract_css_variables(DASHBOARD_CSS.read_text(encoding="utf-8"))

    missing = set(APPROVED_PALETTE) - set(dashboard)
    assert not missing, f"Brand tokens missing from web/src/index.css: {sorted(missing)}"

    for name, approved in APPROVED_PALETTE.items():
        assert dashboard[name].upper() == approved.upper(), (
            f"{name} is {dashboard[name]} in the dashboard but {approved} on the marketing page"
        )


def test_dashboard_drops_the_retired_dark_tokens():
    """The old dark-theme tokens are gone from web/ entirely.

    Leaving one behind means a stale var(--dusk) resolves to nothing and paints a transparent
    panel, or worse, that someone reads --ember as still meaning something.
    """
    retired = ("--ember", "--ember-deep", "--gold", "--mist", "--paper", "--dusk", "--glass-")
    offenders = []
    for source in list((ROOT / "web" / "src").rglob("*.jsx")) + [DASHBOARD_CSS]:
        text = source.read_text(encoding="utf-8")
        for token in retired:
            if token in text:
                offenders.append(f"{source.relative_to(ROOT)} still references {token}")
    assert not offenders, "Retired dark-theme tokens remain:\n" + "\n".join(offenders)


def test_the_waitlist_cta_does_not_spend_the_signal_colour():
    """--signal belongs to the reminder bubble alone.

    The whole point of the accent is that it marks the one moment the product exists. Putting
    it on the CTA as well makes the two most prominent elements the same colour, and the accent
    stops meaning anything. The CTA is --ink.
    """
    css = (SITE_SRC / "styles" / "site.css").read_text(encoding="utf-8")

    button_rule = re.search(r"\.waitlist-button\s*\{([^}]*)\}", css)
    assert button_rule, ".waitlist-button rule not found in site.css"
    assert "var(--ink)" in button_rule.group(1), "The waitlist CTA must be filled with --ink"
    assert "var(--signal)" not in button_rule.group(1), (
        "The waitlist CTA must not use --signal; it belongs to the reminder bubble alone"
    )

    reminder_rule = re.search(r"\.telegram-bubble--reminder\s*\{([^}]*)\}", css)
    assert reminder_rule, ".telegram-bubble--reminder rule not found in site.css"
    assert "var(--signal)" in reminder_rule.group(1), "The reminder bubble must carry --signal"
    # --oat on --signal is 3.30 and fails AA. Text on the fill has to be the dark variant.
    assert "var(--signal-ink)" in reminder_rule.group(1), (
        "Text on the --signal fill must be --signal-ink, not --oat"
    )


def test_landing_css_avoids_the_generic_look():
    """No shadows, blurs or gradients anywhere under site/src."""
    violations = []
    for css_file in SITE_SRC.rglob("*.css"):
        text = css_file.read_text(encoding="utf-8").lower()
        for banned in BANNED_CSS_PROPERTIES:
            if banned in text:
                violations.append(f"{css_file.relative_to(ROOT)} uses '{banned}'")
    assert not violations, "Banned visual treatments found:\n" + "\n".join(violations)


def test_landing_copy_makes_no_unshipped_claims():
    """Marketing copy must not claim capabilities the matrix does not list as shipped."""
    jsx_files = list(SITE_SRC.rglob("*.jsx"))
    assert jsx_files, "No JSX files found under site/src"

    violations = []
    for jsx_file in jsx_files:
        content = jsx_file.read_text(encoding="utf-8")

        # Strip JSX tags and collapse whitespace so a phrase broken across wrapped source
        # lines is still matched.
        normalized = re.sub(r"<[^>]+>", " ", content).lower()
        normalized = re.sub(r"\s+", " ", normalized)

        for exempt in ALLOWED_EXEMPTION_STRINGS:
            normalized = normalized.replace(re.sub(r"\s+", " ", exempt.lower().strip()), " ")

        for phrase in FORBIDDEN_PHRASES:
            if re.search(rf"\b{re.escape(phrase)}\b", normalized):
                violations.append(
                    f"{jsx_file.relative_to(ROOT)} contains '{phrase}' outside an exemption."
                )

    assert not violations, "Found forbidden claims in landing page copy:\n" + "\n".join(violations)
