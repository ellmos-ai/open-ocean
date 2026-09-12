"""Bilingual documentation contract for the OCEAN family and SPEEDBOAT."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_product_boundary_docs_exist_in_both_languages():
    english = (ROOT / "architecture/PRODUCT-STACK-BOUNDARIES.md").read_text(
        encoding="utf-8"
    )
    german = (ROOT / "architecture/PRODUKT-STACK-GRENZEN.md").read_text(
        encoding="utf-8"
    )

    for text in (english, german):
        assert "OPEN OCEAN = PUBLIC" in text
        assert "PRIVATE OCEAN = PRIVATE_NON_PROPRIETARY" in text
        assert "FULL OCEAN = OPEN OCEAN + PRIVATE OCEAN" in text
        assert "SPEEDBOAT" in text
        assert "PROPRIETARY" in text
        assert "explicit" in text.lower() or "explizit" in text.lower()


def test_root_readmes_link_the_matching_boundary_doc():
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    german = (ROOT / "README_de.md").read_text(encoding="utf-8")

    assert "architecture/PRODUCT-STACK-BOUNDARIES.md" in english
    assert "architecture/PRODUKT-STACK-GRENZEN.md" in german
