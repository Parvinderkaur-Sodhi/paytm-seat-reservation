# Seat Reservation Service — Engineering Write-up

## 1. Overview

This service implements a seat reservation API using FastAPI, PostgreSQL, SQLAlchemy, and Alembic.

The primary design goal is correctness under concurrent requests.

The system must ensure that:

* A seat cannot be sold twice.
* A user cannot exceed the per-show booking limit.
* Retried requests do not create duplicate reservations.
* Concurrent requests fail cleanly with `4xx` responses rather than `5xx`.
* The API can reconcile its seat state with the database.

The implementation uses PostgreSQL transactions, row-level locks, advisory locks, unique constraints, and idempotency records.

---

## 2. Atomic Reservation Mechanism

A reservation is processed inside one PostgreSQL transaction.

The main sequence is:

1. Authenticate the user from the Bearer token.
2. Acquire an advisory lock for the user's idempotency key.
3. Check whether the idempotency key already exists.
4. Load the show.
5. Acquire a per-user/show advisory lock.
6. Validate the per-user request limit.
7. Load all requested seats using `SELECT ... FOR UPDATE`.
8. Lock seats in deterministic sorted order.
9. Verify that every requested seat is available.
10. Count the user's existing confirmed seats.
11. Create the reservation.
12. Associate the seats with the reservation.
13. Change the seat status to `CONFIRMED`.
14. Store the idempotency record.
15. Commit the transaction.

Because these operations occur in one transaction, the reservation decision and seat-state changes succeed or fail together.

### Why the seat race is safe

Suppose two requests attempt to reserve A1 simultaneously.

The first transaction obtains the row lock on A1.

The second transaction waits for that lock.

After the first transaction commits, the second transaction reads the updated seat state and sees that A1 is already confirmed. It returns `409 Conflict`.

Therefore, the same seat cannot be confirmed by both requests.

The local and deployed burst tests verify this behavior.

---

## 3. Hot-Seat Storm

The burst test sends 20 concurrent requests for the same seat.

The deployed test produced:

```text
Hot-seat storm: 1 created, 19 conflicts, unexpected=[]
```

This demonstrates the expected behavior:

* exactly one request succeeds with HTTP `201`
* the remaining requests receive HTTP `409`
* no unexpected `5xx` responses occur

The same mechanism scales to a larger number of concurrent attempts because the correctness decision is made by PostgreSQL row locking rather than an application-level in-memory lock.

---

## 4. Multi-Seat Reservations and Deadlock Avoidance

A reservation can contain multiple seats.

Before locking seats, the requested seat names are sorted:

```text
A1, A2, A3
```

Every transaction therefore attempts to acquire locks in the same deterministic order.

For example, one transaction requesting:

```text
A1, A2
```

and another requesting:

```text
A2, A1
```

will both lock:

```text
A1 → A2
```

instead of acquiring locks in different orders.

This reduces the possibility of circular lock waits and database deadlocks.

The reservation is all-or-nothing. If any requested seat is unavailable or does not exist, the entire request is rejected and no subset is confirmed.

---

## 5. Per-User Booking Limit

The default booking limit is four seats per user per show.

A simple count by itself is not sufficient under concurrency.

For example, if a user has three seats and two concurrent requests each attempt to reserve two more seats, both requests could independently observe three seats before either commits.

To prevent this race, the service acquires a PostgreSQL transaction advisory lock keyed by:

```text
user + show
```

This serializes the limit check for that user and show.

The service then counts confirmed seats and checks:

```text
existing confirmed seats + requested seats <= per-user limit
```

The deployed burst test produced:

```text
Per-user limit: 4 created, 6 conflicts
```

for ten concurrent requests from the same user.

---

## 6. Idempotency

Every reservation request requires an `Idempotency-Key`.

The service stores the following information:

* user ID
* show ID
* idempotency key
* normalized request hash
* reservation ID
* creation time

The database enforces uniqueness on:

```text
(user_id, show_id, key)
```

A transaction advisory lock for the same key prevents concurrent retries from creating multiple reservations.

### Same key and same request

A retry returns the original reservation.

Example result from the deployed burst test:

```text
Idempotency replay: first=201, replay=201, same_reservation=True
```

No additional seat movement occurs.

### Same key and different request

If the same key is reused with a different set of seats, the normalized request hash does not match.

The service returns:

```text
409 Conflict
```

The deployed test verified:

```text
Same key / different request: 409
```

This prevents a client from accidentally reusing an idempotency key for a different operation.

---

## 7. Seat Lifecycle and Cancellation

This implementation uses explicit cancellation rather than timed holds.

Seat states are:

```text
AVAILABLE
CONFIRMED
```

The API exposes `held` in the show status response because it is part of the required reconciliation model, but this implementation does not currently create timed holds. Therefore:

```text
held = 0
```

When a reservation is cancelled:

1. The reservation row is locked.
2. Ownership is verified.
3. The reservation is marked `CANCELLED`.
4. Associated seat rows are locked.
5. The seats are changed back to `AVAILABLE`.
6. The transaction commits.

Cancelled reservation history remains stored.

The reservation-to-seat relationship is therefore historical, while the `seats.status` field represents the current sellable state.

This is why a seat can be reserved again after cancellation.

---

## 8. Database Constraints

Important database constraints include:

### Unique seat assignment within a show

```text
(show_id, seat_number)
```

This prevents duplicate seat definitions within a show.

### Idempotency uniqueness

```text
(user_id, show_id, key)
```

This prevents multiple idempotency records for the same logical request key.

### Reservation-seat relationship

```text
(reservation_id, seat_id)
```

This is the composite primary key.

`seat_id` is intentionally not globally unique in this table because a cancelled seat may later appear in a new reservation.

The current seat status remains the source of truth for whether a seat can be sold.

---

## 9. Consistency and Reconciliation

The show endpoint reports:

```text
available
held
confirmed
```

The invariant is:

```text
available + held + confirmed = total
```

The deployed burst test verified:

```text
Reconciliation: total=5, available=3, held=0, confirmed=2
```

Therefore:

```text
3 + 0 + 2 = 5
```

The metrics endpoint also calculates the available-seat gauge from PostgreSQL state rather than relying only on an application counter.

---

## 10. Consistency vs Availability During a Database Partition

The service chooses correctness and consistency over accepting reservations when PostgreSQL is unavailable.

A reservation cannot safely be confirmed without the database transaction and locks.

If the database becomes unavailable:

* readiness returns HTTP `503`
* new reservations cannot be safely committed
* the system should fail closed rather than risk double-selling seats

This means availability is intentionally reduced during a database partition, but seat ownership correctness is preserved.

---

## 11. Health Checks

Two health endpoints are provided.

### Liveness

```text
GET /health/live
```

Checks whether the application process is running.

### Readiness

```text
GET /health/ready
```

Executes:

```sql
SELECT 1
```

against PostgreSQL.

If the database check fails, the endpoint returns:

```text
503 Service Unavailable
```

This allows the deployment platform to distinguish an alive application from one that is ready to serve database-dependent traffic.

---

## 12. Observability

The service exposes Prometheus-style metrics through:

```text
GET /metrics
```

Metrics include:

```text
reservations_confirmed_total
reservations_declined_total{reason="seat-taken"}
reservations_declined_total{reason="per-user-limit"}
reservations_declined_total{reason="idempotent-replay"}
seats_available{show_id="..."}
```

The application also emits structured JSON request logs containing:

```text
request_id
method
path
status
duration_ms
```

Clients can supply an `X-Request-ID`; otherwise the application generates one.

This provides a correlation identifier for tracing an individual API request through logs.

### Metrics limitation

The current Prometheus counters are process-local.

A restart resets the counters, and multiple application replicas would have independent counters.

For a larger production deployment, metrics would be exported to a centralized monitoring system or collected using a platform-managed Prometheus-compatible setup.

The available-seat gauge is recalculated from PostgreSQL state when `/metrics` is requested, which helps it reconcile with the current database state.

---

## 13. Deployment

The service is containerized using Docker.

The container startup sequence is:

```text
Start container
    ↓
Run Alembic migrations
    ↓
Start Uvicorn
```

The startup script runs:

```bash
alembic upgrade head
```

before starting the API.

The deployed service is running on Railway with PostgreSQL.

Live API:

```text
https://paytm-seat-reservation-production.up.railway.app
```

Verified endpoints:

```text
GET /health/live  → 200
GET /health/ready → 200
GET /metrics      → 200
```

The concurrency burst test was also executed against the live URL and passed all checks.

---

## 14. Testing

The automated test suite contains nine tests covering:

* show creation
* basic reservation
* idempotent replay
* same-key/different-request rejection
* taken-seat conflict
* per-user limit
* cancellation and seat release
* cancellation ownership
* concurrent hot-seat reservation

Current local result:

```text
9 passed
```

The concurrency burst script additionally verifies:

* 20 concurrent hot-seat requests
* exactly one successful reservation
* clean conflicts
* idempotency replay
* idempotency key misuse
* concurrent per-user limit enforcement
* final seat reconciliation

The deployed result was:

```text
ALL BURST CHECKS PASSED
```

---

## 15. AI Usage

AI assistance was used during development for:

* discussing the database and concurrency design
* reviewing race conditions and transaction behavior
* generating and refining test scenarios
* reviewing API structure
* improving documentation
* troubleshooting development and deployment issues

The implementation was reviewed and tested locally and against the deployed service. The final correctness checks were executed against the actual running system rather than relying only on generated code.

---

## 16. Future Improvements

For a larger production system, possible improvements include:

1. Replace the exercise Bearer-token authentication with the organization's real OAuth/JWT identity provider.
2. Add timed seat holds if the product requires a checkout window.
3. Integrate a real payment provider when the payment contract/API is defined.
4. Persist business-level audit events for reservation state changes.
5. Use centralized metrics storage for multi-instance deployments.
6. Add distributed tracing using OpenTelemetry.
7. Add rate limiting at the API gateway.
8. Add database connection-pool tuning based on production load.
9. Add automated load testing at larger concurrency levels.
10. Add automated deployment and migration safety checks.