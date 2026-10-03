import json
import os
import sys
import threading
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


def request(method, path, body=None, token=None, headers=None):
    data = None

    if body is not None:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json", **(headers or {})}

    if token:
        headers = {"Authorization": f"Bearer {token}", **(headers or {})}

    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers or {},
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return exc.code, body


def main():
    print(f"Testing: {BASE_URL}")

    # 1. Create a dedicated show for the burst.
    seats = ["A1", "A2", "A3", "A4", "A5"]
    status, show = request(
        "POST",
        "/shows",
        {
            "name": f"burst-{uuid.uuid4()}",
            "seats": seats,
            "price_paise": 25000,
            "per_user_limit": 4,
        },
        token="admin",
    )

    if status != 201:
        print("FAILED: could not create show:", status, show)
        sys.exit(1)

    show_id = show["id"]
    print(f"Created show: {show_id}")

    # 2. Hot-seat storm: 20 users try the exact same seat.
    barrier = threading.Barrier(20)

    def hot_seat_request(i):
        barrier.wait()
        return request(
            "POST",
            f"/shows/{show_id}/reserve",
            {"seats": ["A1"]},
            token=f"hot-user-{i}",
            headers={"Idempotency-Key": f"hot-{i}"},
        )[0]

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(hot_seat_request, range(20)))

    created = results.count(201)
    conflicts = results.count(409)
    unexpected = [status for status in results if status not in (201, 409)]

    print(
        f"Hot-seat storm: {created} created, "
        f"{conflicts} conflicts, unexpected={unexpected}"
    )

    assert created == 1
    assert conflicts == 19
    assert not unexpected

    # 3. Idempotency replay.
    key = "idempotency-proof"
    first_status, first = request(
        "POST",
        f"/shows/{show_id}/reserve",
        {"seats": ["A2"]},
        token="idempotency-user",
        headers={"Idempotency-Key": key},
    )

    replay_status, replay = request(
        "POST",
        f"/shows/{show_id}/reserve",
        {"seats": ["A2"]},
        token="idempotency-user",
        headers={"Idempotency-Key": key},
    )

    print(
        f"Idempotency replay: first={first_status}, "
        f"replay={replay_status}, "
        f"same_reservation={first.get('reservation_id') == replay.get('reservation_id')}"
    )

    assert first_status == 201
    assert replay_status == 201
    assert first["reservation_id"] == replay["reservation_id"]

    # 4. Same idempotency key + different request must conflict.
    different_status, _ = request(
        "POST",
        f"/shows/{show_id}/reserve",
        {"seats": ["A3"]},
        token="idempotency-user",
        headers={"Idempotency-Key": key},
    )

    print(f"Same key / different request: {different_status}")
    assert different_status == 409

    # 5. Per-user limit under concurrency.
    limit_barrier = threading.Barrier(10)

    def limit_request(i):
        limit_barrier.wait()
        return request(
            "POST",
            f"/shows/{show_id}/reserve",
            {"seats": [f"U{i}"]},
            token="limit-user",
            headers={"Idempotency-Key": f"limit-{i}"},
        )[0]

    # A separate show is needed because the burst show has only 5 seats.
    status, limit_show = request(
        "POST",
        "/shows",
        {
            "name": f"limit-{uuid.uuid4()}",
            "seats": [f"U{i}" for i in range(10)],
            "price_paise": 10000,
            "per_user_limit": 4,
        },
        token="admin",
    )

    assert status == 201
    limit_show_id = limit_show["id"]

    def limit_request_real(i):
        limit_barrier.wait()
        return request(
            "POST",
            f"/shows/{limit_show_id}/reserve",
            {"seats": [f"U{i}"]},
            token="limit-user",
            headers={"Idempotency-Key": f"limit-{i}"},
        )[0]

    with ThreadPoolExecutor(max_workers=10) as pool:
        limit_results = list(pool.map(limit_request_real, range(10)))

    limit_created = limit_results.count(201)
    limit_conflicts = limit_results.count(409)

    print(
        f"Per-user limit: {limit_created} created, "
        f"{limit_conflicts} conflicts"
    )

    assert limit_created == 4
    assert limit_conflicts == 6

    # 6. Final reconciliation.
    status, details = request("GET", f"/shows/{show_id}")

    assert status == 200

    total = details["total_seats"]
    available = details["available"]
    held = details["held"]
    confirmed = details["confirmed"]

    print(
        f"Reconciliation: total={total}, "
        f"available={available}, held={held}, confirmed={confirmed}"
    )

    assert available + held + confirmed == total

    print("\nALL BURST CHECKS PASSED")


if __name__ == "__main__":
    main()