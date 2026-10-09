"""
Stripe OA: Asynchronous Payment Event Processing
https://www.fastprep.io/problems/stripe-asynchronous-payment-event-processing

processEvents(events) -> String[]

Each event: "event_id,event_time,event_type,payment_id,payment_event_type,merchant_id,amount"
with "-" for an absent value.  event_type is payment | refund | merchant_update.

Output one row per payment, in the order their create event was first processed:
    payment_id,merchant_id,state,amount_authorized,amount_captured,last_event_at

Rules
* An event_id is processed at most once.  The first row with an id consumes it even
  if that row turns out to be an invalid transition.
* Valid transitions (anything else is ignored and changes nothing):
      non-existent         : create
      created              : authorize
      authorized           : authorize, capture
      partially_captured   : capture
      successful           : refund
      refunded             : -
  authorize adds to amount_authorized; capture adds to amount_captured and the state
  becomes successful when amount_captured == amount_authorized, else partially_captured.
  refund changes only state (-> refunded) and last_event_at.
* merchant_update carries a risk score in the amount column.  A score >= 80 blocks the
  merchant permanently; afterwards every authorize for that merchant is ignored, while
  create, capture and refund still work.  The update itself touches no payment.
* last_event_at is updated only by events that were actually applied.

    ["evt_1,0,payment,payment_1,create,merchant_1,-",
     "evt_3,2,payment,payment_1,authorize,-,10",
     "evt_5,4,payment,payment_1,capture,-,10"]
        -> ["payment_1,merchant_1,successful,10,10,4"]
"""

from typing import List


class Solution:
    def processEvents(self, events: List[str]) -> List[str]:
        BLOCK_THRESHOLD = 80

        seen_ids = set()
        blocked = set()          # merchant ids that are permanently blocked
        payments = {}            # payment_id -> dict(merchant, state, authorized, captured, last)
        order = []               # payment ids in creation order

        for raw in events:
            if not raw or not raw.strip():
                continue
            fields = [p.strip() for p in raw.split(",")]
            while len(fields) < 7:
                fields.append("-")
            event_id, time_s, event_type, payment_id, pay_event, merchant_id, amount_s = fields[:7]

            # ---- de-duplication: first occurrence consumes the id, valid or not ----
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            event_time = int(time_s) if time_s not in ("", "-") else 0
            amount = int(amount_s) if amount_s not in ("", "-") else 0

            # ---------------------------------------------------- merchant_update
            if event_type == "merchant_update":
                if merchant_id not in ("", "-") and amount >= BLOCK_THRESHOLD:
                    blocked.add(merchant_id)
                continue

            # ------------------------------------------------------------ refund
            if event_type == "refund":
                p = payments.get(payment_id)
                if p is not None and p["state"] == "successful":
                    p["state"] = "refunded"
                    p["last"] = event_time
                continue

            # ----------------------------------------------------------- payment
            if event_type != "payment":
                continue
            p = payments.get(payment_id)

            if pay_event == "create":
                if p is not None:
                    continue  # duplicate create for an existing payment: invalid
                payments[payment_id] = {
                    "merchant": merchant_id if merchant_id != "-" else "",
                    "state": "created",
                    "authorized": 0,
                    "captured": 0,
                    "last": event_time,
                }
                order.append(payment_id)
                continue

            if p is None:
                continue  # authorize/capture for a payment that does not exist

            if pay_event == "authorize":
                if p["state"] not in ("created", "authorized"):
                    continue
                if p["merchant"] in blocked:
                    continue  # blocked merchants get no new authorizations
                p["authorized"] += amount
                p["state"] = "authorized"
                p["last"] = event_time
                continue

            if pay_event == "capture":
                if p["state"] not in ("authorized", "partially_captured"):
                    continue
                p["captured"] += amount
                p["state"] = "successful" if p["captured"] >= p["authorized"] else "partially_captured"
                p["last"] = event_time
                continue
            # unknown payment_event_type: ignored

        return [
            f"{pid},{payments[pid]['merchant']},{payments[pid]['state']},"
            f"{payments[pid]['authorized']},{payments[pid]['captured']},{payments[pid]['last']}"
            for pid in order
        ]


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().processEvents

    # Example 1 (Part 1)
    assert f(["evt_1,0,payment,payment_1,create,merchant_1,-", "evt_2,1,payment,payment_2,create,merchant_2,-",
              "evt_3,2,payment,payment_1,authorize,-,10", "evt_4,3,payment,payment_2,authorize,-,25",
              "evt_5,4,payment,payment_1,capture,-,10", "evt_6,5,payment,payment_2,capture,-,5"]) == \
        ["payment_1,merchant_1,successful,10,10,4", "payment_2,merchant_2,partially_captured,25,5,5"]
    # Example 2 (duplicate event id ignored)
    assert f(["evt_1,0,payment,payment_1,create,merchant_1,-", "evt_2,1,payment,payment_2,create,merchant_2,-",
              "evt_3,2,payment,payment_1,authorize,-,10", "evt_4,3,payment,payment_1,authorize,-,10",
              "evt_5,4,payment,payment_2,authorize,-,15", "evt_6,5,payment,payment_1,capture,-,10",
              "evt_6,5,payment,payment_1,capture,-,10", "evt_7,6,payment,payment_2,capture,-,15"]) == \
        ["payment_1,merchant_1,partially_captured,20,10,5", "payment_2,merchant_2,successful,15,15,6"]
    # Example 3 (Part 2: out-of-order events ignored)
    assert f(["evt_1,0,payment,payment_1,create,merchant_1,-", "evt_2,1,payment,payment_2,capture,-,20",
              "evt_3,2,payment,payment_1,capture,-,10", "evt_4,3,payment,payment_2,create,merchant_2,-",
              "evt_5,4,payment,payment_1,authorize,-,10", "evt_6,5,payment,payment_2,authorize,-,20",
              "evt_7,6,payment,payment_1,capture,-,10", "evt_8,7,payment,payment_1,authorize,-,5",
              "evt_9,8,payment,payment_2,capture,-,10", "evt_10,9,payment,payment_2,capture,-,10"]) == \
        ["payment_1,merchant_1,successful,10,10,6", "payment_2,merchant_2,successful,20,20,9"]
    # Example 4 (Part 3: refunds; second refund ignored)
    assert f(["evt_1,0,payment,payment_1,create,merchant_1,-", "evt_2,1,payment,payment_2,create,merchant_2,-",
              "evt_3,2,payment,payment_1,authorize,-,10", "evt_4,3,payment,payment_2,authorize,-,20",
              "evt_5,4,payment,payment_1,capture,-,10", "evt_6,5,payment,payment_2,capture,-,20",
              "evt_7,6,refund,payment_1,-,-,-", "evt_8,7,refund,payment_2,-,-,-",
              "evt_9,8,refund,payment_1,-,-,-"]) == \
        ["payment_1,merchant_1,refunded,10,10,6", "payment_2,merchant_2,refunded,20,20,7"]
    # Example 5 (Part 4: merchant blocked; later low score does not unblock)
    assert f(["evt_1,0,payment,payment_1,create,merchant_1,-", "evt_2,1,payment,payment_1,authorize,-,10",
              "evt_3,2,merchant_update,-,-,merchant_1,85", "evt_4,3,payment,payment_2,create,merchant_1,-",
              "evt_5,4,payment,payment_2,authorize,-,20", "evt_6,5,payment,payment_1,capture,-,10",
              "evt_7,6,merchant_update,-,-,merchant_1,10"]) == \
        ["payment_1,merchant_1,successful,10,10,5", "payment_2,merchant_1,created,0,0,3"]

    # Invalid first row still consumes its event id: the later valid row with that id is dropped.
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,payment,p,capture,-,5",
              "evt_2,2,payment,p,authorize,-,5"]) == ["p,m,created,0,0,0"]
    # Refund is only valid from successful; partially_captured payment ignores it.
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,payment,p,authorize,-,10",
              "evt_3,2,payment,p,capture,-,4", "evt_4,3,refund,p,-,-,-"]) == ["p,m,partially_captured,10,4,2"]
    # Refunded payment accepts nothing further.
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,payment,p,authorize,-,10",
              "evt_3,2,payment,p,capture,-,10", "evt_4,3,refund,p,-,-,-",
              "evt_5,4,payment,p,authorize,-,1", "evt_6,5,payment,p,capture,-,1"]) == ["p,m,refunded,10,10,3"]
    # Exactly 80 blocks; 79 does not.
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,merchant_update,-,-,m,80",
              "evt_3,2,payment,p,authorize,-,10"]) == ["p,m,created,0,0,0"]
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,merchant_update,-,-,m,79",
              "evt_3,2,payment,p,authorize,-,10"]) == ["p,m,authorized,10,0,2"]
    # Blocked merchant: authorized payment still captures; second authorize is ignored.
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,payment,p,authorize,-,10",
              "evt_3,2,merchant_update,-,-,m,99", "evt_4,3,payment,p,authorize,-,10",
              "evt_5,4,payment,p,capture,-,10", "evt_6,5,refund,p,-,-,-"]) == ["p,m,refunded,10,10,5"]
    # Blocking is per merchant.
    assert f(["evt_1,0,payment,p,create,a,-", "evt_2,1,payment,q,create,b,-",
              "evt_3,2,merchant_update,-,-,a,90", "evt_4,3,payment,p,authorize,-,1",
              "evt_5,4,payment,q,authorize,-,1"]) == ["p,a,created,0,0,0", "q,b,authorized,1,0,4"]
    # Duplicate create for an existing payment is ignored; output order is creation order.
    assert f(["evt_1,5,payment,b,create,m,-", "evt_2,6,payment,a,create,m,-",
              "evt_3,7,payment,b,create,other,-"]) == ["b,m,created,0,0,5", "a,m,created,0,0,6"]
    # Multiple authorizes accumulate; capture reaching the total is successful.
    assert f(["evt_1,0,payment,p,create,m,-", "evt_2,1,payment,p,authorize,-,5",
              "evt_3,2,payment,p,authorize,-,5", "evt_4,3,payment,p,capture,-,3",
              "evt_5,4,payment,p,capture,-,7"]) == ["p,m,successful,10,10,4"]
    assert f([]) == []


    # ---- Randomized cross-check against a table-driven reference ----
    import random

    def ref_events(events):
        VALID = {None: {"create"}, "created": {"authorize"}, "authorized": {"authorize", "capture"},
                 "partially_captured": {"capture"}, "successful": {"refund"}, "refunded": set()}
        seen, blocked, pay, order = set(), set(), {}, []
        for e in events:
            eid, t, et, pid, pet, mid, amt = e.split(",")
            if eid in seen:
                continue
            seen.add(eid)
            t = int(t)
            if et == "merchant_update":
                if int(amt) >= 80:
                    blocked.add(mid)
                continue
            action = "refund" if et == "refund" else pet
            state = pay[pid]["state"] if pid in pay else None
            if action not in VALID[state]:
                continue
            if action == "create":
                pay[pid] = {"m": mid, "state": "created", "a": 0, "c": 0, "t": t}; order.append(pid)
            elif action == "authorize":
                if pay[pid]["m"] in blocked:
                    continue
                pay[pid]["a"] += int(amt); pay[pid]["state"] = "authorized"; pay[pid]["t"] = t
            elif action == "capture":
                pay[pid]["c"] += int(amt); pay[pid]["t"] = t
                if pay[pid]["c"] > pay[pid]["a"]:
                    return None  # input violates "captured never exceeds authorized"
                pay[pid]["state"] = "successful" if pay[pid]["c"] == pay[pid]["a"] else "partially_captured"
            else:
                pay[pid]["state"] = "refunded"; pay[pid]["t"] = t
        return [f"{p},{pay[p]['m']},{pay[p]['state']},{pay[p]['a']},{pay[p]['c']},{pay[p]['t']}" for p in order]

    rng = random.Random(3)
    for _ in range(400):
        events, auth = [], {}
        for i in range(rng.randint(1, 30)):
            eid = f"e{rng.randint(1, 20)}"  # small id space => duplicates
            pid = rng.choice(["p1", "p2", "p3"]); mid = rng.choice(["m1", "m2"])
            r = rng.random()
            if r < 0.15:
                events.append(f"{eid},{i},merchant_update,-,-,{mid},{rng.choice([10, 79, 80, 95])}")
            elif r < 0.3:
                events.append(f"{eid},{i},refund,{pid},-,-,-")
            elif r < 0.5:
                events.append(f"{eid},{i},payment,{pid},create,{mid},-")
            elif r < 0.75:
                a = rng.choice([5, 10]); auth[pid] = auth.get(pid, 0) + a
                events.append(f"{eid},{i},payment,{pid},authorize,-,{a}")
            else:
                events.append(f"{eid},{i},payment,{pid},capture,-,{rng.choice([5, 10])}")
        expected = ref_events(events)
        if expected is None:
            continue  # generator broke the input guarantee; not a valid test case
        assert f(events) == expected, events
    print("All tests passed (including randomized cross-checks).")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        # STDIN format: first line n, then n event lines.
        data = [l.rstrip("\n") for l in sys.stdin if l.strip()]
        if not data:
            _run_tests()
        else:
            if data[0].strip().isdigit():
                data = data[1:1 + int(data[0])]
            print("\n".join(Solution().processEvents(data)))
