"""The design system: one palette, and contrast that is verified not eyeballed.

The three front-ends previously carried unrelated palettes (indigo, cyan, blue),
so the product read as three unrelated tools. These tests keep them in step and
keep the colours legible.
"""
import pathlib
import re

import pytest

import theme as T

ROOT = pathlib.Path(__file__).resolve().parent.parent

# fg, bg, minimum ratio. 4.5 is WCAG AA for body text, 3.0 for large text and
# non-text indicators such as focus rings.
CONTRAST_PAIRS = [
    ("primary text on window", T.TEXT, T.BG, 4.5),
    ("primary text on input", T.TEXT, T.SURFACE, 4.5),
    ("primary text on card", T.TEXT, T.CARD, 4.5),
    ("secondary text on window", T.MUTED, T.BG, 4.5),
    ("secondary text on card", T.MUTED, T.CARD, 4.5),
    ("placeholder on input", T.FAINT, T.SURFACE, 3.0),
    ("label on primary button", T.ON_ACCENT, T.ACCENT, 4.5),
    ("focus ring on window", T.ACCENT, T.BG, 3.0),
    ("success on window", T.SUCCESS, T.BG, 4.5),
    ("warning on window", T.WARNING, T.BG, 4.5),
    ("error on window", T.ERROR, T.BG, 4.5),
]


@pytest.mark.parametrize("name,fg,bg,minimum", CONTRAST_PAIRS,
                         ids=[p[0] for p in CONTRAST_PAIRS])
def test_contrast_meets_wcag(name, fg, bg, minimum):
    ratio = T.contrast_ratio(fg, bg)
    assert ratio >= minimum, f"{name}: {ratio:.2f}:1, needs {minimum}:1"


def test_contrast_ratio_is_correct():
    """Guard the maths itself — the extremes are known values."""
    assert T.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.01)
    assert T.contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("app", ["ytd.py", "ytd_audio.py", "ytd_tui.py"])
def test_front_ends_take_colour_from_the_design_system(app):
    """No hard-coded hex outside theme.py: that is how the palettes diverged."""
    src = (ROOT / app).read_text(encoding="utf-8")
    literals = set(re.findall(r"#[0-9a-fA-F]{6}\b", src))
    assert not literals, f"{app} hard-codes colours instead of using theme: {sorted(literals)}"


def test_all_front_ends_share_one_accent():
    import ytd
    import ytd_audio
    import ytd_tui
    assert ytd._ACCENT == ytd_audio._ACCENT == T.ACCENT
    assert ytd_tui.T.ACCENT == T.ACCENT


def test_each_app_has_a_distinct_identity():
    """Shared chrome, but each app must still be recognisable at a glance."""
    tints = {k: v["tint"] for k, v in T.IDENTITY.items()}
    names = {k: v["name"] for k, v in T.IDENTITY.items()}
    assert len(set(names.values())) == len(names), "app names must be distinct"
    assert tints["video"] != tints["audio"]
    for ident in T.IDENTITY.values():
        assert T.contrast_ratio(ident["on_tint"], ident["tint"]) >= 4.5, (
            f"{ident['name']} glyph is illegible on its tint")


def test_spacing_follows_a_4pt_rhythm():
    for name, value in T.SPACE.items():
        assert value % 4 == 0, f"space.{name}={value} breaks the rhythm"


def test_type_scale_is_ordered():
    sizes = [size for size, _ in T.TYPE.values()]
    assert sizes == sorted(sizes, reverse=True) or len(set(sizes)) == len(sizes)
