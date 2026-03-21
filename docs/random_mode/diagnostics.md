# Random Mode Diagnostics

**Endpoint**: `GET /api/random/diagnostics`  
**Feature flag**: `WEB_RANDOM_DIAGNOSTICS=1`

---

## Overview

The diagnostics endpoint exposes seed derivation test vectors and algorithm metadata. It is intended for internal tooling and cross-platform consistency checks — verifying that seed derivation produces identical results across environments, Python versions, or deployments.

The endpoint returns **404** unless `WEB_RANDOM_DIAGNOSTICS=1` is set in the environment.

---

## Usage

```bash
WEB_RANDOM_DIAGNOSTICS=1 curl http://localhost:5000/api/random/diagnostics
```

Example response:

```json
{
  "test_vectors": {
    "test-seed": 6214070892065607348,
    "12345": 12345,
    "zero": 0,
    "empty-string-rejected": "N/A (empty string raises InvalidSeedError)"
  },
  "seed_algorithm": "sha256-63bit",
  "version": "1.0",
  "request_id": "abc123"
}
```

---

## Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `test_vectors` | object | Known-input → expected-output pairs for manual verification |
| `seed_algorithm` | string | Algorithm identifier (`sha256-63bit`) |
| `version` | string | Diagnostics schema version |
| `request_id` | string \| null | Request tracing ID |

---

## Seed Algorithm Details

String seeds are processed as:
1. UTF-8 encode the input string
2. SHA-256 hash the bytes
3. Take the first 8 bytes as a big-endian unsigned integer
4. Mask to 63 bits: `n & ((1 << 63) - 1)`

Integer seeds are normalised as: `abs(n) & ((1 << 63) - 1)`.

This ensures all seeds are non-negative, platform-independent, and fit within Python's `random.Random.seed()` expectations.

---

## Related

- [seed_infrastructure.md](seed_infrastructure.md) — API reference
- [developer_guide.md](developer_guide.md) — Integration guide
- `code/web/services/random_service.py` — `RandomService.derive_seed()`
- `code/random_util.py` — `derive_seed_from_string()`
