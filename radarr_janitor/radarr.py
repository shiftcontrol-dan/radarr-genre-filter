from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class RadarrClient:
    def __init__(self, url: str, api_key: str, verify_ssl: bool = True, timeout: int = 30):
        self.base = url.rstrip("/")
        self.timeout = timeout
        self.verify = verify_ssl
        self.s = requests.Session()
        self.s.headers.update({"X-Api-Key": api_key})
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(502, 503, 504))
        self.s.mount("http://", HTTPAdapter(max_retries=retry))
        self.s.mount("https://", HTTPAdapter(max_retries=retry))

    def get_movies(self) -> list[dict[str, Any]]:
        """Radarr returns the whole library in one unpaginated call."""
        r = self.s.get(f"{self.base}/api/v3/movie", verify=self.verify, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def genres(self) -> list[str]:
        """Distinct genres actually present in the library."""
        seen: set[str] = set()
        for m in self.get_movies():
            seen.update(m.get("genres", []) or [])
        return sorted(seen)

    def delete_movie(self, movie_id: int, delete_files: bool, add_exclusion: bool) -> None:
        # Radarr v3 uses `addImportExclusion` (the old `addExclusion` param was a no-op).
        params = {
            "deleteFiles": str(bool(delete_files)).lower(),
            "addImportExclusion": str(bool(add_exclusion)).lower(),
        }
        r = self.s.delete(
            f"{self.base}/api/v3/movie/{movie_id}",
            params=params,
            verify=self.verify,
            timeout=self.timeout,
        )
        r.raise_for_status()
