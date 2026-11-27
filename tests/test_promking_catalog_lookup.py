"""TPDB lookups answered by the scene catalog (app/routers/promking/tpdb.py: _catalog_request)."""
import asyncio

import httpx

from app.routers.promking import tpdb


def _client(answers):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params), request.headers.get("x-vw-project")))
        return httpx.Response(200, json={"items": answers.get(request.url.path, [])})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


def test_people_take_the_same_name_only_best_first():
    client, seen = _client({"/v1/performers": [
        {"source": "tpdb", "name": "Tiny Texie", "image": "x", "scenes": 900},
        {"source": "tpdb", "name": "Tiny", "image": None, "scenes": 50, "gender": "Male"},
        {"source": "stashdb", "name": "Tiny", "image": "img", "scenes": 10, "gender": "TRANSGENDER_FEMALE"}]})
    out = asyncio.run(tpdb._catalog_request(client, "performers", {"q": "Tiny", "limit": 1}))
    assert out["data"] == [{"name": "Tiny", "gender": "trans", "image": "img", "aliases": [], "source": "stashdb"}]
    path, params, project = seen[0]
    assert path == "/v1/performers" and params["limit"] == str(tpdb.PEOPLE_POOL) and project == "vaultwares-api"


def test_studio_domain_suffix_and_scene_shape():
    client, seen = _client({
        "/v1/studios": [{"source": "stashdb", "name": "Sex Mex", "image": "logo", "scenes": 5}],
        "/v1/scenes": [{"source": "tpdb", "id": "abc", "title": "Shower Power", "studio_name": "Studio",
                        "performers": [{"name": "A", "gender": "Female"}], "tags": ["Blonde"]}]})
    sites = asyncio.run(tpdb._catalog_request(client, "sites", {"q": "SexMex.xxx", "limit": 1}))
    assert sites["data"][0]["logo"] == "logo" and seen[0][1]["q"] == "SexMex"
    scenes = asyncio.run(tpdb._catalog_request(client, "scenes", {"q": "Shower Power", "limit": 10}))
    s = scenes["data"][0]
    assert s["id"] == "tpdb:abc" and s["site"] == {"name": "Studio"} and s["tags"] == [{"name": "Blonde"}]
    assert s["performers"] == [{"name": "A", "gender": "Female"}]


def test_no_query_asks_nothing():
    client, seen = _client({})
    assert asyncio.run(tpdb._catalog_request(client, "scenes", {"q": "  "})) == {"data": []}
    assert seen == []
