"""Parameters. Every value here is ILLUSTRATIVE and 'to agree' with the metric owners, not a recommendation."""
import datetime as dt

PERIOD_START = dt.datetime(2026, 9, 7)      # synthetic 28-day period (UTC)
PERIOD_DAYS = 28
CLOSE_AFTER_H = 48                          # numbers frozen at period end + 48 h; later rows go to restatement
SESSION_GAP_S = 120                         # sessionisation fallback gap (approximate)
LATE_H = 24                                 # ingested > 24 h after event = late (counted, flagged)
MIN_GROUP = 5                               # small-group suppression: never show a group smaller than this

# M19 value score: provisional pillar weights (sum 100) and interim index weights when Outcome is absent
WEIGHTS = {"Reach": 20, "Depth": 15, "Outcome": 40, "Reliability": 15, "Trust": 10}
INTERIM_WEIGHTS = {"Reach": 33, "Depth": 25, "Reliability": 25, "Trust": 17}
# 0-100 normalisation between an agreed baseline and target (placeholders)
NORM = {"M01": (30, 90), "M02": (10, 60), "M04": (1, 6), "M17": (0, 300), "M10": (0, 20), "M11": (0, 30)}

# Renewal thresholds (placeholders, to be agreed in advance with Finance and Procurement)
UTIL_THRESHOLD = 70.0          # Evidence 1: M01 at or above this = met
EXACT_SHARE_MIN = 40.0         # Evidence 2: impact can only be attributed if >= this % of interactions are exact (interaction ID)
COST_INDEX_MAX = 1.0           # Evidence 3: M18 cost per verified hour as an index vs current process (1.0 = parity)
M10_MAX, M11_MAX = 10.0, 25.0  # Evidence 4: reliability gates
METRIC_VERSION = "v1.0"

# Seat reclaim + vendor bill: PLACEHOLDER unit price in abstract "price units" per seat per term. Synthetic, not a NimbusPay or vendor price.
SEAT_PRICE_PLACEHOLDER = 100
RECLAIM_KEEP_BUFFER = 0.10     # keep 10% of a team's assigned seats as headroom when proposing reclaims (illustrative)
