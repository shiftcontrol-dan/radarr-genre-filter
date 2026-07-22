from __future__ import annotations

from typing import Any

import requests


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    try:
        return int(str(v).split("/")[0].strip())
    except (TypeError, ValueError):
        return None


class OmdbClient:
    """OMDb is the one practical source that returns IMDb + Rotten Tomatoes + Metacritic together."""

    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = api_key
        self.timeout = timeout
        self.s = requests.Session()

    def fetch(self, imdb_id: str | None) -> dict[str, Any] | None:
        if not imdb_id or not self.api_key:
            return None
        try:
            r = self.s.get(
                "https://www.omdbapi.com/",
                params={"i": imdb_id, "apikey": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return None
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("Response") != "True":
            return None
        return self._parse(data)

    @staticmethod
    def _parse(data: dict[str, Any]) -> dict[str, Any]:
        rt: int | None = None
        for rating in data.get("Ratings", []):
            if rating.get("Source") == "Rotten Tomatoes":
                rt = _to_int(rating.get("Value", "").rstrip("%"))
        return {
            "imdb": _to_float(data.get("imdbRating")),
            "rt": rt,
            "metacritic": _to_int(data.get("Metascore")),
        }
