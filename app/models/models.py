import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class SeatStatus(str, enum.Enum):
    AVAILABLE = "available"
    CONFIRMED = "confirmed"


class ReservationStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Show(Base):
    __tablename__ = "shows"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    per_user_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    seats: Mapped[list["Seat"]] = relationship(
        back_populates="show",
        cascade="all, delete-orphan",
    )
    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="show",
    )


class Seat(Base):
    __tablename__ = "seats"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    show_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("shows.id"),
        nullable=False,
    )
    seat_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus),
        nullable=False,
        default=SeatStatus.AVAILABLE,
    )

    show: Mapped["Show"] = relationship(
        back_populates="seats",
    )
    reservation_seats: Mapped[list["ReservationSeat"]] = relationship(
        back_populates="seat",
    )

    __table_args__ = (
        UniqueConstraint(
            "show_id",
            "seat_number",
            name="uq_seat_show_seat_number",
        ),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    show_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("shows.id"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus),
        nullable=False,
        default=ReservationStatus.CONFIRMED,
    )
    amount_paise: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    show: Mapped["Show"] = relationship(
        back_populates="reservations",
    )
    reservation_seats: Mapped[list["ReservationSeat"]] = relationship(
        back_populates="reservation",
        cascade="all, delete-orphan",
    )


class ReservationSeat(Base):
    __tablename__ = "reservation_seats"

    reservation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reservations.id"),
        primary_key=True,
    )
    seat_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("seats.id"),
        primary_key=True
    )

    reservation: Mapped["Reservation"] = relationship(
        back_populates="reservation_seats",
    )
    seat: Mapped["Seat"] = relationship(
        back_populates="reservation_seats",
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    show_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("shows.id"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    reservation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reservations.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "show_id",
            "key",
            name="uq_idempotency_user_show_key",
        ),
    )