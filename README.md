# Seat Reservation Service

A concurrency-safe seat reservation API built with **FastAPI + PostgreSQL**, designed to handle hot-seat races, idempotent retries, per-user booking limits, and concurrent multi-seat reservations.

## 🚀 Live Deployment

**Base URL (API):**  
https://paytm-seat-reservation-production.up.railway.app

**Interactive API Docs:**  
https://paytm-seat-reservation-production.up.railway.app/docs

**Health Check:**  
https://paytm-seat-reservation-production.up.railway.app/health/live

**Metrics:**  
https://paytm-seat-reservation-production.up.railway.app/metrics

| Endpoint        | Purpose                  |
| --------------- | ------------------------ |
| `/health/live`  | Liveness check           |
| `/health/ready` | Database readiness check |
| `/metrics`      | Prometheus metrics       |
| `/docs`         | Interactive Swagger API  |

---

## ✨ What This Project Demonstrates

* 🔒 **Atomic seat reservation**
* ⚡ **Concurrency-safe booking**
* 🎟️ **No double-selling**
* 🔁 **Idempotent retries**
* 👤 **Per-user booking limits**
* 🔓 **Reservation cancellation**
* 📊 **Prometheus metrics**
* 📝 **Structured JSON request logs**
* 🐘 **PostgreSQL persistence**
* 🐳 **Dockerized deployment**
* 🛠️ **Alembic migrations**
* ☁️ **Live Railway deployment**

---

## 🏗️ Architecture

```text
                    Client
                      │
                      ▼
              ┌───────────────┐
              │   FastAPI     │
              │     API       │
              └───────┬───────┘
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
       Auth       Reservation   Metrics
                     Service
                      │
                      ▼
              ┌───────────────┐
              │  PostgreSQL   │
              │               │
              │ Row Locks     │
              │ Advisory Locks│
              │ Constraints   │
              └───────────────┘
```

---

## 🔐 Concurrency Design

The reservation decision happens inside **one PostgreSQL transaction**.

### Seat race

Requested seats are locked using:

```sql
SELECT ...
FROM seats
WHERE ...
FOR UPDATE;
```

Only one transaction can successfully confirm a particular seat.

If 20 users attempt the same seat concurrently:

```text
1 × 201 Created
19 × 409 Conflict
0 × 500
```

### Multi-seat requests

Seats are always locked in sorted order.

```text
A1 → A2 → A3
```

This deterministic ordering reduces deadlock risk when multiple requests contain overlapping seats.

### Per-user limit

The default limit is **4 seats per show**.

A PostgreSQL advisory lock keyed by:

```text
user + show
```

serializes concurrent limit checks so parallel requests cannot bypass the booking limit.

---

## 🔁 Idempotency

Every reservation requires an `Idempotency-Key`.

The service stores:

```text
user_id
show_id
idempotency_key
request_hash
reservation_id
```

### Same key + same request

Returns the original reservation.

```text
First request  → 201
Retry          → 201
Same booking   → Yes
```

### Same key + different request

Returns:

```text
409 Conflict
```

This prevents accidental duplicate operations when clients retry requests.

---

## 🎟️ Reservation Lifecycle

```text
AVAILABLE
    │
    │ reserve
    ▼
CONFIRMED
    │
    │ cancel
    ▼
AVAILABLE
```

This implementation uses **explicit cancellation** rather than timed holds.

Therefore the current API reports:

```text
held = 0
```

The reservation history remains stored even after cancellation, while the seat itself becomes available for a future reservation.

---

## 💰 Money Handling

All prices and reservation amounts use **integer paise**.

Example:

```json
{
  "price_paise": 25000
}
```

No floating-point values are used for money.

---

## 🔑 Authentication

For this assignment, authentication uses a lightweight Bearer-token mechanism.

Example:

```http
Authorization: Bearer user-1
```

The user identity comes from the token.

A client cannot provide another user's identity through the reservation request body.

---

## 📡 API

### Create Show

```http
POST /shows
```

Requires:

```http
Authorization: Bearer admin
```

Request:

```json
{
  "name": "friday-night",
  "seats": ["A1", "A2", "A3", "A4"],
  "price_paise": 25000
}
```

---

### Reserve Seats

```http
POST /shows/{show_id}/reserve
```

Requires:

```http
Authorization: Bearer user-1
Idempotency-Key: reservation-001
```

Request:

```json
{
  "seats": ["A1", "A2"]
}
```

---

### Cancel Reservation

```http
POST /reservations/{reservation_id}/cancel
```

Requires the reservation owner's authentication token.

---

### Show Status

```http
GET /shows/{show_id}
```

Returns:

* individual seat status
* available count
* held count
* confirmed count
* total seats

The reconciliation invariant is:

```text
available + held + confirmed = total
```

---

## 🧪 Testing

### Unit / API Tests

```bash
python -m pytest -q
```

Current suite covers:

* show creation
* seat reservation
* idempotency replay
* same-key/different-request rejection
* taken-seat conflicts
* per-user limits
* cancellation
* cancellation ownership
* concurrent hot-seat reservation

### Concurrency Burst Test

## 📥 Run Locally

Follow these steps if you are running the project for the first time.

### 1. Clone the repository

Copy and run:

```bash
git clone https://github.com/Parvinderkaur-Sodhi/paytm-seat-reservation.git
cd paytm-seat-reservation
```

### 2. Create and activate a virtual environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

You should now see `(.venv)` at the beginning of your terminal prompt.

### 3. Install the required Python packages

```bash
pip install -r requirements.txt
```

### 4. Start PostgreSQL and the API with Docker

Make sure Docker Desktop is installed and running, then run:

```bash
docker compose up --build
```

This starts:

* PostgreSQL database
* FastAPI application
* Database migrations

The API will be available at:

```text
http://localhost:8000
```

### 5. Check that the API is running

Open another terminal and run:

```bash
curl http://localhost:8000/health/live
```

Expected response:

```json
{"status":"ok"}
```

You can also open the interactive API documentation:

```text
http://localhost:8000/docs
```

### 6. Run the automated tests

With the virtual environment activated:

```bash
python -m pytest -q
```

### 7. Run the concurrency / burst test

Make sure the API is running first, then in another terminal:

```bash
python scripts/burst_test.py
```

The burst test verifies:

* 500 concurrent attempts for the same seat
* exactly 1 successful reservation
* 499 clean conflicts
* idempotency replay
* same-key/different-request protection
* per-user booking limit under concurrency
* final seat-count reconciliation

A successful run ends with:

```text
ALL BURST CHECKS PASSED
```

### 8. Stop the application

Press `Ctrl + C` in the terminal running Docker Compose, then run:

```bash
docker compose down
```

To also remove the local PostgreSQL data:

```bash
docker compose down -v
```

> **Note:** `docker compose down -v` deletes the local database volume. Use it only when you want to reset the local database completely.

---

## 📊 Observability

### Health

```bash
GET /health/live
GET /health/ready
```

Readiness checks PostgreSQL and returns `503` if the database is unavailable.

### Metrics

```bash
GET /metrics
```

Exposes:

```text
reservations_confirmed_total
reservations_declined_total{reason="seat-taken"}
reservations_declined_total{reason="per-user-limit"}
reservations_declined_total{reason="idempotent-replay"}
seats_available{show_id="..."}
```

### Structured Logs

Every request produces JSON containing:

```text
request_id
method
path
status
duration_ms
```

Clients can provide:

```http
X-Request-ID
```

If not provided, the service generates one.

---

## 🐳 Run Locally

### Requirements

* Python 3.13+
* Docker Desktop
* Git

### Setup

```bash
git clone git@github.com:Parvinderkaur-Sodhi/paytm-seat-reservation.git
cd paytm-seat-reservation

python3.13 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Start PostgreSQL

```bash
docker compose up -d postgres
```

### Run migrations

```bash
alembic upgrade head
```

### Start API

```bash
uvicorn app.main:app --reload
```

API:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

---

## 🐳 Run Everything with Docker

```bash
docker compose up --build
```

Container startup automatically runs:

```bash
alembic upgrade head
```

before starting Uvicorn.

---

## 📁 Project Structure

```text
paytm-seat-reservation/
│
├── app/
│   ├── api/
│   │   ├── health.py
│   │   ├── reservations.py
│   │   └── shows.py
│   │
│   ├── core/
│   │   ├── auth.py
│   │   └── metrics.py
│   │
│   ├── db/
│   │   └── database.py
│   │
│   ├── models/
│   │   └── models.py
│   │
│   ├── schemas/
│   │   ├── reservation.py
│   │   └── show.py
│   │
│   ├── services/
│   │   └── reservation_service.py
│   │
│   └── main.py
│
├── alembic/
│   └── versions/
│
├── scripts/
│   └── burst_test.py
│
├── tests/
│   └── test_reservations.py
│
├── Dockerfile
├── docker-compose.yml
├── start.sh
├── requirements.txt
├── README.md
└── WRITEUP.md
```

---

## 📖 Engineering Write-up

For the detailed design decisions and trade-offs, see:

**[WRITEUP.md](WRITEUP.md)**

It covers:

* atomic reservation mechanism
* PostgreSQL locking strategy
* deadlock avoidance
* idempotency design
* per-user concurrency control
* cancellation
* consistency vs availability
* health checks
* observability
* testing
* AI usage
* future improvements

---

## 🤖 AI Usage

AI was used during development for:

* architecture discussions
* concurrency and race-condition review
* test-case generation
* debugging
* deployment troubleshooting
* documentation

The resulting implementation was manually reviewed and validated through automated tests and a live concurrency burst test.

---

## 📌 Assignment Result

The service has been tested both locally and against the deployed Railway instance.

```text
Local tests                 PASS
Docker build                PASS
Database migrations         PASS
Liveness                    PASS
Readiness                    PASS
Prometheus metrics          PASS
Hot-seat concurrency        PASS
Idempotency                 PASS
Per-user concurrency limit  PASS
Seat reconciliation         PASS
Live burst test             PASS
```

**Live API:**
https://paytm-seat-reservation-production.up.railway.app

**API Docs:**
https://paytm-seat-reservation-production.up.railway.app/docs
