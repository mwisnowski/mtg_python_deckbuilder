import os
import time
from typing import Optional

import pytest
from fastapi.testclient import TestClient
import sys


def _client_with_flags(window_s: int = 2, limit_random: int = 2, limit_build: int = 2, limit_suggest: int = 2) -> TestClient:
    # Ensure flags are set prior to importing app
    os.environ['RANDOM_MODES'] = '1'
    os.environ['RANDOM_UI'] = '1'
    os.environ['RANDOM_RATE_LIMIT'] = '1'
    os.environ['RATE_LIMIT_WINDOW_S'] = str(window_s)
    os.environ['RANDOM_RATE_LIMIT_RANDOM'] = str(limit_random)
    os.environ['RANDOM_RATE_LIMIT_BUILD'] = str(limit_build)
    os.environ['RANDOM_RATE_LIMIT_SUGGEST'] = str(limit_suggest)

    # Force fresh import so RATE_LIMIT_* constants reflect env
    sys.modules.pop('code.web.app', None)
    from code.web import app as app_module
    # Force override constants for deterministic test
    try:
        app_module.RATE_LIMIT_ENABLED = True
        app_module.RATE_LIMIT_WINDOW_S = window_s
        app_module.RATE_LIMIT_RANDOM = limit_random
        app_module.RATE_LIMIT_BUILD = limit_build
        app_module.RATE_LIMIT_SUGGEST = limit_suggest
        # Reset in-memory counters
        if hasattr(app_module, '_RL_COUNTS'):
            app_module._RL_COUNTS.clear()
    except Exception:
        pass
    return TestClient(app_module.app)


@pytest.mark.parametrize("path, method, payload, header_check", [
    ("/api/random_reroll", "post", {"seed": 1}, True),
    ("/themes/api/suggest?q=to", "get", None, True),
])
def test_rate_limit_emits_headers_and_429(path: str, method: str, payload: Optional[dict], header_check: bool):
    client = _client_with_flags(window_s=5, limit_random=1, limit_suggest=1)

    # first call should be OK or at least emit rate-limit headers
    if method == 'post':
        r1 = client.post(path, json=payload)
    else:
        r1 = client.get(path)
    assert 'X-RateLimit-Reset' in r1.headers
    assert 'X-RateLimit-Remaining' in r1.headers or r1.status_code == 429

    # Drive additional requests to exceed the remaining budget deterministically
    rem = None
    try:
        if 'X-RateLimit-Remaining' in r1.headers:
            rem = int(r1.headers['X-RateLimit-Remaining'])
    except Exception:
        rem = None

    attempts = (rem + 1) if isinstance(rem, int) else 5
    rN = r1
    for _ in range(attempts):
        if method == 'post':
            rN = client.post(path, json=payload)
        else:
            rN = client.get(path)
        if rN.status_code == 429:
            break

    assert rN.status_code == 429
    assert 'Retry-After' in rN.headers

    # Wait for window to pass, then call again and expect success
    time.sleep(5.2)
    if method == 'post':
        r3 = client.post(path, json=payload)
    else:
        r3 = client.get(path)

    assert r3.status_code != 429
    assert 'X-RateLimit-Remaining' in r3.headers
