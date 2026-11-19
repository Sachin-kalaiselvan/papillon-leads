"""Finds prospects for Papillon. Three feeds, all from public sources that allow it:

  projects  — residential projects under construction around Bengaluru (OpenStreetMap)
  posts     — people publicly asking for an interior designer (Reddit RSS feeds)
  partners  — businesses that can refer homeowners: builders, estate agents, property managers,
              apartment associations (OpenStreetMap, plus Google Places if a key is set),
              searched in rings outward from central Bengaluru

Results go to the `prospects` table and the dashboard's Prospects page — never straight into
messages. Individuals' phone numbers are not collected.
"""

from __future__ import annotations

import asyncio
import html
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from . import db
from .config import cfg

CENTER = (12.9716, 77.5946)          # central Bengaluru
RING_STEP_KM = 5
MAX_RING_KM = 60
UA = "PapillonLeads/1.0 (+https://leads.papilloninteriors.in)"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

# ── shared ──────────────────────────────────────────────────────

async def get_state(key: str) -> dict:
    row = await db.fetchone("select value from crawl_state where key = %s", [key])
    return row["value"] if row else {}


async def set_state(key: str, value: dict) -> None:
    await db.execute(
        """insert into crawl_state (key, value, updated_at) values (%s, %s, now())
           on conflict (key) do update set value = excluded.value, updated_at = now()""", [key, value])


async def save(p: dict) -> bool:
    """Insert a prospect; returns True if it's new. Existing rows get fresh details but keep their status/notes."""
    row = await db.fetchone(
        """insert into prospects (kind, source, external_id, name, category, locality, city, lat, lon, phone,
                                  website, email, url, body, posted_at, score, ring_km, data)
           values (%(kind)s, %(source)s, %(external_id)s, %(name)s, %(category)s, %(locality)s, %(city)s, %(lat)s,
                   %(lon)s, %(phone)s, %(website)s, %(email)s, %(url)s, %(body)s, %(posted_at)s, %(score)s, %(ring_km)s, %(data)s)
           on conflict (source, external_id) do update set
             name = excluded.name, category = excluded.category, phone = coalesce(excluded.phone, prospects.phone),
             website = coalesce(excluded.website, prospects.website), score = excluded.score, updated_at = now()
           returning (xmax = 0) as inserted""",
        {k: p.get(k) for k in ("kind", "source", "external_id", "name", "category", "locality", "city", "lat", "lon",
                               "phone", "website", "email", "url", "body", "posted_at", "score", "ring_km")}
        | {"data": p.get("data") or {}},
    )
    return bool(row and row["inserted"])


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


async def overpass(query: str) -> list[dict]:
    last = None
    for url in OVERPASS:
        try:
            async with httpx.AsyncClient(timeout=120, headers={"User-Agent": UA}) as http:
                r = await http.post(url, data={"data": query})
                r.raise_for_status()
                return r.json().get("elements", [])
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Overpass unavailable: {last}")


def _tags_locality(t: dict) -> str | None:
    return t.get("addr:suburb") or t.get("addr:neighbourhood") or t.get("addr:district") or t.get("addr:street")


def _phone(t: dict) -> str | None:
    p = t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or t.get("mobile")
    return p.split(";")[0].strip() if p else None


# ── feed 1: projects being built ────────────────────────────────

def project_query(radius_km: int = 45) -> str:
    lat, lon = CENTER
    r = radius_km * 1000
    return f"""[out:json][timeout:110];
(
  nwr["landuse"="construction"]["construction"~"residential|apartments|house"](around:{r},{lat},{lon});
  nwr["building"="construction"]["name"](around:{r},{lat},{lon});
  nwr["building"="construction"]["construction"~"apartments|residential"](around:{r},{lat},{lon});
  nwr["construction"="apartments"](around:{r},{lat},{lon});
);
out center tags;"""


def parse_projects(elements: list[dict]) -> list[dict]:
    out = []
    for e in elements:
        t = e.get("tags", {})
        name = t.get("name") or t.get("name:en")
        if not name:
            continue
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        out.append({
            "kind": "project", "source": "osm", "external_id": f"{e['type']}/{e['id']}", "name": name,
            "category": t.get("construction") or t.get("building") or "residential",
            "locality": _tags_locality(t), "city": t.get("addr:city") or "Bengaluru", "lat": lat, "lon": lon,
            "website": t.get("website") or t.get("contact:website"), "phone": _phone(t),
            "url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            "score": 60 if t.get("building:levels") else 50,
            "ring_km": int(km_between(CENTER, (lat, lon))) if lat and lon else None,
            "data": {k: v for k, v in t.items() if k in ("operator", "developer", "building:levels", "start_date", "opening_date")},
        })
    return out


async def crawl_projects() -> int:
    items = parse_projects(await overpass(project_query()))
    new = sum([await save(p) for p in items])
    await set_state("projects", {"last_run": datetime.now(timezone.utc).isoformat(), "found": len(items), "new": new})
    return new


# ── feed 2: people asking for an interior designer ──────────────

SUBREDDIT_QUERIES = [
    ("bangalore", "interior designer"), ("bangalore", "interiors"), ("bangalore", "modular kitchen"),
    ("bangalore", "possession flat"), ("IndianHomeImprovement", "bangalore interior"),
    ("IndianHomeImprovement", "bengaluru interior"), ("indianrealestate", "bangalore interiors"),
    ("NRI", "bangalore flat interiors"),
]
INTEREST = re.compile(r"interior|designer|modular kitchen|wardrobe|false ceiling|woodwork|carpenter|furnish", re.I)
INTENT = [(r"looking for|recommend|suggest|any (good|reliable)|need (an? )?(interior|designer)", 25),
          (r"possession|handover|hand over|got (the )?keys|new (flat|apartment|home|villa)|just bought", 25),
          (r"budget|quote|quotation|lakh|lakhs|\bL\b|cost", 15), (r"3 ?bhk|4 ?bhk|villa|duplex", 10),
          (r"full home|complete home|turnkey|entire (flat|house|home)", 15)]
CITY = re.compile(r"bangalore|bengaluru|blr|whitefield|sarjapur|hebbal|electronic city|devanahalli|koramangala|hsr", re.I)
ATOM = "{http://www.w3.org/2005/Atom}"


def score_post(text: str) -> int:
    return min(100, sum(pts for pat, pts in INTENT if re.search(pat, text, re.I)))


def parse_reddit_rss(xml_text: str, subreddit: str) -> list[dict]:
    out = []
    root = ET.fromstring(xml_text)
    for e in root.findall(f"{ATOM}entry"):
        title = (e.findtext(f"{ATOM}title") or "").strip()
        body = re.sub(r"<[^>]+>", " ", html.unescape(e.findtext(f"{ATOM}content") or ""))
        body = re.sub(r"\s+", " ", body).strip()
        text = f"{title} {body}"
        if not INTEREST.search(text):
            continue
        if subreddit.lower() != "bangalore" and not CITY.search(text):
            continue
        link = e.find(f"{ATOM}link")
        posted = e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated")
        posted_at = datetime.fromisoformat(posted.replace("Z", "+00:00")) if posted else None
        if posted_at and posted_at < datetime.now(timezone.utc) - timedelta(days=90):
            continue
        out.append({
            "kind": "post", "source": "reddit", "external_id": e.findtext(f"{ATOM}id") or (link.get("href") if link is not None else title),
            "name": title[:300], "category": f"r/{subreddit}", "city": "Bengaluru",
            "url": link.get("href") if link is not None else None, "body": body[:2000],
            "posted_at": posted_at, "score": score_post(text),
            "data": {"author": (e.findtext(f"{ATOM}author/{ATOM}name") or "").strip()},
        })
    return out


async def crawl_posts() -> int:
    new = found = 0
    errors = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}, follow_redirects=True) as http:
        for sub, q in SUBREDDIT_QUERIES:
            try:
                r = await http.get(f"https://www.reddit.com/r/{sub}/search.rss",
                                   params={"q": q, "restrict_sr": "1", "sort": "new", "t": "month"})
                r.raise_for_status()
                items = parse_reddit_rss(r.text, sub)
                found += len(items)
                new += sum([await save(p) for p in items])
            except Exception as e:  # noqa: BLE001
                errors.append(f"r/{sub} '{q}': {str(e)[:120]}")
            await asyncio.sleep(4)   # be polite
    await set_state("posts", {"last_run": datetime.now(timezone.utc).isoformat(), "found": found, "new": new, "errors": errors})
    return new


# ── feed 3: referral partners, ring by ring ─────────────────────

PARTNER_NAME = r"[Bb]uilders|[Dd]evelopers|[Rr]ealty|[Rr]eal [Ee]state|[Pp]roperties|[Cc]onstructions|[Ee]states|[Hh]omes|[Ii]nfra|[Pp]roperty [Mm]anagement|[Ff]acility|[Oo]wners.? [Aa]ssociation|[Aa]partment [Oo]wners|[Rr]esidents.? [Ww]elfare|RWA"


def partner_query(inner_km: int, outer_km: int) -> str:
    lat, lon = CENTER
    o, i = outer_km * 1000, inner_km * 1000
    return f"""[out:json][timeout:110];
(
  nwr["office"~"estate_agent|property_management|association|construction_company"](around:{o},{lat},{lon});
  nwr["shop"="estate_agent"](around:{o},{lat},{lon});
  nwr["office"="company"]["name"~"{PARTNER_NAME}"](around:{o},{lat},{lon});
  nwr["name"~"{PARTNER_NAME}"]["office"](around:{o},{lat},{lon});
)->.all;
(
  nwr.all(around:{i},{lat},{lon});
)->.inner;
(.all; - .inner;);
out center tags;"""


def partner_category(t: dict) -> str:
    name = (t.get("name") or "").lower()
    office = t.get("office") or t.get("shop") or ""
    if re.search(r"owners.? association|apartment owners|residents.? welfare|rwa", name) or office == "association":
        return "apartment association"
    if office == "property_management" or re.search(r"property management|facility", name):
        return "property manager"
    if re.search(r"builders|developers|constructions|infra", name) or office == "construction_company":
        return "builder / developer"
    if office == "estate_agent" or re.search(r"realty|real estate|properties|estates", name):
        return "estate agent"
    return "real estate business"


def parse_partners(elements: list[dict], ring_km: int) -> list[dict]:
    out = []
    for e in elements:
        t = e.get("tags", {})
        if not t.get("name"):
            continue
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        phone, site = _phone(t), t.get("website") or t.get("contact:website")
        out.append({
            "kind": "partner", "source": "osm", "external_id": f"{e['type']}/{e['id']}", "name": t["name"],
            "category": partner_category(t), "locality": _tags_locality(t), "city": t.get("addr:city") or "Bengaluru",
            "lat": lat, "lon": lon, "phone": phone, "website": site, "email": t.get("email") or t.get("contact:email"),
            "url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            "score": 40 + (25 if phone else 0) + (15 if site else 0) + (20 if partner_category(t) in ("builder / developer", "property manager", "apartment association") else 0),
            "ring_km": ring_km,
        })
    return out


GOOGLE_QUERIES = ["builders and developers", "property management company", "real estate agent",
                  "apartment owners association", "NRI property management"]


async def google_places(ring_km: int) -> list[dict]:
    """Optional: Google Places Text Search (needs GOOGLE_MAPS_KEY). Searches near a point on the current ring."""
    key = cfg.google_maps_key
    if not key:
        return []
    out = []
    bearing = (ring_km * 37) % 360
    dlat = (ring_km / 111) * math.cos(math.radians(bearing))
    dlon = (ring_km / (111 * math.cos(math.radians(CENTER[0])))) * math.sin(math.radians(bearing))
    lat, lon = CENTER[0] + dlat, CENTER[1] + dlon
    async with httpx.AsyncClient(timeout=30) as http:
        for q in GOOGLE_QUERIES:
            r = await http.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask":
                         "places.id,places.displayName,places.formattedAddress,places.location,places.nationalPhoneNumber,places.websiteUri,places.googleMapsUri,places.rating,places.userRatingCount"},
                json={"textQuery": q, "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 5000.0}},
                      "maxResultCount": 20})
            if r.status_code >= 300:
                logger.warning("Places {}: {}", r.status_code, r.text[:200])
                continue
            for p in r.json().get("places", []):
                name = p.get("displayName", {}).get("text", "")
                out.append({
                    "kind": "partner", "source": "google", "external_id": p["id"], "name": name,
                    "category": partner_category({"name": name}) if partner_category({"name": name}) != "real estate business" else q,
                    "locality": (p.get("formattedAddress") or "").split(",")[-4:-3][0].strip() if p.get("formattedAddress", "").count(",") >= 3 else None,
                    "city": "Bengaluru", "lat": p.get("location", {}).get("latitude"), "lon": p.get("location", {}).get("longitude"),
                    "phone": p.get("nationalPhoneNumber"), "website": p.get("websiteUri"), "url": p.get("googleMapsUri"),
                    "score": 45 + (25 if p.get("nationalPhoneNumber") else 0) + min(20, (p.get("userRatingCount") or 0) // 5),
                    "ring_km": ring_km, "data": {"address": p.get("formattedAddress"), "rating": p.get("rating")},
                })
            await asyncio.sleep(1)
    return out


async def crawl_partners_next_ring() -> int:
    st = await get_state("partners")
    ring = int(st.get("next_ring_km", RING_STEP_KM))
    inner = max(0, ring - RING_STEP_KM)
    items = parse_partners(await overpass(partner_query(inner, ring)), ring) + await google_places(ring)
    new = sum([await save(p) for p in items])
    rings = st.get("rings", [])
    rings.append({"km": ring, "found": len(items), "new": new, "at": datetime.now(timezone.utc).isoformat()})
    nxt = ring + RING_STEP_KM
    cycle = int(st.get("cycle", 1))
    if nxt > MAX_RING_KM:          # finished the area: start a fresh pass to catch new businesses
        nxt, cycle = RING_STEP_KM, cycle + 1
    await set_state("partners", {"next_ring_km": nxt, "max_ring_km": MAX_RING_KM, "cycle": cycle, "rings": rings[-40:],
                                 "last_run": datetime.now(timezone.utc).isoformat()})
    return new


# ── schedule ────────────────────────────────────────────────────

SCHEDULE = {"projects": (crawl_projects, timedelta(hours=24)),
            "posts": (crawl_posts, timedelta(hours=3)),
            "partners": (crawl_partners_next_ring, timedelta(hours=2))}


async def run_feed(name: str) -> int:
    fn, _ = SCHEDULE[name]
    try:
        n = await fn()
        logger.info("crawler {}: {} new", name, n)
        return n
    except Exception as e:  # noqa: BLE001
        logger.warning("crawler {} failed: {}", name, e)
        st = await get_state(name)
        await set_state(name, {**st, "last_error": str(e)[:300], "last_run": datetime.now(timezone.utc).isoformat()})
        return 0


async def run_forever() -> None:
    await asyncio.sleep(20)
    while True:
        if cfg.crawler_enabled:
            for name, (_, every) in SCHEDULE.items():
                st = await get_state(name)
                last = st.get("last_run")
                if not last or datetime.fromisoformat(last) < datetime.now(timezone.utc) - every:
                    await run_feed(name)
        await asyncio.sleep(300)
