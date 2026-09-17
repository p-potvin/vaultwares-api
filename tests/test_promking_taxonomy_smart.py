import pytest
from app.routers.promking.taxonomy.dictionaries import (
    clean_title_for_search,
    extract_categories_from_title,
    KNOWN_STUDIOS,
    CATEGORY_STEMS,
)
from app.routers.promking.tpdb import generate_candidate_scene_queries
from app.routers.promking.taxonomy.classifier import TaxonomyClassifier


def test_clean_title_for_search():
    assert clean_title_for_search("Brazzers - Nicole Aniston & Johnny Sins - Shower Power 1080p") == "Brazzers Nicole Aniston & Johnny Sins Shower Power"
    assert clean_title_for_search("Blacked - Gianna Dior - First Interracial 4k.mp4") == "Blacked Gianna Dior First Interracial"
    assert clean_title_for_search("pxp.cool - Tushy - Angela White - Anal Addiction [FullHD]") == "Tushy Angela White Anal Addiction"


def test_candidate_scene_queries():
    c = generate_candidate_scene_queries(
        "Brazzers - Nicole Aniston - Shower Power 1080p",
        studio_hint="Brazzers",
        performer_hints=["Nicole Aniston"]
    )
    # Must include full title, the pure scene title "Shower Power"
    assert any("Shower Power" in cand for cand in c)


def test_extract_categories_from_title():
    cats1 = extract_categories_from_title("Cock Sucking Epiphany: Brunette Slobbers Over Massive Hard-On")
    assert "Blowjob" in cats1
    assert "Brunette" in cats1

    cats2 = extract_categories_from_title("Sexy Toes Clinic: Horny Nurse Loves Giving Footjobs")
    assert "Footjob" in cats2 or "Foot Fetish" in cats2
    assert "Roleplay" in cats2

    cats3 = extract_categories_from_title("Big Wet Milf Asses! Anal!")
    assert "Anal" in cats3
    assert "MILF" in cats3


def test_taxonomy_classifier_isolation():
    clf = TaxonomyClassifier(
        db_studios={"Brazzers", "Vixen", "Blacked"},
        db_pornstars={"Angela White", "Blake Blossom"}
    )
    # Even if "Anal" or "MILF" was mistakenly supplied as a studio or model, it MUST NOT become a studio/pornstar
    cats, stars, studs = clf.classify_video_tags(
        title="Blake Blossom In Hardcore Anal",
        categories=["Anal", "MILF"],
        pornstars=["Anal", "Blake Blossom"],
        studios=["Anal", "Brazzers"]
    )
    assert "Brazzers" in studs
    assert "Blake Blossom" in stars
    assert "Anal" not in studs
    assert "Anal" not in stars
    assert "Anal" in cats
    assert "MILF" in cats
