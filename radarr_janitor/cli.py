from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .db import Db
from .notify import send_telegram
from .providers.omdb import OmdbClient
from .providers.tmdb import TmdbClient
from .radarr import RadarrClient
from .rules import Thresholds, evaluate

LEGACY_FLAGS = {"-f", "--filter", "-l", "--list", "-d", "--delete", "-df", "--deletefile",
                "-a", "--addexclusion", "-v", "--verify", "-m", "--minscore"}
SUBCOMMANDS = {"report", "apply", "list-genres", "keep", "notify"}


def humanize(n: int) -> str:
    x = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if x < 1024 or unit == "PB":
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{n} B"


def _radarr_tmdb_score(movie: dict[str, Any]) -> float | None:
    ratings = movie.get("ratings") or {}
    tmdb = ratings.get("tmdb") if isinstance(ratings, dict) else None
    if isinstance(tmdb, dict):
        return tmdb.get("value")
    return None


def _ratings_for(
    movie: dict[str, Any], db: Db, omdb: OmdbClient, cfg: Config, allow_fetch: bool = True
) -> tuple[dict[str, Any], bool]:
    """Return (ratings, fetched_omdb). Cache first; only hit OMDb when allowed."""
    tmdb_id = movie.get("tmdbId")
    tmdb_score = _radarr_tmdb_score(movie)
    cached = db.get_rating(tmdb_id, cfg.cache_ttl_days) if tmdb_id else None
    if cached:
        cached["tmdb"] = cached.get("tmdb") or tmdb_score
        return cached, False
    if not allow_fetch:
        return {"imdb": None, "rt": None, "metacritic": None,
                "tmdb": tmdb_score, "popularity": movie.get("popularity")}, False
    omdb_data = omdb.fetch(movie.get("imdbId")) or {}
    rating = {
        "imdb": omdb_data.get("imdb"),
        "rt": omdb_data.get("rt"),
        "metacritic": omdb_data.get("metacritic"),
        "tmdb": tmdb_score,
        "popularity": movie.get("popularity"),
    }
    if tmdb_id and movie.get("imdbId"):
        db.put_rating(tmdb_id, movie.get("imdbId"), rating["imdb"], rating["rt"],
                      rating["metacritic"], rating["tmdb"], rating["popularity"])
    return rating, bool(omdb_data)


def _write_reports(out_dir: Path, run_id: int, params: dict[str, Any],
                   candidates: list[dict[str, Any]]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_verdict: dict[str, list[dict[str, Any]]] = {"remove": [], "review": [], "keep": []}
    for c in candidates:
        by_verdict.setdefault(c["verdict"], []).append(c)
    reclaimable = sum(c["size_bytes"] for c in by_verdict["remove"])
    review_size = sum(c["size_bytes"] for c in by_verdict["review"])

    json_path = out_dir / f"report-{run_id}.json"
    json_path.write_text(json.dumps({
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": params,
        "summary": {
            "candidates": len(candidates),
            "remove": len(by_verdict["remove"]),
            "review": len(by_verdict["review"]),
            "keep": len(by_verdict["keep"]),
            "reclaimable_bytes": reclaimable,
            "review_bytes": review_size,
        },
        "candidates": candidates,
    }, indent=2))

    lines = [f"# Radarr Janitor report #{run_id}", "",
             f"- Candidates: **{len(candidates)}**",
             f"- Clear removals: **{len(by_verdict['remove'])}** ({humanize(reclaimable)})",
             f"- Needs review (genre/seasonal, scores not clearly bad): **{len(by_verdict['review'])}** ({humanize(review_size)})",
             f"- Protected (keep-list): **{len(by_verdict['keep'])}**", ""]
    for verdict, label in (("remove", "Clear removals"), ("review", "Needs AI/human review"), ("keep", "Protected")):
        rows = by_verdict[verdict]
        if not rows:
            continue
        lines += [f"## {label} ({len(rows)})", "",
                  "| Title | Year | IMDb | RT | MC | Size | Reason |",
                  "|---|---|---|---|---|---|---|"]
        for c in rows:
            lines.append("| {t} | {y} | {i} | {r} | {m} | {s} | {rs} |".format(
                t=c["title"], y=c.get("year") or "", i=c.get("imdb") or "-",
                r=(f"{c['rt']}%" if c.get("rt") is not None else "-"),
                m=c.get("metacritic") or "-", s=humanize(c["size_bytes"]),
                rs=(("[seasonal] " if c.get("seasonal") else "") + (c.get("reason") or ""))))
        lines.append("")
    md_path = out_dir / f"report-{run_id}.md"
    md_path.write_text("\n".join(lines))
    return json_path, md_path


def cmd_report(cfg: Config, args: argparse.Namespace) -> int:
    db = Db(cfg.db_path)
    radarr = RadarrClient(cfg.radarr_url, cfg.radarr_api_key, cfg.verify_ssl)
    omdb = OmdbClient(cfg.omdb_api_key)
    tmdb = TmdbClient(cfg.tmdb_api_key)
    th = Thresholds(
        genres=args.filter or [],
        imdb_below=args.imdb_below,
        rt_below=args.rt_below,
        meta_below=args.meta_below,
        tmdb_minscore=(args.minscore if args.minscore is not None and args.minscore < 100 else None),
        seasonal=args.seasonal,
    )
    params = {"genres": th.genres, "imdb_below": th.imdb_below, "rt_below": th.rt_below,
              "meta_below": th.meta_below, "tmdb_minscore": th.tmdb_minscore, "seasonal": th.seasonal}
    has_score = any(v is not None for v in (th.imdb_below, th.rt_below, th.meta_below, th.tmdb_minscore))
    broad_score_sweep = has_score and not th.genres and not th.seasonal
    movies = radarr.get_movies()
    print(f"[+] {len(movies)} movies in Radarr")
    run_id = db.new_run("report", params)
    candidates: list[dict[str, Any]] = []
    omdb_used = 0
    deferred = 0
    for i, m in enumerate(movies, 1):
        if not m.get("hasFile") and not args.include_missing:
            continue
        genres_lower = [g.lower() for g in m.get("genres", []) or []]
        genre_hit = bool(th.genres) and any(g.lower() in genres_lower for g in th.genres)
        seasonal = tmdb.is_seasonal(m["tmdbId"]) if (th.seasonal and m.get("tmdbId")) else False
        # Only spend an OMDb lookup on movies that are actually in scope.
        if not (genre_hit or (th.seasonal and seasonal) or broad_score_sweep):
            continue
        allow = omdb_used < args.max_omdb
        ratings, fetched = _ratings_for(m, db, omdb, cfg, allow_fetch=allow)
        if fetched:
            omdb_used += 1
        elif not allow and ratings["imdb"] is None:
            deferred += 1
        kept = db.is_kept(m.get("tmdbId"))
        cand = evaluate(m, ratings, seasonal, kept, th)
        if cand:
            db.add_candidate(run_id, cand)
            candidates.append(cand)
        if i % 500 == 0:
            print(f"    scanned {i}/{len(movies)} (omdb used {omdb_used})")
    if deferred:
        print(f"[i] {deferred} in-scope movies deferred past the OMDb cap ({args.max_omdb}/run); "
              f"cache persists, so re-run to fill them in.")
    out_dir = Path(args.out) if args.out else (cfg.db_path.parent / "reports")
    json_path, md_path = _write_reports(out_dir, run_id, params, candidates)
    reclaimable = sum(c["size_bytes"] for c in candidates if c["verdict"] == "remove")
    print(f"[+] run #{run_id}: {len(candidates)} candidates "
          f"({sum(c['verdict']=='remove' for c in candidates)} remove / "
          f"{sum(c['verdict']=='review' for c in candidates)} review / "
          f"{sum(c['verdict']=='keep' for c in candidates)} protected)")
    print(f"[+] clear-removal reclaimable: {humanize(reclaimable)}")
    print(f"[+] report: {json_path}")
    if args.notify:
        _notify_summary(cfg, db)
    db.close()
    return 0


def _load_decisions(path: Path) -> dict[int, str]:
    """Approved decisions JSON: list of {tmdb_id|radarr_id, decision: keep|remove}."""
    data = json.loads(Path(path).read_text())
    items = data["candidates"] if isinstance(data, dict) and "candidates" in data else data
    out: dict[int, str] = {}
    for it in items:
        key = it.get("tmdb_id") if it.get("tmdb_id") is not None else it.get("radarr_id")
        if key is not None and it.get("decision"):
            out[int(key)] = it["decision"]
    return out


def cmd_apply(cfg: Config, args: argparse.Namespace) -> int:
    db = Db(cfg.db_path)
    radarr = RadarrClient(cfg.radarr_url, cfg.radarr_api_key, cfg.verify_ssl)
    run = None
    if args.run:
        candidates = db.candidates(args.run)
    else:
        run = db.latest_run("report")
        if not run:
            print("[!] no report run found; run `report` first", file=sys.stderr)
            return 2
        candidates = db.candidates(run["id"])
    if not candidates:
        print("[!] no candidates to act on")
        return 0

    decisions = _load_decisions(Path(args.from_json)) if args.from_json else {}
    verdicts_to_delete = set(args.verdicts.split(","))

    to_delete: list[dict[str, Any]] = []
    for c in candidates:
        key = c.get("tmdb_id") if c.get("tmdb_id") is not None else c.get("radarr_id")
        decision = decisions.get(int(key)) if key is not None else None
        if decision == "keep":
            continue
        if decision == "remove" or (decision is None and c["verdict"] in verdicts_to_delete):
            to_delete.append(c)

    total = sum(c["size_bytes"] for c in to_delete)
    print(f"[+] {len(to_delete)} movies to delete, {humanize(total)} to reclaim")
    if not to_delete:
        return 0
    if not args.yes:
        resp = input("Proceed with deletion? [y/N] ").strip().lower()
        if resp != "y":
            print("[!] aborted")
            return 1

    for c in to_delete:
        seasonal = bool(c.get("seasonal"))
        # seasonal items: delete files but DON'T exclude, so they re-download next season
        add_exclusion = args.exclude and not (seasonal and args.seasonal_redownload)
        try:
            radarr.delete_movie(c["radarr_id"], delete_files=args.deletefile, add_exclusion=add_exclusion)
            db.log_deletion(c.get("tmdb_id"), c.get("radarr_id"), c["title"],
                            c["size_bytes"], add_exclusion, seasonal)
            print(f"    deleted: {c['title']} ({humanize(c['size_bytes'])})"
                  f"{' [seasonal, will re-download]' if seasonal and not add_exclusion else ''}")
        except Exception as e:  # noqa: BLE001 - report and continue the batch
            print(f"    [!] failed {c['title']}: {e}", file=sys.stderr)
    db.close()
    return 0


def cmd_list_genres(cfg: Config, args: argparse.Namespace) -> int:
    radarr = RadarrClient(cfg.radarr_url, cfg.radarr_api_key, cfg.verify_ssl)
    print("[+] genres present in your library:")
    for g in radarr.genres():
        print(f"    {g}")
    return 0


def cmd_keep(cfg: Config, args: argparse.Namespace) -> int:
    db = Db(cfg.db_path)
    if args.keep_action == "add":
        db.add_keep(args.tmdb, args.title or "", args.reason or "", source=args.source)
        print(f"[+] protected: {args.title or args.tmdb}")
    elif args.keep_action == "remove":
        db.remove_keep(args.tmdb)
        print(f"[+] unprotected: {args.tmdb}")
    else:
        for row in db.list_keep():
            print(f"    {row['tmdb_id']:>8}  {row['title']}  ({row['source']}: {row['reason']})")
    db.close()
    return 0


def _notify_summary(cfg: Config, db: Db) -> None:
    run = db.latest_run("report")
    if not run:
        return
    cands = db.candidates(run["id"])
    remove = [c for c in cands if c["verdict"] == "remove"]
    review = [c for c in cands if c["verdict"] == "review"]
    reclaimable = humanize(sum(c["size_bytes"] for c in remove))
    text = (f"*Radarr Janitor* report #{run['id']}\n"
            f"{len(remove)} clear removals ({reclaimable})\n"
            f"{len(review)} to review\n"
            f"Run the *MediaJanitor* skill to judge and approve.")
    ok = send_telegram(cfg.telegram_bot_token or "", cfg.telegram_chat_id or "", text)
    print(f"[+] telegram notify: {'sent' if ok else 'skipped/failed (check token/chat id)'}")


def cmd_notify(cfg: Config, args: argparse.Namespace) -> int:
    db = Db(cfg.db_path)
    _notify_summary(cfg, db)
    db.close()
    return 0


def _legacy_to_report(argv: list[str]) -> list[str]:
    """Map the old `--filter Horror --deletefile --addexclusion --minscore 85` call
    onto the safe `report` subcommand. Deletion now requires an explicit `apply`."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-l", "--list", action="store_true")
    p.add_argument("-f", "--filter", action="append")
    p.add_argument("-d", "--delete", action="store_true")
    p.add_argument("-df", "--deletefile", action="store_true")
    p.add_argument("-a", "--addexclusion", action="store_true")
    p.add_argument("-v", "--verify", action="store_true")
    p.add_argument("-m", "--minscore", type=int, default=100)
    ns, _ = p.parse_known_args(argv)
    if ns.list:
        return ["list-genres"]
    new = ["report"]
    for g in ns.filter or []:
        new += ["--filter", g]
    if ns.minscore is not None:
        new += ["--minscore", str(ns.minscore)]
    print("[i] legacy invocation mapped to a safe `report` (no deletion). "
          "Review the report, then run `apply` to delete.", file=sys.stderr)
    return new


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="radarr-janitor", description="Score-aware Radarr library cleanup.")
    p.add_argument("--env", help="path to a .env file")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("report", help="build a candidate list (no deletion)")
    r.add_argument("-f", "--filter", action="append", help="genre to sweep (repeatable)")
    r.add_argument("--imdb-below", type=float, help="flag movies with IMDb below this")
    r.add_argument("--rt-below", type=int, help="flag movies with Rotten Tomatoes %% below this")
    r.add_argument("--meta-below", type=int, help="flag movies with Metacritic below this")
    r.add_argument("-m", "--minscore", type=int, default=None, help="legacy TMDb%% floor within a genre sweep")
    r.add_argument("--seasonal", action="store_true", help="flag holiday/Christmas movies")
    r.add_argument("--include-missing", action="store_true", help="include movies with no file on disk")
    r.add_argument("--max-omdb", type=int, default=950, help="cap OMDb lookups this run (free tier ~1000/day)")
    r.add_argument("--out", help="report output directory")
    r.add_argument("--notify", action="store_true", help="send a Telegram summary after")
    r.set_defaults(func=cmd_report)

    a = sub.add_parser("apply", help="delete from an approved candidate list")
    a.add_argument("--run", type=int, help="run id (default: latest report)")
    a.add_argument("--from-json", help="approved decisions JSON (overrides verdicts)")
    a.add_argument("--verdicts", default="remove", help="comma verdicts to delete when no decisions file (default: remove)")
    a.add_argument("--deletefile", action="store_true", default=True)
    a.add_argument("--no-deletefile", dest="deletefile", action="store_false")
    a.add_argument("--exclude", action="store_true", default=True, help="add import exclusion (blacklist)")
    a.add_argument("--no-exclude", dest="exclude", action="store_false")
    a.add_argument("--seasonal-redownload", action="store_true", default=True,
                   help="seasonal items: delete files but skip exclusion so they return next year")
    a.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    a.set_defaults(func=cmd_apply)

    sub.add_parser("list-genres", help="list genres present in the library").set_defaults(func=cmd_list_genres)

    k = sub.add_parser("keep", help="manage the protected keep-list")
    ksub = k.add_subparsers(dest="keep_action", required=True)
    ka = ksub.add_parser("add")
    ka.add_argument("--tmdb", type=int, required=True)
    ka.add_argument("--title")
    ka.add_argument("--reason")
    ka.add_argument("--source", default="user")
    kr = ksub.add_parser("remove")
    kr.add_argument("--tmdb", type=int, required=True)
    ksub.add_parser("list")
    k.set_defaults(func=cmd_keep)

    sub.add_parser("notify", help="send a Telegram summary of the latest report").set_defaults(func=cmd_notify)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # legacy compatibility: no subcommand but old flags present
    if argv and argv[0] not in SUBCOMMANDS and any(a in LEGACY_FLAGS for a in argv):
        argv = _legacy_to_report(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = Config.load(args.env)
    if not cfg.radarr_api_key:
        print("[!] RADARR_API_KEY not set (create .env from .env.example)", file=sys.stderr)
        return 2
    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
