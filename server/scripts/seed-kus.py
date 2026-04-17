#!/usr/bin/env python3
"""Load seed knowledge units into the cq server.

Reads seed-kus.json and POSTs each unit to the running server. After creation,
approves most units via the review API, then calls /confirm or /flag to reach
the target confidence defined by _target_confidence.

Leaves the last few units in 'pending' status so the review queue is not
empty for demo purposes.

Usage:
    python server/scripts/seed-kus.py --user demo --pass demo123 [--url http://localhost:3000]

The server must be running and a user must be seeded before this script
is executed.
"""

import argparse
import json
import math
import urllib.error
import urllib.request
from pathlib import Path

SEED_FILE = Path(__file__).parent / "seed-kus.json"

# Number of units to leave in pending status for the review queue.
PENDING_COUNT = 3


def _request(
    url: str,
    *,
    method: str = "POST",
    body: dict | None = None,
    token: str | None = None,
) -> dict:
    """Send a JSON request and return parsed response."""
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {url}: {body_text}") from exc


def _check_health(base_url: str) -> None:
    """Verify the server is reachable."""
    req = urllib.request.Request(f"{base_url}/health")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            if result.get("status") != "ok":
                raise SystemExit(f"Health check failed: {result}")
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach server at {base_url}: {exc.reason}\n"
            "Make sure the server is running (make dev-api or make compose-up)."
        ) from exc


def _login(base_url: str, username: str, password: str) -> str:
    """Log in and return a JWT token."""
    result = _request(
        f"{base_url}/auth/login",
        body={"username": username, "password": password},
    )
    return result["token"]


def _create_api_key(base_url: str, jwt_token: str) -> tuple[str, str]:
    """Create a short-lived API key for data-plane calls and return (id, plaintext)."""
    result = _request(
        f"{base_url}/auth/api-keys",
        body={"name": "seed-kus", "ttl": "1h"},
        token=jwt_token,
    )
    return result["id"], result["token"]


def _revoke_api_key(base_url: str, jwt_token: str, key_id: str) -> None:
    """Revoke the seed API key. Failures are logged and swallowed."""
    try:
        _request(f"{base_url}/auth/api-keys/{key_id}", method="DELETE", token=jwt_token)
    except SystemExit as exc:
        print(f"  warning: failed to revoke seed API key {key_id}: {exc}")


def _confirms_needed(target: float) -> int:
    """Number of /confirm calls to reach target confidence from 0.5."""
    return max(0, math.ceil((target - 0.5) / 0.1 - 1e-9))


def _flags_needed(target: float) -> int:
    """Number of /flag calls to reach target confidence from 0.5."""
    return max(0, math.ceil((0.5 - target) / 0.15 - 1e-9))


def load(base_url: str, jwt_token: str, api_key: str) -> None:
    """Load seed units: propose, approve, and adjust confidence.

    JWT authenticates the /review routes; the API key authenticates the
    /propose, /confirm, and /flag data-plane routes.
    """
    units = json.loads(SEED_FILE.read_text())
    total = len(units)
    approve_count = total - PENDING_COUNT
    print(f"Loading {total} seed units ({approve_count} approved, {PENDING_COUNT} pending)\n")

    for i, unit in enumerate(units, 1):
        target = unit.get("_target_confidence", 0.5)
        flag_reason = unit.get("_flag_reason", "stale")

        # Strip loader-only keys before posting.
        payload = {k: v for k, v in unit.items() if not k.startswith("_")}

        # Propose the unit with the API key; server overrides created_by to the key's owner.
        result = _request(f"{base_url}/propose", body=payload, token=api_key)
        unit_id = result["id"]

        # Approve most units; leave the last PENDING_COUNT in pending.
        if i <= approve_count:
            _request(f"{base_url}/review/{unit_id}/approve", token=jwt_token)
            status_label = "approved"

            # Adjust confidence via confirm/flag (only works on approved units).
            if target > 0.5:
                for _ in range(_confirms_needed(target)):
                    _request(f"{base_url}/confirm/{unit_id}", token=api_key)
            elif target < 0.5:
                for _ in range(_flags_needed(target)):
                    _request(
                        f"{base_url}/flag/{unit_id}",
                        body={"reason": flag_reason},
                        token=api_key,
                    )
        else:
            status_label = "pending"

        summary = unit["insight"]["summary"][:55]
        print(f"  [{i:2d}] {status_label:<8}  conf={target:.2f}  {summary}")

    print(f"\n  {total} units loaded.")


def main() -> None:
    """Load seed knowledge units into the cq server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="Base URL of the cq server (default: http://localhost:3000)",
    )
    parser.add_argument("--user", required=True, help="Username for review auth.")
    parser.add_argument("--pass", dest="password", required=True, help="Password.")
    args = parser.parse_args()

    _check_health(args.url)
    jwt_token = _login(args.url, args.user, args.password)
    key_id, api_key = _create_api_key(args.url, jwt_token)
    try:
        load(args.url, jwt_token, api_key)
    finally:
        _revoke_api_key(args.url, jwt_token, key_id)


if __name__ == "__main__":
    main()
