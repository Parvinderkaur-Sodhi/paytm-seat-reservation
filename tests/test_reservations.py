import concurrent.futures

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def create_show(seats, per_user_limit=4):
    response = client.post(
        "/shows",
        headers={"Authorization": "Bearer admin"},
        json={
            "name": "test-show",
            "seats": seats,
            "price_paise": 10000,
            "per_user_limit": per_user_limit,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_show():
    show_id = create_show(["A1", "A2", "A3"])

    response = client.get(f"/shows/{show_id}")

    assert response.status_code == 200

    data = response.json()

    assert data["total_seats"] == 3
    assert data["available"] == 3
    assert data["held"] == 0
    assert data["confirmed"] == 0


def test_reserve_seat():
    show_id = create_show(["A1", "A2"])

    response = client.post(
        f"/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer user-test",
            "Idempotency-Key": "reserve-1",
        },
        json={"seats": ["A1"]},
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == "user-test"
    assert data["seats"] == ["A1"]
    assert data["amount_paise"] == 10000
    assert data["status"] == "confirmed"


def test_same_idempotency_key_returns_same_reservation():
    show_id = create_show(["A1", "A2"])

    headers = {
        "Authorization": "Bearer user-test",
        "Idempotency-Key": "same-key",
    }

    first = client.post(
        f"/shows/{show_id}/reserve",
        headers=headers,
        json={"seats": ["A1"]},
    )

    second = client.post(
        f"/shows/{show_id}/reserve",
        headers=headers,
        json={"seats": ["A1"]},
    )

    assert first.status_code == 201
    assert second.status_code == 201

    assert (
        first.json()["reservation_id"]
        == second.json()["reservation_id"]
    )


def test_same_idempotency_key_different_request_returns_409():
    show_id = create_show(["A1", "A2"])

    headers = {
        "Authorization": "Bearer user-test",
        "Idempotency-Key": "same-key",
    }

    first = client.post(
        f"/shows/{show_id}/reserve",
        headers=headers,
        json={"seats": ["A1"]},
    )

    second = client.post(
        f"/shows/{show_id}/reserve",
        headers=headers,
        json={"seats": ["A2"]},
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_cannot_reserve_taken_seat():
    show_id = create_show(["A1"])

    first = client.post(
        f"/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer user-1",
            "Idempotency-Key": "user-1-key",
        },
        json={"seats": ["A1"]},
    )

    second = client.post(
        f"/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer user-2",
            "Idempotency-Key": "user-2-key",
        },
        json={"seats": ["A1"]},
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_per_user_limit():
    show_id = create_show(
        ["A1", "A2", "A3", "A4", "A5"],
        per_user_limit=4,
    )

    for index, seat in enumerate(["A1", "A2", "A3", "A4"]):
        response = client.post(
            f"/shows/{show_id}/reserve",
            headers={
                "Authorization": "Bearer limit-user",
                "Idempotency-Key": f"limit-{index}",
            },
            json={"seats": [seat]},
        )

        assert response.status_code == 201

    fifth = client.post(
        f"/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer limit-user",
            "Idempotency-Key": "limit-5",
        },
        json={"seats": ["A5"]},
    )

    assert fifth.status_code == 409


def test_cancel_releases_seat():
    show_id = create_show(["A1"])

    reserve_response = client.post(
        f"/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer cancel-user",
            "Idempotency-Key": "cancel-key",
        },
        json={"seats": ["A1"]},
    )

    assert reserve_response.status_code == 201

    reservation_id = reserve_response.json()["reservation_id"]

    cancel_response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"Authorization": "Bearer cancel-user"},
    )

    assert cancel_response.status_code == 200

    show_response = client.get(f"/shows/{show_id}")
    data = show_response.json()

    assert data["available"] == 1
    assert data["confirmed"] == 0


def test_cancel_only_owner_can_cancel():
    show_id = create_show(["A1"])

    reserve_response = client.post(
        f"/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer owner",
            "Idempotency-Key": "owner-key",
        },
        json={"seats": ["A1"]},
    )

    reservation_id = reserve_response.json()["reservation_id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers={"Authorization": "Bearer attacker"},
    )

    assert response.status_code == 403


def test_hot_seat_only_one_wins():
    show_id = create_show(["A1"])

    def reserve(index):
        return client.post(
            f"/shows/{show_id}/reserve",
            headers={
                "Authorization": f"Bearer hot-user-{index}",
                "Idempotency-Key": f"hot-key-{index}",
            },
            json={"seats": ["A1"]},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        responses = list(executor.map(reserve, range(20)))

    statuses = [response.status_code for response in responses]

    assert statuses.count(201) == 1
    assert statuses.count(409) == 19

    show_response = client.get(f"/shows/{show_id}")
    data = show_response.json()

    assert data["available"] == 0
    assert data["confirmed"] == 1
    assert data["held"] == 0
    assert (
        data["available"]
        + data["held"]
        + data["confirmed"]
        == data["total_seats"]
    )