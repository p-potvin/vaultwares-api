import httpx
import pytest

from app.routers.promking.short_links import (
    ALIAS_MAX_LEN,
    ShortenError,
    _extract_short_url,
    make_alias,
    reuse_probability,
    video_url,
)


@pytest.mark.parametrize(
    ("pool_size", "expected"),
    [(0, 0.0), (99, 0.0), (100, 0.25), (199, 0.25), (200, 0.5), (499, 0.5), (500, 0.75), (5000, 0.75)],
)
def test_reuse_probability_tiers(pool_size, expected):
    assert reuse_probability(pool_size) == expected


def test_video_url_per_site():
    assert video_url("sexyprn", "some-video") == "https://sexyprn.lol/videos/some-video"
    assert video_url("oneporn", "x") == "https://1pornhub.vip/videos/x"
    assert video_url("fxv", "x") == "https://fullxxx.video/videos/x"


def test_make_alias_prefix_and_pascal_case():
    assert make_alias("sexyprn", "hot milf gets caught") == "SPN_HotMilfGetsCaught"
    assert make_alias("oneporn", "Ébène & friends!").startswith("1PH_EbeneFriends")
    assert make_alias("fxv", "") == "FXV_Video"


def test_make_alias_cuty_is_alphanumeric_only():
    assert make_alias("sexyprn", "hot milf gets caught", provider="cuty") == "SPNHotMilfGe"
    assert make_alias("fxv", "x y", 42, provider="cuty") == "FXV42XY"
    assert make_alias("fxv", "alina gets fucked", 12345, provider="cuty") == "FXV12345Alin"


def test_make_alias_is_capped_and_id_qualified():
    long_title = "a very long title that keeps going well beyond any sane alias length"
    alias = make_alias("fxv", long_title)
    assert len(alias) == ALIAS_MAX_LEN
    retry = make_alias("fxv", long_title, 1234)
    assert retry.startswith("FXV_1234_") and len(retry) <= ALIAS_MAX_LEN


def _res(body, status=200):
    if isinstance(body, str):
        return httpx.Response(status, text=body)
    return httpx.Response(status, json=body)


def test_extract_short_url_variants():
    assert _extract_short_url(_res({"status": "success", "shortenedUrl": "https://exe.io/abc"})) == "https://exe.io/abc"
    assert _extract_short_url(_res({"short_url": "https://cuty.io/abc"})) == "https://cuty.io/abc"
    assert _extract_short_url(_res({"data": {"url": "https://cuty.io/xyz"}})) == "https://cuty.io/xyz"
    assert _extract_short_url(_res("https://cuty.io/plain")) == "https://cuty.io/plain"


def test_extract_short_url_error_is_rejected():
    with pytest.raises(ShortenError) as exc:
        _extract_short_url(_res({"status": "error", "message": "Alias already exists."}))
    assert exc.value.rejected is True
    with pytest.raises(ShortenError):
        _extract_short_url(_res({"success": False, "message": "bad alias", "short_url": None}))
