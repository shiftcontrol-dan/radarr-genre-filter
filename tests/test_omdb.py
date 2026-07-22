from radarr_janitor.providers.omdb import OmdbClient


def test_parse_full():
    data = {
        "Response": "True",
        "imdbRating": "7.5",
        "Metascore": "73",
        "Ratings": [
            {"Source": "Internet Movie Database", "Value": "7.5/10"},
            {"Source": "Rotten Tomatoes", "Value": "87%"},
            {"Source": "Metacritic", "Value": "73/100"},
        ],
    }
    assert OmdbClient("x")._parse(data) == {"imdb": 7.5, "rt": 87, "metacritic": 73}


def test_parse_missing_values():
    data = {"Response": "True", "imdbRating": "N/A", "Metascore": "N/A", "Ratings": []}
    r = OmdbClient("x")._parse(data)
    assert r["imdb"] is None
    assert r["rt"] is None
    assert r["metacritic"] is None
