"""
Stripe OA: Incident Detection / Incident Monitor
(pasted from fastprep; the page's own URL is
 https://www.fastprep.io/problems/stripe-incident-monitor)

detectIncidents(logs) -> String[]

logs   : "timestamp,merchant_id,status_code,count", sorted by timestamp, no duplicate
         (timestamp, merchant_id, status_code) entries.  200 = success, 4xx/5xx = error.
output : "timestamp,event_type,merchant_id,status_code" sorted by
         (timestamp ASC, merchant_id ASC, status_code ASC, event_type ASC)
         (alphabetical, so RESOLVE precedes TRIGGER).

Rules
* Process entries in order.  After each entry at timestamp T, evaluate every
  (merchant, error_code) alert state for that entry's merchant using the inclusive
  sliding window [T-29, T].
* TRIGGER when both hold for a (merchant, error_code) pair that is not active:
    volume : at least 5 failures with that error code in the window
    impact : those failures are MORE THAN 1% of the merchant's 200-count in the window
             (errors * 100 > successes; with zero successes any 5+ errors qualify)
* De-duplication: an active alert never re-triggers.
* RESOLVE when an active alert's conditions are no longer met at a log for that
  merchant.  The alert then becomes inactive and may TRIGGER again later.

    ["10,merchant1,500,2","10,merchant2,500,1","15,merchant1,500,2",
     "20,merchant1,500,1","20,merchant2,500,4"]
        -> ["20,TRIGGER,merchant1,500","20,TRIGGER,merchant2,500"]
"""

from collections import deque
from typing import List


class Solution:
    def detectIncidents(self, logs: List[str]) -> List[str]:
        WINDOW = 30            # window is [T-29, T]
        MIN_FAILURES = 5
        IMPACT_PERCENT = 1     # errors must exceed 1% of successes

        successes = {}   # merchant -> deque[(ts, count)] of status-200 logs
        success_sum = {} # merchant -> running count of successes in the deque
        errors = {}      # merchant -> {code: deque[(ts, count)]}
        error_sum = {}   # merchant -> {code: running count}
        active = set()   # (merchant, code) pairs with a live alert
        events = []      # (timestamp, merchant, code, event_type)

        for raw in logs:
            if not raw or not raw.strip():
                continue
            ts_s, merchant, code, cnt_s = (p.strip() for p in raw.split(",")[:4])
            ts, cnt = int(ts_s), int(cnt_s)

            # ---- record the entry -------------------------------------------
            if code == "200":
                successes.setdefault(merchant, deque()).append((ts, cnt))
                success_sum[merchant] = success_sum.get(merchant, 0) + cnt
            else:
                errors.setdefault(merchant, {}).setdefault(code, deque()).append((ts, cnt))
                sums = error_sum.setdefault(merchant, {})
                sums[code] = sums.get(code, 0) + cnt

            # ---- evict everything older than the window for this merchant ----
            lo = ts - (WINDOW - 1)
            sq = successes.get(merchant)
            if sq:
                while sq and sq[0][0] < lo:
                    success_sum[merchant] -= sq.popleft()[1]
            ok_count = success_sum.get(merchant, 0)

            # ---- evaluate every error code this merchant has ever logged ------
            for err_code in sorted(errors.get(merchant, {})):
                eq = errors[merchant][err_code]
                while eq and eq[0][0] < lo:
                    error_sum[merchant][err_code] -= eq.popleft()[1]
                failures = error_sum[merchant][err_code]

                meets = failures >= MIN_FAILURES and failures * 100 > ok_count * IMPACT_PERCENT
                key = (merchant, err_code)
                if meets and key not in active:
                    active.add(key)
                    events.append((ts, merchant, err_code, "TRIGGER"))
                elif not meets and key in active:
                    active.discard(key)
                    events.append((ts, merchant, err_code, "RESOLVE"))

        # ---- output ordering: (timestamp, merchant, status_code, event_type) ---
        events.sort(key=lambda e: (e[0], e[1], e[2], e[3]))
        return [f"{ts},{etype},{merchant},{code}" for ts, merchant, code, etype in events]


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().detectIncidents

    # Example 1 (Part 1)
    assert f(["10,merchant1,500,2", "10,merchant2,500,1", "15,merchant1,500,2",
              "20,merchant1,500,1", "20,merchant2,500,4"]) == \
        ["20,TRIGGER,merchant1,500", "20,TRIGGER,merchant2,500"]
    # Example 2 (Part 2: exactly 1% does not trigger, > 1% does)
    assert f(["10,merchant1,200,600", "12,merchant1,500,6",
              "15,merchant2,200,599", "16,merchant2,500,6"]) == ["16,TRIGGER,merchant2,500"]

    # Window is [T-29, T]: errors at t=10 are inside the window at t=39, outside at t=40.
    assert f(["10,m,500,4", "39,m,500,1"]) == ["39,TRIGGER,m,500"]
    assert f(["10,m,500,4", "40,m,500,1"]) == []
    # De-duplication: conditions persisting never re-trigger.
    assert f(["10,m,500,5", "11,m,500,5", "12,m,500,5"]) == ["10,TRIGGER,m,500"]
    # Part 3: resolve when the window no longer meets the conditions, then re-trigger.
    assert f(["10,m,500,5", "45,m,500,1", "50,m,500,4"]) == \
        ["10,TRIGGER,m,500", "45,RESOLVE,m,500", "50,TRIGGER,m,500"]
    # Resolve caused by a burst of successes dropping impact to <= 1%.
    assert f(["10,m,500,5", "11,m,200,500"]) == ["10,TRIGGER,m,500", "11,RESOLVE,m,500"]
    # One alert per (merchant, status_code); 404 and 500 are independent.
    assert f(["10,m,404,5", "10,m,500,5"]) == ["10,TRIGGER,m,404", "10,TRIGGER,m,500"]
    # Failures below the volume threshold never trigger, whatever the impact.
    assert f(["10,m,500,4"]) == []
    # A log for another merchant does not touch this merchant's alerts.
    assert f(["10,a,500,5", "45,b,200,1"]) == ["10,TRIGGER,a,500"]
    # Output ordering: status_code sorts before event_type at the same (ts, merchant).
    assert f(["10,m,500,5", "40,m,404,5", "40,m,500,1"]) == \
        ["10,TRIGGER,m,500", "40,TRIGGER,m,404", "40,RESOLVE,m,500"]
    # Same pair, same timestamp: RESOLVE sorts before TRIGGER (alphabetical event_type).
    assert f(["10,m,500,5", "40,m,500,1", "40,m,200,1", "40,m,500,4"]) == \
        ["10,TRIGGER,m,500", "40,RESOLVE,m,500", "40,TRIGGER,m,500"]
    # Empty input.
    assert f([]) == []

    print("All tests passed.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        data = [l.rstrip("\n") for l in sys.stdin if l.strip()]
        if not data:
            _run_tests()
        else:
            print("\n".join(Solution().detectIncidents(data)))
