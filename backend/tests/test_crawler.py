import asyncio
import os
from datetime import datetime, timezone

import pytest

from papillon import api, crawler, db

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry><id>t3_aaa</id><title>Got possession of our 3BHK in Whitefield - looking for interior designer recommendations</title>
  <content type="html">&lt;p&gt;Budget around 18 lakhs for full home interiors. Any good designers?&lt;/p&gt;</content>
  <link href="https://www.reddit.com/r/bangalore/comments/aaa/x/"/><published>{NOW}</published>
  <author><name>/u/someone</name></author></entry>
 <entry><id>t3_bbb</id><title>Best biryani in Indiranagar?</title><content type="html">food</content>
  <link href="https://www.reddit.com/r/bangalore/comments/bbb/y/"/><published>{NOW}</published></entry>
</feed>"""

OSM_PROJECTS = [
    {"type": "way", "id": 1, "center": {"lat": 12.98, "lon": 77.75}, "tags": {"landuse": "construction", "construction": "residential", "name": "Lakeview Grande", "addr:suburb": "Varthur"}},
    {"type": "way", "id": 2, "center": {"lat": 12.9, "lon": 77.6}, "tags": {"landuse": "construction", "construction": "residential"}},
]
OSM_PARTNERS = [
    {"type": "node", "id": 10, "lat": 12.95, "lon": 77.62, "tags": {"office": "estate_agent", "name": "Sunrise Realty", "phone": "+91 80 1234 5678"}},
    {"type": "node", "id": 11, "lat": 12.96, "lon": 77.63, "tags": {"office": "association", "name": "Cedar Heights Apartment Owners Association"}},
    {"type": "node", "id": 12, "lat": 12.97, "lon": 77.64, "tags": {"office": "company", "name": "Northstar Builders and Developers", "website": "https://example.com"}},
]


def test_parsers():
    posts = crawler.parse_reddit_rss(RSS, "bangalore")
    assert len(posts) == 1 and posts[0]["score"] >= 50 and "reddit.com" in posts[0]["url"]
    projects = crawler.parse_projects(OSM_PROJECTS)
    assert [p["name"] for p in projects] == ["Lakeview Grande"] and projects[0]["locality"] == "Varthur"
    partners = crawler.parse_partners(OSM_PARTNERS, 10)
    cats = {p["name"]: p["category"] for p in partners}
    assert cats["Sunrise Realty"] == "estate agent"
    assert cats["Cedar Heights Apartment Owners Association"] == "apartment association"
    assert cats["Northstar Builders and Developers"] == "builder / developer"
    q = crawler.partner_query(5, 10)
    assert "around:10000" in q and "around:5000" in q


URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
def test_crawl_cycle(monkeypatch):
    async def fake_overpass(q):
        return OSM_PROJECTS if "construction" in q and "estate_agent" not in q else OSM_PARTNERS

    async def go():
        await db.open_pool(URL)
        await db.execute("truncate prospects, crawl_state, projects cascade")
        monkeypatch.setattr(crawler, "overpass", fake_overpass)
        assert await crawler.crawl_projects() == 1
        assert await crawler.crawl_partners_next_ring() == 3
        assert await crawler.crawl_partners_next_ring() == 0          # same places on the next ring → no duplicates
        st = await crawler.get_state("partners")
        assert st["next_ring_km"] == 15 and len(st["rings"]) == 2
        user = {"org": "agency", "email": "x"}
        res = await api.prospects(user)
        assert len(res["prospects"]) == 4 and "partners" in res["state"]
        proj = next(p for p in res["prospects"] if p["kind"] == "project")

        class Req:
            async def json(self):
                return {"possession_from": "2026-10-01", "possession_to": "2027-03-31"}
        await api.prospect_to_projects(proj["id"], Req(), user)
        assert (await db.fetchone("select count(*) n from projects"))["n"] == 1
        await db.close_pool()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(go())
