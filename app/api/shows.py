from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.db.database import SessionLocal
from app.models.models import Seat, SeatStatus, Show
from app.schemas.show import CreateShowRequest, ShowResponse, SeatStatusResponse, ShowDetailsResponse


router = APIRouter(prefix="/shows", tags=["shows"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "",
    response_model=ShowResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_show(
    request: CreateShowRequest,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    seat_numbers = [seat.strip() for seat in request.seats]

    if any(not seat for seat in seat_numbers):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seat names cannot be empty",
        )

    if len(set(seat_numbers)) != len(seat_numbers):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate seat names are not allowed",
        )

    show = Show(
        name=request.name,
        price_paise=request.price_paise,
        total_seats=len(seat_numbers),
        per_user_limit=request.per_user_limit,
    )

    db.add(show)
    db.flush()

    seats = [
        Seat(
            show_id=show.id,
            seat_number=seat_number,
            status=SeatStatus.AVAILABLE,
        )
        for seat_number in seat_numbers
    ]

    db.add_all(seats)
    db.commit()
    db.refresh(show)

    return ShowResponse(
        id=show.id,
        name=show.name,
        seats=seat_numbers,
        price_paise=show.price_paise,
        per_user_limit=show.per_user_limit,
    )

@router.get(
    "/{show_id}",
    response_model=ShowDetailsResponse,
)
def get_show(
    show_id: str,
    db: Session = Depends(get_db),
):
    show = db.execute(
        select(Show)
        .where(Show.id == show_id)
    ).scalar_one_or_none()

    if show is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Show not found",
        )

    seats = db.execute(
        select(Seat)
        .where(Seat.show_id == show_id)
        .order_by(Seat.seat_number)
    ).scalars().all()

    available = sum(
        seat.status == SeatStatus.AVAILABLE
        for seat in seats
    )

    confirmed = sum(
        seat.status == SeatStatus.CONFIRMED
        for seat in seats
    )

    held = 0

    return ShowDetailsResponse(
        id=show.id,
        name=show.name,
        price_paise=show.price_paise,
        per_user_limit=show.per_user_limit,
        total_seats=len(seats),
        available=available,
        held=held,
        confirmed=confirmed,
        seats=[
            SeatStatusResponse(
                seat=seat.seat_number,
                status=seat.status.value,
            )
            for seat in seats
        ],
    )