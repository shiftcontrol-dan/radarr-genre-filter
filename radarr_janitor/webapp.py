from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from .cli import humanize
from .config import Config
from .db import Db
from .radarr import RadarrClient

BASE = Path(__file__).resolve().parent.parent


def create_app(cfg: Config | None = None) -> Flask:
    cfg = cfg or Config.load()
    app = Flask(__name__)
    app.secret_key = os.environ.get("WEB_SECRET", "radarr-janitor-local")
    _cache: dict[str, list[str]] = {}

    def genres() -> list[str]:
        if "g" not in _cache:
            try:
                _cache["g"] = RadarrClient(cfg.radarr_url, cfg.radarr_api_key, cfg.verify_ssl).genres()
            except Exception:
                _cache["g"] = []
        return _cache["g"]

    @app.route("/")
    def index():
        d = Db(cfg.db_path)
        run = d.latest_run("report")
        cands = d.candidates(run["id"]) if run else []
        keep = d.list_keep()
        d.close()
        groups: dict[str, list[dict]] = {"remove": [], "review": [], "keep": []}
        for c in cands:
            groups.setdefault(c["verdict"], []).append(c)
        totals = {
            k: {"n": len(v), "size": humanize(sum(x["size_bytes"] for x in v))}
            for k, v in groups.items()
        }
        return render_template(
            "index.html", genres=genres(), run=run, groups=groups,
            totals=totals, keep=keep, humanize=humanize,
        )

    @app.route("/run", methods=["POST"])
    def run():
        args = [sys.executable, "-m", "radarr_janitor.cli", "report"]
        for g in request.form.getlist("genres"):
            args += ["--filter", g]
        for field, flag in (("imdb_below", "--imdb-below"),
                            ("rt_below", "--rt-below"),
                            ("meta_below", "--meta-below")):
            val = request.form.get(field, "").strip()
            if val:
                args += [flag, val]
        if request.form.get("seasonal"):
            args.append("--seasonal")
        mo = request.form.get("max_omdb", "").strip()
        if mo:
            args += ["--max-omdb", mo]
        proc = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True)
        out = (proc.stdout or proc.stderr).strip().splitlines()
        flash(("report done: " if proc.returncode == 0 else "report FAILED: ")
              + (out[-1] if out else ""))
        return redirect(url_for("index"))

    @app.route("/keep", methods=["POST"])
    def keep_add():
        d = Db(cfg.db_path)
        d.add_keep(int(request.form["tmdb_id"]), request.form.get("title", ""),
                   request.form.get("reason", "protected via web UI"), source="user")
        d.close()
        flash(f"protected: {request.form.get('title', '')}")
        return redirect(url_for("index"))

    @app.route("/apply", methods=["POST"])
    def apply():
        # explicit-confirm enforced client-side; re-validated here by only acting on checked ids
        ids = {int(x) for x in request.form.getlist("delete")}
        delete_files = request.form.get("deletefile") is not None
        exclude = request.form.get("exclude") is not None
        d = Db(cfg.db_path)
        run = d.latest_run("report")
        by_id = {c["radarr_id"]: c for c in (d.candidates(run["id"]) if run else [])}
        radarr = RadarrClient(cfg.radarr_url, cfg.radarr_api_key, cfg.verify_ssl)
        reclaimed = n = 0
        errors: list[str] = []
        for rid in ids:
            c = by_id.get(rid)
            if not c:
                continue
            seasonal = bool(c.get("seasonal"))
            add_excl = exclude and not seasonal  # seasonal: allow re-download next year
            try:
                radarr.delete_movie(rid, delete_files=delete_files, add_exclusion=add_excl)
                d.log_deletion(c.get("tmdb_id"), rid, c["title"], c["size_bytes"], add_excl, seasonal)
                reclaimed += c["size_bytes"]
                n += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"{c['title']}: {e}")
        d.close()
        msg = f"deleted {n}, reclaimed {humanize(reclaimed)}"
        if errors:
            msg += f"; {len(errors)} errors"
        flash(msg)
        return redirect(url_for("index"))

    return app


app = create_app()


def main() -> None:
    create_app().run(
        host=os.environ.get("WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("WEB_PORT", "5056")),
    )


if __name__ == "__main__":
    main()
