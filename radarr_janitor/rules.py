from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _poster(movie: dict[str, Any]) -> str | None:
    for img in movie.get("images", []) or []:
        if img.get("coverType") == "poster":
            return img.get("remoteUrl") or img.get("url")
    return None


@dataclass
class Thresholds:
    """What makes a movie a removal *candidate*. Any matching rule flags it.

    The final keep/remove call for borderline (genre-only) hits is left to the
    AI review layer in the MediaJanitor skill; this module only does the
    deterministic filtering and a preliminary verdict.
    """

    genres: list[str] = field(default_factory=list)
    imdb_below: float | None = None
    rt_below: int | None = None
    meta_below: int | None = None
    tmdb_minscore: int | None = None  # legacy: keep if TMDb% >= minscore, within a genre sweep
    seasonal: bool = False


def evaluate(
    movie: dict[str, Any],
    ratings: dict[str, Any],
    seasonal: bool,
    kept: bool,
    th: Thresholds,
) -> dict[str, Any] | None:
    """Return a candidate dict if the movie matches any removal rule, else None.

    verdict:
      keep   -> on the protected keep-list, never delete
      review -> matched a genre/seasonal sweep but scores are not clearly bad;
                the AI layer decides (this is the "28 Days Later" rescue path)
      remove -> a score threshold was crossed; a clear cut unless AI overrides
    """
    genres_lower = [g.lower() for g in movie.get("genres", []) or []]
    imdb = ratings.get("imdb")
    rt = ratings.get("rt")
    meta = ratings.get("metacritic")
    tmdb = ratings.get("tmdb")

    genre_hit = bool(th.genres) and any(g.lower() in genres_lower for g in th.genres)
    seasonal_hit = th.seasonal and seasonal

    score_reasons: list[str] = []
    score_hit = False
    if th.imdb_below is not None and imdb is not None and imdb < th.imdb_below:
        score_hit = True
        score_reasons.append(f"IMDb {imdb} < {th.imdb_below}")
    if th.rt_below is not None and rt is not None and rt < th.rt_below:
        score_hit = True
        score_reasons.append(f"RT {rt}% < {th.rt_below}%")
    if th.meta_below is not None and meta is not None and meta < th.meta_below:
        score_hit = True
        score_reasons.append(f"Metacritic {meta} < {th.meta_below}")

    legacy_hit = False
    if (
        th.tmdb_minscore is not None
        and tmdb is not None
        and (tmdb * 10) < th.tmdb_minscore
        and genre_hit
    ):
        legacy_hit = True
        score_reasons.append(f"TMDb {int(tmdb * 10)}% < {th.tmdb_minscore}%")

    if not (genre_hit or seasonal_hit or score_hit or legacy_hit):
        return None

    reasons: list[str] = []
    if genre_hit:
        matched = [g for g in th.genres if g.lower() in genres_lower]
        reasons.append("genre: " + ", ".join(matched))
    if seasonal_hit:
        reasons.append("seasonal (holiday)")
    if score_reasons:
        reasons.append("; ".join(score_reasons))

    if kept:
        verdict = "keep"
        reason = "PROTECTED (keep-list)"
    elif score_hit or legacy_hit:
        verdict = "remove"
        reason = "; ".join(reasons)
    else:
        # genre/seasonal sweep with no clearly-bad score -> let the AI decide
        verdict = "review"
        reason = "; ".join(reasons)

    return {
        "tmdb_id": movie.get("tmdbId"),
        "radarr_id": movie.get("id"),
        "title": movie.get("title", ""),
        "year": movie.get("year"),
        "genres": movie.get("genres", []) or [],
        "imdb": imdb,
        "rt": rt,
        "metacritic": meta,
        "tmdb": tmdb,
        "size_bytes": movie.get("sizeOnDisk", 0) or 0,
        "seasonal": 1 if seasonal_hit else 0,
        "verdict": verdict,
        "reason": reason,
        "poster": _poster(movie),
    }
