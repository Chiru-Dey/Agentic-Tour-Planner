"""Offline mock mode: patches the HTTP layer + place-search classes so the suite
runs without weather/places/FX API keys. The LLM (Groq) and judge still run live.

IMPORTANT: the weather mock is *faithful to the real OpenWeatherMap contract* —
it returns Kelvin unless `units=metric` is passed. So the repo's Kelvin-as-°C
bug reproduces offline, and disappears once you apply the fix in patches.md."""
import datetime
from contextlib import contextmanager
from unittest.mock import patch

WEATHER_SEED = {"goa": (31, "clear sky"), "manali": (12, "light rain"), "jaipur": (34, "haze"),
    "kerala": (29, "moderate rain"), "leh": (8, "clear sky"), "andaman": (30, "few clouds"),
    "rishikesh": (26, "clear sky"), "darjeeling": (14, "mist"), "udaipur": (33, "clear sky"),
    "hampi": (32, "few clouds"), "paris": (11, "overcast clouds"), "tokyo": (16, "few clouds"),
    "bali": (29, "scattered clouds"), "dubai": (41, "clear sky"), "singapore": (30, "thunderstorm"),
    "bangkok": (33, "few clouds"), "new york": (9, "clear sky"), "london": (8, "light rain"),
    "rome": (17, "clear sky"), "sydney": (21, "few clouds"), "mumbai": (29, "heavy intensity rain"),
    "reykjavik": (-2, "snow"), "gulmarg": (-5, "snow"), "kyoto": (15, "clear sky"),
    "maldives": (30, "few clouds"), "varanasi": (30, "haze"), "pondicherry": (31, "few clouds")}
KNOWN_CITIES = set(WEATHER_SEED) | {"vietnam","hanoi","lisbon","meghalaya","shillong","prague",
    "kuala lumpur","delhi","agra","amsterdam","berlin","osaka","chennai","madurai","kochi",
    "boston","washington","phuket","san francisco","queenstown","new zealand","spiti","zanskar",
    "iceland","reykjavik","peru","cusco","machu picchu","goa"}
GOOGLE_FAIL_CITIES = {"spiti"}          # forces the Tavily fallback deterministically
FX_RATES = {"USD":1.0,"EUR":0.92,"GBP":0.79,"INR":83.2,"JPY":151.4,"THB":36.5,"AUD":1.52,
    "NZD":1.66,"SGD":1.34,"AED":3.67,"ISK":138.0,"PEN":3.75,"VND":25400.0,"CZK":23.2,"MYR":4.7}

def _key(place): return str(place).lower().strip()
def _known(place): return any(k in _key(place) for k in KNOWN_CITIES)

class _Resp:
    def __init__(self, payload, status=200): self._p, self.status_code = payload, status
    def json(self): return self._p

def fake_requests_get(url, params=None, **kw):
    params = params or {}
    if "openweathermap.org" in url:
        city = _key(params.get("q", ""))
        temp_c, desc = next((v for k, v in WEATHER_SEED.items() if k in city), (25.0, "partly cloudy"))
        metric = params.get("units") == "metric"
        conv = (lambda c: c) if metric else (lambda c: round(c + 273.15, 2))  # faithful: default = Kelvin
        if url.endswith("/weather"):
            return _Resp({"main": {"temp": conv(temp_c)}, "weather": [{"description": desc}]})
        now = datetime.datetime(2026, 7, 1, 12, 0)
        items = [{"dt_txt": (now + datetime.timedelta(hours=3*i)).strftime("%Y-%m-%d %H:%M:%S"),
                  "main": {"temp": conv(temp_c + (i % 4) - 2)}, "weather": [{"description": desc}]}
                 for i in range(int(params.get("cnt", 10)))]
        return _Resp({"list": items})
    if "exchangerate-api.com" in url:
        return _Resp({"result": "success", "conversion_rates": FX_RATES})
    raise RuntimeError(f"Unmocked HTTP call in mock mode: {url}")

def _canned(kind, place):
    city = str(place).strip().title()
    return {"attractions": f"Top attractions in and around {city}: {city} Old Town, {city} Central Museum, Lakeview Park, Sunset Point, Heritage Fort.",
            "restaurants": f"Top restaurants in {city}: Spice Route (avg 12 USD/person), Garden Cafe (8 USD), Local Thali House (4 USD), Harbor Grill (18 USD).",
            "activities": f"Popular activities in {city}: guided heritage walk (15 USD), boat ride (10 USD), day trek (20 USD), cooking class (25 USD).",
            "transportation": f"Transport in {city}: metro/day pass 5 USD, taxis ~0.5 USD/km, local buses 1 USD, scooter rental 8 USD/day."}[kind]

@contextmanager
def mocked_apis():
    from utils.place_info_search import GooglePlaceSearchTool, TavilyPlaceSearchTool
    def google(kind):
        def f(self, place):
            if not _known(place) or _key(place) in GOOGLE_FAIL_CITIES:
                raise Exception("Google Places API: no results / quota exceeded (mock)")
            return _canned(kind, place)
        return f
    def tavily(kind):
        def f(self, place):
            if not _known(place):
                return f"No verified travel information found for '{place}'."
            return _canned(kind, place) + " [source: Tavily web search]"
        return f
    kinds = ["attractions", "restaurants", "activity", "transportation"]
    gnames = ["google_search_attractions", "google_search_restaurants", "google_search_activity", "google_search_transportation"]
    tnames = ["tavily_search_attractions", "tavily_search_restaurants", "tavily_search_activity", "tavily_search_transportation"]
    with patch("requests.get", side_effect=fake_requests_get):
        patches = [patch.object(GooglePlaceSearchTool, gn, google(k)) for gn, k in zip(gnames, kinds)]
        patches += [patch.object(TavilyPlaceSearchTool, tn, tavily(k)) for tn, k in zip(tnames, kinds)]
        for p in patches: p.start()
        try: yield
        finally:
            for p in patches: p.stop()