Seat Reservation Service

A production-style seat reservation API built with FastAPI and PostgreSQL, designed to remain correct under concurrent reservation requests.

Live API

https://paytm-seat-reservation-production.up.railway.app

Health checks:

GET /health/live
GET /health/ready
GET /metrics

Interactive API documentation:

/docs
Features
Create shows with assigned seats and integer prices in paise
Authenticated seat reservations using Bearer tokens
Atomic seat reservation under concurrent requests
Per-user booking limit
Idempotency for safe request retries
Explicit reservation cancellation
Seat availability reconciliation
Prometheus-style metrics
Structured request logging with correlation IDs
PostgreSQL-backed persistence
Dockerized deployment
Alembic database migrations
Public deployment on Railway
API
Create a show
POST /shows
Authorization: Bearer admin
Content-Type: application/json
{
  "name": "friday-night",
  "seats": ["A1", "A2", "A3", "A4"],
  "price_paise": 25000
}

The endpoint returns the show ID and assigned seats.

Reserve seats
POST /shows/{show_id}/reserve
Authorization: Bearer user-1
Idempotency-Key: reservation-001
Content-Type: application/json
{
  "seats": ["A1", "A2"]
}

The authenticated user identity is taken from the Bearer token and cannot be supplied through the request body.

The default per-user limit is 4 seats per show.

Cancel a reservation
POST /reservations/{reservation_id}/cancel
Authorization: Bearer user-1

Only the reservation owner can cancel the reservation. Cancelled seats become available again.

Show status
GET /shows/{show_id}

Returns individual seat states and aggregate counts for:

available
held
confirmed

This implementation uses explicit cancellation rather than timed holds, so held is currently 0.

Concurrency and correctness

Reservations are performed inside a single PostgreSQL transaction.

Requested seats are sorted before locking and selected using FOR UPDATE. This serializes concurrent attempts for the same seat and prevents double-selling.

For example, if 20 concurrent requests attempt to reserve the same seat:

exactly one request can confirm the seat
the remaining requests receive 409 Conflict
no request should return 500 because of the normal seat race

Multi-seat reservations lock requested seats in deterministic sorted order to reduce deadlock risk.

The per-user limit is protected with a PostgreSQL transaction advisory lock keyed by user and show, so concurrent requests cannot bypass the limit through a race.

Idempotency

Each reservation request requires an Idempotency-Key.

The service stores:

user identity
show
idempotency key
normalized request hash
resulting reservation ID

The idempotency key is unique per user and show.

Retrying the same key with the same request returns the original reservation.

Reusing the same key with a different seat request returns 409 Conflict.

A PostgreSQL transaction advisory lock serializes concurrent requests using the same idempotency key.

Partial requests

Multi-seat reservations are all-or-nothing.

If any requested seat does not exist or is already unavailable, the complete reservation is rejected with 409 Conflict. No subset of the requested seats is confirmed.

Money

All monetary values are represented as integer paise.

No floating-point values are used for reservation prices or amounts.

Authentication

The assignment uses a simple Bearer-token authentication mechanism for the exercise.

Example:

Authorization: Bearer user-1

The token value is used as the authenticated user identity.

This is intentionally lightweight and is not intended to replace a production OAuth/JWT identity provider.

Observability
Metrics

GET /metrics exposes Prometheus-style metrics including:

reservations_confirmed_total
reservations_declined_total{reason="seat-taken"}
reservations_declined_total{reason="per-user-limit"}
reservations_declined_total{reason="idempotent-replay"}
seats_available{show_id="..."}

The available-seat gauge is reconciled from PostgreSQL state when /metrics is requested.

Request logging

Each HTTP request produces structured JSON containing:

request ID
HTTP method
path
response status
request duration

Clients can provide an X-Request-ID header. If omitted, the service generates one.

Health checks
Liveness
GET /health/live

Confirms that the application process is running.

Readiness
GET /health/ready

Performs a database connectivity check and returns HTTP 503 when the database is unavailable.

Running locally
Requirements
Python 3.13+
Docker Desktop
PostgreSQL, or the provided Docker Compose setup
Setup
git clone git@github.com:Parvinderkaur-Sodhi/paytm-seat-reservation.git
cd paytm-seat-reservation

python3.13 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
Start PostgreSQL
docker compose up -d postgres
Run migrations
alembic upgrade head
Start the API
uvicorn app.main:app --reload

The API is then available at:

http://localhost:8000
Run with Docker Compose
docker compose up --build

The container startup script automatically runs:

alembic upgrade head

before starting Uvicorn.

Tests

Run the automated test suite:

python -m pytest -q

The test suite covers show creation, reservations, idempotency, conflicts, per-user limits, cancellation, ownership checks, and concurrent hot-seat reservation.

Concurrency burst test

Run the burst test locally:

python scripts/burst_test.py

Run it against the deployed service:

BASE_URL="https://paytm-seat-reservation-production.up.railway.app" python scripts/burst_test.py

The burst test verifies:

hot-seat concurrency
exactly one successful reservation for the same seat
clean 409 conflicts
idempotent replay
same-key/different-request rejection
per-user booking limit under concurrency
final seat-count reconciliation
Database migrations

Alembic migrations are stored under:

alembic/versions/

For deployment, migrations run automatically from start.sh.

Project structure
app/
  api/
    health.py
    reservations.py
    shows.py
  core/
    auth.py
    metrics.py
  db/
    database.py
  models/
    models.py
  schemas/
    reservation.py
    show.py
  services/
    reservation_service.py
  main.py

tests/
  test_reservations.py

scripts/
  burst_test.py

alembic/
  versions/

Dockerfile
docker-compose.yml
start.sh
requirements.txt
README.md
WRITEUP.md
Design details

The detailed engineering decisions, concurrency mechanism, consistency trade-offs, observability approach, AI usage, and future improvements are documented in WRITEUP.md.