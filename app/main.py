from fastapi import FastAPI

from app.api.reservations import router as reservations_router
from app.api.shows import router as shows_router


app = FastAPI(title="Seat Reservation Service")

app.include_router(shows_router)
app.include_router(reservations_router)