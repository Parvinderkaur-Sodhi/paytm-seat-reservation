from prometheus_client import Counter, Gauge


reservations_confirmed = Counter(
    "reservations_confirmed_total",
    "Total number of confirmed reservations",
)

reservations_declined = Counter(
    "reservations_declined_total",
    "Total number of declined reservation requests",
    ["reason"],
)

seats_available = Gauge(
    "seats_available",
    "Number of currently available seats",
    ["show_id"],
)