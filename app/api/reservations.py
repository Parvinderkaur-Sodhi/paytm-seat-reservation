from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import SessionLocal
from app.models.models import (
    Reservation,
    ReservationSeat,
    ReservationStatus,
    Seat,
    SeatStatus,
)

from app.schemas.reservation import ReserveRequest, ReservationResponse
from app.services.reservation_service import reserve_seats


router = APIRouter(tags=["reservations"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "/shows/{show_id}/reserve",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def reserve(
    show_id: str,
    request: ReserveRequest,
    user_id: str = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    try:
        reservation = reserve_seats(
            db=db,
            show_id=show_id,
            user_id=user_id,
            seats_requested=request.seats,
            idempotency_key=idempotency_key,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return ReservationResponse(
        reservation_id=reservation.id,
        show_id=reservation.show_id,
        user_id=reservation.user_id,
        seats=sorted(
            seat.seat.seat_number
            for seat in reservation.reservation_seats
        ),
        amount_paise=reservation.amount_paise,
        status=reservation.status.value.lower(),
    )

@router.post(
    "/reservations/{reservation_id}/cancel",
    status_code=status.HTTP_200_OK,
)
def cancel_reservation(
    reservation_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation = db.execute(
        select(Reservation)
        .where(Reservation.id == reservation_id)
        .with_for_update()
    ).scalar_one_or_none()

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )

    if reservation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own reservation",
        )

    if reservation.status == ReservationStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation is already cancelled",
        )

    reservation.status = ReservationStatus.CANCELLED
    reservation.cancelled_at = datetime.now(timezone.utc).replace(tzinfo=None)

    seats = db.execute(
        select(Seat)
        .join(
            ReservationSeat,
            ReservationSeat.seat_id == Seat.id,
        )
        .where(
            ReservationSeat.reservation_id == reservation.id,
        )
        .with_for_update()
    ).scalars().all()

    for seat in seats:
        seat.status = SeatStatus.AVAILABLE

    db.commit()

    return {
        "reservation_id": reservation.id,
        "status": "cancelled",
        "released_seats": [
            seat.seat_number for seat in seats
        ],
    }