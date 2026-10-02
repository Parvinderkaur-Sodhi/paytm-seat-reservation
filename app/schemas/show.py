from pydantic import BaseModel, Field

class CreateShowRequest(BaseModel):
    name: str = Field(min_length=1)
    seats: list[str] = Field(min_length=1)
    price_paise: int = Field(gt=0)
    per_user_limit: int = Field(default=4, gt=0)


class ShowResponse(BaseModel):
    id: str
    name: str
    seats: list[str]
    price_paise: int
    per_user_limit: int

class SeatStatusResponse(BaseModel):
    seat: str
    status: str


class ShowDetailsResponse(BaseModel):
    id: str
    name: str
    price_paise: int
    per_user_limit: int
    total_seats: int
    available: int
    held: int
    confirmed: int
    seats: list[SeatStatusResponse]