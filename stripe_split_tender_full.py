"""
Stripe OA: Split Tender Transactions, Parts 1-4
(basic split tendering, expiration dates, ZIP-code surcharges, refunds)

process_events(events, surcharge_rates) -> list[str]

Events arrive in chronological order (equal timestamps keep input order):
    timestamp,ADD_GIFTCARD,customer_id,card_id,amount,valid_before
    timestamp,CHARGE,charge_id,customer_id,amount,zip_code
    timestamp,REFUND,charge_id,refund_amount
surcharge_rates entries look like "start_zip-end_zip:rate" (non-overlapping, inclusive
ranges, e.g. "90000-99999:0.05").

One output string per input event, in the same order:
* ADD_GIFTCARD -> ""
* CHARGE       -> "CC_CHARGE[,card_id:amount_used ...]"
      Gift cards pay first, the credit card takes the remainder.
      Part 2: at charge time T a card is usable only if T < valid_before; once T is at
      or after valid_before the card's balance is voided for good.  Cards are drained
      earliest-expiring first (ties: lexicographically smaller card_id first), one card
      completely before the next; cards with no expiry come after every expiring card.
      The cards listed in the output are sorted lexicographically by card_id.
      Part 3: CC_CHARGE = cc_portion + cc_portion * rate, where rate belongs to the
      surcharge range the zip_code falls into (0 if none).  Gift-card money is never
      surcharged.
* REFUND       -> "CC_REFUND,GC_REFUND"
      Part 4: refund_amount goes back to the credit card first, up to what that charge
      actually put on the credit card (surcharge included); anything beyond that is
      store credit: a new never-expiring gift card "REFUND_<charge_id>" for the same
      customer, which later charges use like any other card.

    events = ["1,ADD_GIFTCARD,cust1,gc1,5000,10", "2,CHARGE,chg1,cust1,15000,90210",
              "3,REFUND,chg1,12000"],  surcharge_rates = ["90000-99999:0.05"]
        -> ["", "10500,gc1:5000", "10500,1500"]

Money is kept as exact integer hundredths, so 12.50 and 5000 are both handled exactly.
"""

import heapq
import re
from bisect import bisect_right
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional

# Number style of the output.  The assessment's examples print whole amounts without
# decimals ("0", "10500", "10.5"); set this to True for a judge that always wants two
# decimals ("0.00", "10500.00", "10.50" -- the fastprep.io version of Part 1 does).
TWO_DECIMALS = False


def _to_cents(text: str) -> int:
    """'12.5' -> 1250, '5000' -> 500000.  Exact decimal arithmetic; 0 if unparsable."""
    try:
        return int((Decimal(text.strip()) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0


def _fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    if TWO_DECIMALS:
        return f"{sign}{whole}.{frac:02d}"
    if frac == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{frac:02d}".rstrip("0")


def _number(text: str) -> Optional[Decimal]:
    """Numeric value of a timestamp / rate field, or None when it is not a number."""
    try:
        value = Decimal(text.strip())
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _card_key(valid_before: str, card_id: str):
    """Heap priority: expiring cards by (valid_before, card_id), then non-expiring ones
    by card_id.  A missing, blank, non-numeric or negative valid_before means 'never'."""
    expiry = _number(valid_before)
    if expiry is None or expiry < 0:
        return (1, Decimal(0), card_id)
    return (0, expiry, card_id)


class _SurchargeTable:
    """'start-end:rate' ranges with O(log m) lookup by ZIP code."""

    _ROW = re.compile(r"\s*(\d+)\s*-\s*(\d+)\s*:\s*([0-9.]+)\s*(%?)\s*$")
    _ZIP = re.compile(r"\s*(\d+)")

    def __init__(self, rates: Optional[List[str]]):
        rows = []
        for raw in rates or []:
            m = self._ROW.match(raw or "")
            rate = _number(m.group(3)) if m else None
            if rate is None:
                continue
            if m.group(4):                       # "5%" -> 0.05
                rate /= 100
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            rows.append((lo, hi, rate))
        rows.sort()
        self._rows = rows
        self._starts = [lo for lo, _, _ in rows]

    def rate(self, zip_code: str) -> Decimal:
        m = self._ZIP.match(zip_code or "")
        if not m or not self._rows:
            return Decimal(0)
        z = int(m.group(1))
        i = bisect_right(self._starts, z) - 1
        if i >= 0 and self._rows[i][0] <= z <= self._rows[i][1]:
            return self._rows[i][2]
        return Decimal(0)


class Solution:
    def processEvents(self, events: List[str],
                      surcharge_rates: Optional[List[str]] = None) -> List[str]:
        table = _SurchargeTable(surcharge_rates)
        cards = {}      # customer_id -> min-heap of [key, card_id, balance_cents]
        charges = {}    # charge_id -> [customer_id, credit-card cents still refundable]
        out = []

        for raw in events:
            parts = [p.strip() for p in raw.split(",")] if raw else []
            kind = parts[1].upper() if len(parts) > 1 else ""

            if kind == "ADD_GIFTCARD" and len(parts) >= 5:
                customer, card_id = parts[2], parts[3]
                amount = _to_cents(parts[4])
                if amount > 0:
                    valid_before = parts[5] if len(parts) > 5 else ""
                    heapq.heappush(cards.setdefault(customer, []),
                                   [_card_key(valid_before, card_id), card_id, amount])
                out.append("")

            elif kind == "CHARGE" and len(parts) >= 5:
                charge_id, customer = parts[2], parts[3]
                now = _number(parts[0])
                remaining = _to_cents(parts[4])
                zip_code = parts[5] if len(parts) > 5 else ""
                heap = cards.get(customer)
                used = []
                if heap:
                    # Part 2: the heap is ordered by expiry, so every expired card
                    # (valid_before <= now) sits on top.  Void them for good.
                    if now is not None:
                        while heap and heap[0][0][0] == 0 and heap[0][0][1] <= now:
                            heapq.heappop(heap)
                    while remaining > 0 and heap:
                        top = heap[0]
                        take = min(top[2], remaining)
                        top[2] -= take
                        remaining -= take
                        used.append((top[1], take))
                        if top[2] == 0:
                            heapq.heappop(heap)     # drained: no longer active
                used.sort()                         # output order: lexicographic card_id
                # Part 3: surcharge only the credit-card portion.
                cc = remaining
                rate = table.rate(zip_code)
                if cc and rate:
                    cc += int((cc * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                charges[charge_id] = [customer, cc]
                out.append(",".join([_fmt(cc)] + [f"{cid}:{_fmt(amt)}" for cid, amt in used]))

            elif kind == "REFUND" and len(parts) >= 4:
                charge_id = parts[2]
                amount = _to_cents(parts[3])
                record = charges.get(charge_id)
                if record is None:                  # never happens per the statement
                    out.append(f"{_fmt(0)},{_fmt(0)}")
                    continue
                cc_refund = min(amount, record[1])  # Part 4: real dollars first ...
                record[1] -= cc_refund
                gc_refund = amount - cc_refund      # ... then store credit
                if gc_refund > 0:
                    card_id = f"REFUND_{charge_id}"
                    heapq.heappush(cards.setdefault(record[0], []),
                                   [_card_key("", card_id), card_id, gc_refund])
                out.append(f"{_fmt(cc_refund)},{_fmt(gc_refund)}")

            else:
                out.append("")                      # blank / unknown event types

        return out


def process_events(events: List[str], surcharge_rates: Optional[List[str]] = None) -> List[str]:
    return Solution().processEvents(events, surcharge_rates)


processEvents = process_events


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    global TWO_DECIMALS
    f = process_events

    # ---- Examples from the assessment (Parts 2, 3, 4) ----
    assert f(["1,ADD_GIFTCARD,cust1,gc1,5000,10", "2,ADD_GIFTCARD,cust1,gc2,4000,5",
              "3,CHARGE,chg1,cust1,6000,10000", "11,CHARGE,chg2,cust1,1000,10000"]) == \
        ["", "", "0,gc1:2000,gc2:4000", "1000"]
    assert f(["1,ADD_GIFTCARD,cust1,gc1,5000,10", "2,CHARGE,chg1,cust1,15000,90210"],
             ["80000-89999:0.02", "90000-99999:0.05"]) == ["", "10500,gc1:5000"]
    assert f(["1,ADD_GIFTCARD,cust1,gc1,5000,10", "2,CHARGE,chg1,cust1,15000,90210",
              "3,REFUND,chg1,12000"], ["90000-99999:0.05"]) == \
        ["", "10500,gc1:5000", "10500,1500"]

    # ---- Part 1 behaviour still holds ----
    assert f(["1,CHARGE,ch1,cust1,12.50,94105"]) == ["12.5"]
    assert f(["1,ADD_GIFTCARD,c,gc1,10,99", "2,CHARGE,x1,c,10,10000", "3,CHARGE,x2,c,5,10000",
              "4,ADD_GIFTCARD,c,gc2,3,99", "5,CHARGE,x3,c,5,10000"]) == \
        ["", "0,gc1:10", "5", "", "2,gc2:3"]
    assert f(["1,ADD_GIFTCARD,alice,g1,100,9", "2,CHARGE,c1,bob,40,10000",
              "3,CHARGE,c2,alice,40,10000"]) == ["", "40", "0,g1:40"]
    assert f(["1,ADD_GIFTCARD,c,g0,0,9", "2,CHARGE,x,c,1,10000", "3,CHARGE,y,c,0,10000"]) == \
        ["", "1", "0"]
    assert f([]) == [] and f(["", "7,BOGUS,x"]) == ["", ""]

    # ---- Part 2: expiry is strict (T < valid_before), voided cards never come back ----
    assert f(["1,ADD_GIFTCARD,c,g,100,5", "4,CHARGE,a,c,30,10000", "5,CHARGE,b,c,30,10000",
              "6,ADD_GIFTCARD,c,h,10,9", "6,CHARGE,d,c,30,10000"]) == \
        ["", "0,g:30", "30", "", "20,h:10"]
    # Earliest expiry first, ties by card_id, never-expiring cards last; output sorted.
    assert f(["1,ADD_GIFTCARD,c,zz,10,20", "2,ADD_GIFTCARD,c,aa,10,20", "3,ADD_GIFTCARD,c,mm,10,",
              "4,ADD_GIFTCARD,c,bb,10,30", "5,CHARGE,x,c,25,10000"]) == \
        ["", "", "", "", "0,aa:10,bb:5,zz:10"]
    assert f(["1,ADD_GIFTCARD,c,mm,10,", "2,ADD_GIFTCARD,c,aa,10,30", "3,CHARGE,x,c,15,10000",
              "40,CHARGE,y,c,15,10000"]) == ["", "", "0,aa:10,mm:5", "10,mm:5"]
    # A card that is already expired when added is simply never usable.
    assert f(["5,ADD_GIFTCARD,c,g,10,5", "5,CHARGE,x,c,1,10000"]) == ["", "1"]
    # Missing valid_before field / negative sentinel both mean "never expires".
    assert f(["1,ADD_GIFTCARD,c,g,10", "1,ADD_GIFTCARD,c,h,10,-1", "99,CHARGE,x,c,15,1"]) == \
        ["", "", "0,g:10,h:5"]

    # ---- Part 3: surcharge on the credit-card portion only, inclusive ranges ----
    rates = ["80000-89999:0.02", "90000-99999:0.05", "00000-09999:0.5"]
    assert f(["1,CHARGE,a,c,100,80000", "2,CHARGE,b,c,100,89999", "3,CHARGE,d,c,100,79999",
              "4,CHARGE,e,c,100,02134", "5,CHARGE,g,c,100,10000", "6,CHARGE,h,c,0,90210"],
             rates) == ["102", "102", "100", "150", "100", "0"]
    assert f(["1,ADD_GIFTCARD,c,g,60,9", "2,CHARGE,a,c,100,95000"], rates) == ["", "42,g:60"]
    assert f(["1,CHARGE,a,c,10001,90210"], ["90000-99999:0.05"]) == ["10501.05"]
    assert f(["1,CHARGE,a,c,100,90210"], None) == ["100"]
    assert f(["1,CHARGE,a,c,100,90210"], ["90000-99999:5%", " 10-20 : 0.1 "]) == ["105"]

    # ---- Part 4: refunds ----
    # Fully covered by the credit card: no store-credit card is created.
    assert f(["1,ADD_GIFTCARD,c,g,50,9", "2,CHARGE,a,c,150,90210", "3,REFUND,a,100",
              "4,CHARGE,b,c,10,10000"], ["90000-99999:0.05"]) == \
        ["", "105,g:50", "100,0", "10"]
    # Whole paid amount refunded: credit card gets exactly its 105, the rest is a card.
    assert f(["1,ADD_GIFTCARD,c,g,50,9", "2,CHARGE,a,c,150,90210", "3,REFUND,a,155",
              "4,CHARGE,b,c,60,10000"], ["90000-99999:0.05"]) == \
        ["", "105,g:50", "105,50", "10,REFUND_a:50"]
    # Charge paid entirely by gift card: everything comes back as store credit.
    assert f(["1,ADD_GIFTCARD,c,g,50,9", "2,CHARGE,a,c,30,10000", "3,REFUND,a,30"]) == \
        ["", "0,g:30", "0,30"]
    # Refund cards never expire, are used after expiring cards and sort in the output
    # ('R' < 'g' in ASCII), and go to the charge's customer.
    assert f(["1,ADD_GIFTCARD,c,gc1,5000,10", "2,CHARGE,chg1,c,15000,90210",
              "3,REFUND,chg1,12000", "4,ADD_GIFTCARD,c,gc2,1000,9", "5,CHARGE,chg2,c,2000,10000",
              "12,CHARGE,chg3,c,1000,10000", "13,CHARGE,chg4,d,1,10000"],
             ["90000-99999:0.05"]) == \
        ["", "10500,gc1:5000", "10500,1500", "", "0,REFUND_chg1:1000,gc2:1000",
         "500,REFUND_chg1:500", "1"]
    # Refund of a charge that was itself paid with a refund card (chained store credit).
    assert f(["1,ADD_GIFTCARD,c,g,10,99", "2,CHARGE,a,c,10,10000", "3,REFUND,a,10",
              "4,CHARGE,b,c,10,10000", "5,REFUND,b,10", "6,CHARGE,d,c,10,10000"]) == \
        ["", "0,g:10", "0,10", "0,REFUND_a:10", "0,10", "0,REFUND_b:10"]
    # Unknown charge id: nothing to refund (never happens per the statement).
    assert f(["1,REFUND,nope,5"]) == ["0,0"]

    # ---- Two-decimal output style (fastprep.io Part 1 examples) ----
    TWO_DECIMALS = True
    try:
        assert f(["1,ADD_GIFTCARD,cust1,gc1,50,10", "2,ADD_GIFTCARD,cust2,gc2,20,15",
                  "3,CHARGE,chg1,cust2,30,10000", "4,CHARGE,chg2,cust1,30,10000"]) == \
            ["", "", "10.00,gc2:20.00", "0.00,gc1:30.00"]
        assert f(["1,CHARGE,ch1,cust1,12.50,94105"]) == ["12.50"]
        assert f(["1,ADD_GIFTCARD,cust1,gc1,25.50,50", "2,CHARGE,ch1,cust1,10.25,10000",
                  "3,CHARGE,ch2,cust1,20.00,10000"]) == ["", "0.00,gc1:10.25", "4.75,gc1:15.25"]
        assert f(["1,CHARGE,a,c,10001,90210", "2,REFUND,a,10501"], ["90000-99999:0.05"]) == \
            ["10501.05", "10501.00,0.00"]
    finally:
        TWO_DECIMALS = False

    # ---- Randomized cross-check against a brute-force reference ----
    import random

    def ref_fmt(d: Decimal) -> str:
        q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return str(int(q)) if q == q.to_integral_value() else format(q.normalize(), "f")

    def ref_events(evs, rates):
        ranges = []
        for r in rates:
            lohi, rate = r.split(":")
            lo, hi = lohi.split("-")
            ranges.append((int(lo), int(hi), Decimal(rate)))
        cards, charges, out = {}, {}, []
        for e in evs:
            p = e.split(",")
            t = Decimal(p[0])
            if p[1] == "ADD_GIFTCARD":
                exp = Decimal(p[5]) if p[5] != "" else None
                cards.setdefault(p[2], []).append([p[3], Decimal(p[4]), exp])
                out.append("")
            elif p[1] == "CHARGE":
                cust, amt, z = p[3], Decimal(p[4]), int(p[5])
                live = [c for c in cards.get(cust, []) if c[2] is None or t < c[2]]
                live.sort(key=lambda c: (c[2] is None, c[2] if c[2] is not None else 0, c[0]))
                used = []
                for c in live:
                    take = min(c[1], amt)
                    if take > 0:
                        c[1] -= take
                        amt -= take
                        used.append((c[0], take))
                cards[cust] = [c for c in live if c[1] > 0]
                rate = next((r for lo, hi, r in ranges if lo <= z <= hi), Decimal(0))
                cc = (amt + amt * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                charges[p[2]] = [cust, cc]
                out.append(",".join([ref_fmt(cc)] + [f"{cid}:{ref_fmt(a)}" for cid, a in sorted(used)]))
            else:
                cust, cc_left = charges[p[2]]
                amt = Decimal(p[3])
                ccr = min(amt, cc_left)
                charges[p[2]][1] -= ccr
                gcr = amt - ccr
                if gcr > 0:
                    cards.setdefault(cust, []).append([f"REFUND_{p[2]}", gcr, None])
                out.append(f"{ref_fmt(ccr)},{ref_fmt(gcr)}")
        return out

    rng = random.Random(2024)
    for _ in range(600):
        rates = []
        lo = 0
        while lo <= 99999 and rng.random() < 0.7:
            hi = min(99999, lo + rng.randint(0, 40000))
            rates.append(f"{lo:05d}-{hi:05d}:{rng.choice(['0.05', '0.1', '0.2', '0.25', '0.5', '1'])}")
            lo = hi + 1 + rng.randint(0, 20000)
        evs, ts, card_no, open_charges = [], 0, 0, []
        for _ in range(rng.randint(1, 40)):
            ts += rng.randint(0, 3)
            cust = rng.choice(["c1", "c2", "c3"])
            amt = rng.choice([rng.randint(0, 50), rng.randint(0, 50), rng.randint(0, 5000) / 100])
            roll = rng.random()
            if roll < 0.35:
                card_no += 1
                exp = "" if rng.random() < 0.2 else str(ts + rng.randint(0, 8))
                evs.append(f"{ts},ADD_GIFTCARD,{cust},gc{card_no},{amt},{exp}")
            elif roll < 0.8 or not open_charges:
                cid = f"ch{len(evs)}"
                evs.append(f"{ts},CHARGE,{cid},{cust},{amt},{rng.randint(0, 99999):05d}")
                open_charges.append((cid, amt))
            else:
                cid, paid = open_charges.pop(rng.randrange(len(open_charges)))
                refund = rng.choice([paid, round(paid * rng.random(), 2), 0])
                evs.append(f"{ts},REFUND,{cid},{refund}")
        assert f(evs, rates) == ref_events(evs, rates), (evs, rates)

    # ---- Large input smoke test ----
    import time
    big = []
    for i in range(100_000):
        c = f"cust{i % 5000}"
        if i % 3 == 0:
            big.append(f"{i},ADD_GIFTCARD,{c},card{i},{i % 977},{i + 100 + (i % 7) * 1000}")
        elif i % 3 == 1:
            big.append(f"{i},CHARGE,ch{i},{c},{i % 1313},{(i * 7919) % 100000:05d}")
        else:
            big.append(f"{i},REFUND,ch{i - 1},{(i % 1313) // 2}")
    t0 = time.perf_counter()
    res = f(big, ["00000-49999:0.02", "50000-99999:0.05"])
    elapsed = time.perf_counter() - t0
    assert len(res) == len(big) and elapsed < 10, elapsed
    print(f"All tests passed (including randomized cross-checks); large case {elapsed:.2f}s.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        # stdin: one event per line; lines shaped like "90000-99999:0.05" are surcharge rates.
        events, rates = [], []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            (rates if re.match(r"\d+\s*-\s*\d+\s*:", line) else events).append(line)
        if not events:
            _run_tests()
        else:
            print("\n".join(process_events(events, rates)))
