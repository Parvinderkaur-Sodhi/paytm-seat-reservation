from pydantic import BaseModel, Field


class ReserveRequest(BaseModel):
    seats: list[str] = Field(min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    show_id: str
    user_id: str
    seats: list[str]
    amount_paise: int
    status: str