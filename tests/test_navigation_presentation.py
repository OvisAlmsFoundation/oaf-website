"""Owner-approved shared navigation dimensions; no runtime or database access."""

import re
from pathlib import Path

import migration_offline as isolation

isolation.require_early_registration()

ROOT = Path(__file__).resolve().parents[1]


def declarations(selector):
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    match = re.search(re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    assert match is not None
    return dict(re.findall(r"([\w-]+)\s*:\s*([^;]+);", match[1]))


def test_navigation_approved_dimensions_and_spacing_compensation():
    rule = declarations(".site-header nav a")
    for name, value in {
        "display": "inline-flex", "align-items": "center", "min-height": "36px",
        "padding": "6px 8px", "margin": "-6px -8px", "border-radius": "6px",
        "line-height": "1.5",
    }.items():
        assert rule[name] == value


def test_navigation_coarse_pointer_minimum():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert re.search(
        r"@media\s*\(pointer:\s*coarse\)\s*\{\s*\.site-header\s*\{\s*--header-compact-height:\s*52px;\s*\}\s*\.site-header nav a\s*\{\s*min-height:\s*44px;\s*\}\s*\}",
        css,
    )


def test_support_cta_retains_distinctive_dimensions_and_colors():
    rule = declarations(".site-header nav .nav-support")
    for name, value in {
        "padding": "6px 14px", "margin": "-6px 0", "border-radius": "3px",
        "background": "var(--brand-green)", "color": "#fff",
    }.items():
        assert rule[name] == value


def test_shared_navigation_script_is_deferred_on_every_public_page():
    from oaf_website.local_testing import PUBLIC_FILES

    assert "assets/navigation.js" in PUBLIC_FILES
    for name in PUBLIC_FILES:
        if name.endswith(".html"):
            html = (ROOT / name).read_text(encoding="utf-8")
            assert html.count('<script src="assets/navigation.js" defer></script>') == 1, name
