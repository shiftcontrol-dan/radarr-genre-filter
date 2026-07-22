from __future__ import annotations

from typing import Any

import requests

HOLIDAY_KEYWORDS = {
    "christmas",
    "christmas movie",
    "holiday",
    "santa claus",
    "santa",
    "advent",
    "nativity",
    "hanukkah",
    "new year's eve",
}


class TmdbClient:
    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = api_key
        self.base = "https://api.themoviedb.org/3"
        self.timeout = timeout
        self.s = requests.Session()

    def _get(self, path: str) -> dict[str, Any]:
        try:
            r = self.s.get(
                f"{self.base}{path}",
                params={"api_key": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return {}
        return r.json() if r.status_code == 200 else {}

    def genres(self) -> list[str]:
        return [g["name"] for g in self._get("/genre/movie/list").get("genres", [])]

    def movie(self, tmdb_id: int) -> dict[str, Any]:
        return self._get(f"/movie/{tmdb_id}")

    def is_seasonal(self, tmdb_id: int) -> bool:
        data = self._get(f"/movie/{tmdb_id}/keywords")
        keywords = {k["name"].lower() for k in data.get("keywords", [])}
        return bool(keywords & HOLIDAY_KEYWORDS)
