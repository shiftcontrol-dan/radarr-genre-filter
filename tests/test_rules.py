from radarr_janitor.rules import Thresholds, evaluate


def movie(**kw):
    base = {"tmdbId": 1, "id": 1, "title": "X", "year": 2000,
            "genres": ["Horror"], "sizeOnDisk": 100}
    base.update(kw)
    return base


GOOD = {"imdb": 7.0, "rt": 80, "metacritic": 70, "tmdb": 7.0}
BAD = {"imdb": 3.0, "rt": 10, "metacritic": 20, "tmdb": 3.0}


def test_genre_only_is_review():
    c = evaluate(movie(), GOOD, False, False, Thresholds(genres=["Horror"]))
    assert c["verdict"] == "review"


def test_score_hit_is_remove():
    c = evaluate(movie(), BAD, False, False, Thresholds(genres=["Horror"], imdb_below=5.0))
    assert c["verdict"] == "remove"


def test_keep_list_protects_even_bad_scores():
    c = evaluate(movie(), BAD, False, True, Thresholds(genres=["Horror"], imdb_below=5.0))
    assert c["verdict"] == "keep"


def test_no_genre_match_returns_none():
    c = evaluate(movie(genres=["Comedy"]), GOOD, False, False, Thresholds(genres=["Horror"]))
    assert c is None


def test_cult_classic_rescued_to_review_not_remove():
    # Horror genre + score thresholds set, but good scores -> review (not remove)
    m = movie(title="28 Days Later", genres=["Horror", "Thriller", "Science Fiction"])
    ratings = {"imdb": 7.5, "rt": 87, "metacritic": 73, "tmdb": 7.2}
    c = evaluate(m, ratings, False, False, Thresholds(genres=["Horror"], imdb_below=5.0, rt_below=40))
    assert c["verdict"] == "review"


def test_seasonal_flag():
    c = evaluate(movie(genres=["Family"]), GOOD, True, False, Thresholds(seasonal=True))
    assert c is not None and c["seasonal"] == 1
