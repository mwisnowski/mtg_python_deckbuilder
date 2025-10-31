from code.web.services import preview_cache as pc


def _force_interval_elapsed():
    # Ensure adaptation interval guard passes
    if pc._LAST_ADAPT_AT is not None:
        pc._LAST_ADAPT_AT -= (pc._ADAPT_INTERVAL_S + 1)


def test_ttl_adapts_down_and_up(capsys):
    # Enable adaptation regardless of env
    pc._ADAPTATION_ENABLED = True
    pc.TTL_SECONDS = pc._TTL_BASE
    pc._RECENT_HITS.clear()
    pc._LAST_ADAPT_AT = None

    # Low hit ratio pattern (~0.1)
    for _ in range(72):
        pc.record_request_hit(False)
    for _ in range(8):
        pc.record_request_hit(True)
    pc.maybe_adapt_ttl()
    out1 = capsys.readouterr().out
    assert "theme_preview_ttl_adapt" in out1, "expected adaptation log for low hit ratio"
    ttl_after_down = pc.TTL_SECONDS
    assert ttl_after_down <= pc._TTL_BASE

    # Force interval elapsed & high hit ratio pattern (~0.9)
    _force_interval_elapsed()
    pc._RECENT_HITS.clear()
    for _ in range(72):
        pc.record_request_hit(True)
    for _ in range(8):
        pc.record_request_hit(False)
    pc.maybe_adapt_ttl()
    out2 = capsys.readouterr().out
    assert "theme_preview_ttl_adapt" in out2, "expected adaptation log for high hit ratio"
    ttl_after_up = pc.TTL_SECONDS
    assert ttl_after_up >= ttl_after_down
    # Extract hit_ratio fields to assert directionality if logs present
    ratios = []
    for line in (out1 + out2).splitlines():
        if 'theme_preview_ttl_adapt' in line:
            import json
            try:
                obj = json.loads(line)
                ratios.append(obj.get('hit_ratio'))
            except Exception:
                pass
    if len(ratios) >= 2:
        assert ratios[0] < ratios[-1], "expected second adaptation to have higher hit_ratio"
