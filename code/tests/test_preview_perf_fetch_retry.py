from code.scripts import preview_perf_benchmark as perf


def test_fetch_all_theme_slugs_retries(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(url):  # type: ignore[override]
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient 500")
        assert url.endswith("offset=0")
        return {"items": [{"id": "alpha"}], "next_offset": None}

    monkeypatch.setattr(perf, "_fetch_json", fake_fetch)
    monkeypatch.setattr(perf.time, "sleep", lambda *_args, **_kwargs: None)

    slugs = perf.fetch_all_theme_slugs("http://example.com", page_limit=1)

    assert slugs == ["alpha"]
    assert calls["count"] == 2
