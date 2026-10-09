"""
Stripe OA: Split Tender Transactions, Part 1 - Basic Split Tendering
https://www.fastprep.io/problems/stripe-split-tender-basic

processEvents(events) -> String[]

Events arrive in chronological order (equal timestamps keep input order) and use
one of these schemas:
    timestamp,ADD_GIFTCARD,customer_id,card_id,amount,valid_before
    timestamp,CHARGE,charge_id,customer_id,amount,zip_code
    timestamp,REFUND,charge_id,refund_amount            (later parts only)

One output string per input event, in the same order:
* ADD_GIFTCARD  adds amount to that customer's gift-card balance        -> ""
* CHARGE        pays from the customer's gift cards first and puts the rest on the
                credit card -> "CC_AMOUNT[,CARD_ID:AMOUNT_USED ...]".  Cards that
                were not debited are not listed.
* anything else (e.g. REFUND)                                            -> ""

Amounts have at most two decimals and are printed with exactly two ("0.00").
Part 1 ignores valid_before and zip_code (no expiry, no surcharge) and promises at
most one active gift card per customer; several cards are supported anyway and are
drained in (valid_before, card_id) order, the priority the later parts describe.

    ["1,ADD_GIFTCARD,cust1,gc1,50,10", "2,ADD_GIFTCARD,cust2,gc2,20,15",
     "3,CHARGE,chg1,cust2,30,10000", "4,CHARGE,chg2,cust1,30,10000"]
        -> ["", "", "10.00,gc2:20.00", "0.00,gc1:30.00"]
"""

import heapq
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List


def _to_cents(text: str) -> int:
    """'12.5' -> 1250, '30' -> 3000, '25.50' -> 2550 (exact decimal arithmetic)."""
    try:
        return int((Decimal(text.strip()) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0


def _fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def _sort_key(text: str):
    """valid_before as a number when possible so cards order by expiry, then id."""
    try:
        return (0, Decimal(text.strip()))
    except (InvalidOperation, ValueError):
        return (1, Decimal(0))


class Solution:
    def processEvents(self, events: List[str]) -> List[str]:
        # customer_id -> min-heap of [sort_key, card_id, balance_cents]; a card is removed
        # as soon as its balance reaches zero, so only active cards are kept.
        cards = {}
        out = []

        for raw in events:
            line = raw.strip() if raw else ""
            parts = [p.strip() for p in line.split(",")] if line else []
            kind = parts[1].upper() if len(parts) > 1 else ""

            if kind == "ADD_GIFTCARD" and len(parts) >= 5:
                customer, card_id = parts[2], parts[3]
                amount = _to_cents(parts[4])
                valid_before = parts[5] if len(parts) > 5 else ""
                if amount > 0:
                    heapq.heappush(cards.setdefault(customer, []),
                                   [_sort_key(valid_before), card_id, amount])
                out.append("")

            elif kind == "CHARGE" and len(parts) >= 5:
                customer = parts[3]
                remaining = _to_cents(parts[4])
                used = []
                heap = cards.get(customer)
                while remaining > 0 and heap:
                    top = heap[0]
                    take = min(top[2], remaining)
                    top[2] -= take
                    remaining -= take
                    if take > 0:
                        used.append(f"{top[1]}:{_fmt(take)}")
                    if top[2] == 0:
                        heapq.heappop(heap)   # drained: no longer active
                out.append(",".join([_fmt(remaining)] + used))

            else:
                out.append("")              # REFUND (later parts), blanks, unknown types

        return out


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().processEvents

    # Example 1
    assert f(["1,ADD_GIFTCARD,cust1,gc1,50,10", "2,ADD_GIFTCARD,cust2,gc2,20,15",
              "3,CHARGE,chg1,cust2,30,10000", "4,CHARGE,chg2,cust1,30,10000"]) == \
        ["", "", "10.00,gc2:20.00", "0.00,gc1:30.00"]
    # Example 2 (no gift card: whole amount on the credit card)
    assert f(["1,CHARGE,ch1,cust1,12.50,94105"]) == ["12.50"]
    # Example 3 (partial use, then drain + remainder)
    assert f(["1,ADD_GIFTCARD,cust1,gc1,25.50,50", "2,CHARGE,ch1,cust1,10.25,10000",
              "3,CHARGE,ch2,cust1,20.00,10000"]) == ["", "0.00,gc1:10.25", "4.75,gc1:15.25"]

    # A drained card is not listed on later charges; a new card for the same customer works.
    assert f(["1,ADD_GIFTCARD,c,gc1,10,99", "2,CHARGE,x1,c,10,10000", "3,CHARGE,x2,c,5,10000",
              "4,ADD_GIFTCARD,c,gc2,3,99", "5,CHARGE,x3,c,5,10000"]) == \
        ["", "0.00,gc1:10.00", "5.00", "", "2.00,gc2:3.00"]
    # Exact-balance charge, zero charge, and one-decimal / integer amounts.
    assert f(["1,ADD_GIFTCARD,c,gc,7.5,9", "2,CHARGE,a,c,7.50,10000", "3,CHARGE,b,c,0,10000",
              "4,CHARGE,d,c,3,10000"]) == ["", "0.00,gc:7.50", "0.00", "3.00"]
    # Gift cards are per customer.
    assert f(["1,ADD_GIFTCARD,alice,g1,100,9", "2,CHARGE,c1,bob,40,10000",
              "3,CHARGE,c2,alice,40,10000"]) == ["", "40.00", "0.00,g1:40.00"]
    # A zero-amount card is never debited or listed.
    assert f(["1,ADD_GIFTCARD,c,g0,0,9", "2,CHARGE,x,c,1,10000"]) == ["", "1.00"]
    # Output length always equals input length; unknown/later-part events give "".
    assert f(["1,ADD_GIFTCARD,c,g,5,9", "2,CHARGE,x,c,2,10000", "3,REFUND,x,2"]) == \
        ["", "0.00,g:2.00", ""]
    # Several active cards (beyond Part 1): drained by valid_before, then card id.
    assert f(["1,ADD_GIFTCARD,c,late,10,50", "2,ADD_GIFTCARD,c,early,10,20",
              "3,ADD_GIFTCARD,c,also20,10,20", "4,CHARGE,x,c,25,10000"]) == \
        ["", "", "", "0.00,also20:10.00,early:10.00,late:5.00"]
    # Large balances (64-bit cents) are exact.
    assert f(["1,ADD_GIFTCARD,c,g,90000000000.75,9", "2,CHARGE,x,c,90000000000.80,10000"]) == \
        ["", "0.05,g:90000000000.75"]
    # Empty input.
    assert f([]) == []

    # ---- Randomized cross-check against a Decimal single-balance reference ----
    import random

    def ref_events(evs):
        bal, out = {}, []
        for e in evs:
            p = e.split(",")
            if p[1] == "ADD_GIFTCARD":
                bal[p[2]] = [p[3], Decimal(p[4])]
                out.append("")
            else:
                amt, b = Decimal(p[4]), bal.get(p[3])
                if b and b[1] > 0 and amt > 0:      # a zero charge debits nothing
                    used = min(b[1], amt)
                    b[1] -= used
                    out.append(f"{amt - used:.2f},{b[0]}:{used:.2f}")
                else:
                    out.append(f"{amt:.2f}")
        return out

    rng = random.Random(7)
    for _ in range(500):
        evs, balances, ts, card_no = [], {}, 0, 0
        for _ in range(rng.randint(1, 40)):
            ts += rng.randint(0, 3)
            cust = rng.choice(["c1", "c2", "c3"])
            amt = rng.choice([rng.randint(0, 50), rng.randint(0, 5000) / 100, rng.randint(0, 500) / 10])
            # Part 1 guarantee: a customer only gets a new card once the old one is drained.
            if rng.random() < 0.4 and balances.get(cust, Decimal(0)) == 0:
                card_no += 1
                evs.append(f"{ts},ADD_GIFTCARD,{cust},gc{card_no},{amt},{ts + rng.randint(1, 9)}")
                balances[cust] = Decimal(str(amt))
            else:
                evs.append(f"{ts},CHARGE,ch{len(evs)},{cust},{amt},{rng.randint(10000, 99999)}")
                balances[cust] = max(Decimal(0), balances.get(cust, Decimal(0)) - Decimal(str(amt)))
        assert f(evs) == ref_events(evs), evs

    # ---- Large input smoke test ----
    import time
    big = []
    for i in range(100_000):
        c = f"cust{i % 5000}"
        if i % 3 == 0:
            big.append(f"{i},ADD_GIFTCARD,{c},card{i},{(i % 977) / 100},{i + 100}")
        else:
            big.append(f"{i},CHARGE,ch{i},{c},{(i % 1313) / 100},94105")
    t0 = time.perf_counter()
    res = f(big)
    elapsed = time.perf_counter() - t0
    assert len(res) == len(big) and elapsed < 10, elapsed
    print(f"All tests passed (including randomized cross-checks); large case {elapsed:.2f}s.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        data = [l.rstrip("\n") for l in sys.stdin if l.strip()]
        if not data:
            _run_tests()
        else:
            print("\n".join(Solution().processEvents(data)))
