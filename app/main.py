from fastapi import FastAPI

from app.api.reservations import router as reservations_router
from app.api.shows import router as shows_router
from app.api.health import router as health_router

from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.models.models import Seat, SeatStatus, Show
from app.core.metrics import seats_available


app = FastAPI(title="Seat Reservation Service")

app.include_router(shows_router)
app.include_router(reservations_router)
app.include_router(health_router)

@app.get("/metrics")
def metrics():
    db = SessionLocal()
    try:
        rows = db.execute(
            select(
                Show.id,
                func.count(Seat.id),
            )
            .outerjoin(
                Seat,
                (Seat.show_id == Show.id)
                & (Seat.status == SeatStatus.AVAILABLE),
            )
            .group_by(Show.id)
        ).all()

        for show_id, available in rows:
            seats_available.labels(show_id=show_id).set(available)

        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
    finally:
        db.close()