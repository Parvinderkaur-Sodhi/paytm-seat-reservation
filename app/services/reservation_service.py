import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.models import (
    IdempotencyKey,
    Reservation,
    ReservationSeat,
    ReservationStatus,
    Seat,
    SeatStatus,
    Show,
)


def _request_hash(seats: list[str]) -> str:
    normalized = json.dumps(
        sorted(seats),
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def reserve_seats(
    db: Session,
    show_id: str,
    user_id: str,
    seats_requested: list[str],
    idempotency_key: str,
) -> Reservation:
    seats_requested = sorted(set(seats_requested))

    if not seats_requested:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one seat is required",
        )

    # Serialize concurrent requests using the same idempotency key.
    lock_key = f"{user_id}:{show_id}:{idempotency_key}"

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": lock_key},
    )

    request_hash = _request_hash(seats_requested)

    # Check whether this idempotency key was already successfully used.
    existing_key = db.execute(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.show_id == show_id,
            IdempotencyKey.key == idempotency_key,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if existing_key:
        if existing_key.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used with a different request",
            )

        existing_reservation = db.get(
            Reservation,
            existing_key.reservation_id,
        )

        if existing_reservation is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Idempotency record is inconsistent",
            )

        return existing_reservation

    # Load the show.
    show = db.execute(
        select(Show)
        .where(Show.id == show_id)
    ).scalar_one_or_none()

    if show is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show not found",
        )

    # Serialize reservations for the same user + show.
    # This makes the per-user limit safe under concurrent requests.
    user_limit_lock_key = f"limit:{user_id}:{show_id}"

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": user_limit_lock_key},
    )

    if len(seats_requested) > show.per_user_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Per-user seat limit exceeded",
        )

    # Lock all requested seats in deterministic order.
    # This prevents two concurrent multi-seat requests from
    # acquiring the same seats in different orders.
    seats = db.execute(
        select(Seat)
        .where(
            Seat.show_id == show_id,
            Seat.seat_number.in_(seats_requested),
        )
        .order_by(Seat.seat_number)
        .with_for_update()
    ).scalars().all()

    if len(seats) != len(seats_requested):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more requested seats do not exist",
        )

    unavailable = [
        seat.seat_number
        for seat in seats
        if seat.status != SeatStatus.AVAILABLE
    ]

    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Seat(s) already taken: {', '.join(unavailable)}",
        )

    # Count the user's currently confirmed seats.
    current_seat_count = db.execute(
        select(func.count(ReservationSeat.seat_id))
        .join(
            Reservation,
            Reservation.id == ReservationSeat.reservation_id,
        )
        .where(
            Reservation.show_id == show_id,
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.CONFIRMED,
        )
    ).scalar_one()

    if current_seat_count + len(seats) > show.per_user_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Per-user seat limit exceeded",
        )

    # Create the reservation.
    reservation = Reservation(
        id=str(uuid4()),
        show_id=show_id,
        user_id=user_id,
        status=ReservationStatus.CONFIRMED,
        amount_paise=show.price_paise * len(seats),
    )

    db.add(reservation)
    db.flush()

    # Mark seats confirmed and attach them to the reservation.
    for seat in seats:
        seat.status = SeatStatus.CONFIRMED

        db.add(
            ReservationSeat(
                reservation_id=reservation.id,
                seat_id=seat.id,
            )
        )

    # Store the idempotency record in the same transaction.
    db.add(
        IdempotencyKey(
            user_id=user_id,
            show_id=show_id,
            key=idempotency_key,
            request_hash=request_hash,
            reservation_id=reservation.id,
        )
    )

    db.commit()
    db.refresh(reservation)

    return reservation