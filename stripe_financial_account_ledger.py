"""
Stripe: Financial Account Ledger
https://www.fastprep.io/problems/stripe-financial-account-ledger

Commands (chronological):
    INIT account_id starting_balance
    FUND timestamp account_id method amount      method in {WIRE, ACH, STABLECOIN}
    BALANCE timestamp account_id

timestamp = "8" (day only, hour 0) or "8,16" (day,hour).  Day 1 is Monday;
days 6 and 7 of every seven-day cycle are Saturday / Sunday.

Settlement
    WIRE        cutoff 17, settles on its effective submission day
    ACH         cutoff 20, settles one business day after its effective day
    STABLECOIN  no cutoff, settles on the request day (weekends included)

Effective submission day (WIRE / ACH):
    business day before cutoff      -> that day
    business day at/after cutoff    -> next business day
    weekend (any hour)              -> following Monday

ACH limits per account, bucketed by effective submission day:
    5,000,000 per effective business day, 10,000,000 per 7-day week
    (days 1-7 = week 1, 8-14 = week 2, ...).  A request that would exceed
    either limit is rejected entirely and consumes nothing.

BALANCE appends starting balance + every earlier accepted fund whose
settlement day <= query day, or FAILURE for an unknown account.  Results are
joined with commas; empty string if there is no BALANCE command.
"""

from typing import List


class Solution:
    def processLedger(self, commands: List[str]) -> str:
        WIRE_CUTOFF = 17
        ACH_CUTOFF = 20
        ACH_DAILY_LIMIT = 5_000_000
        ACH_WEEKLY_LIMIT = 10_000_000

        starting = {}      # account_id -> starting balance (first INIT wins)
        funds = {}         # account_id -> list of (settle_day, amount) for accepted funds
        ach_daily = {}     # (account_id, effective_day)  -> accepted ACH principal
        ach_weekly = {}    # (account_id, week_index)     -> accepted ACH principal
        results = []

        for raw in commands:
            tokens = raw.split()
            if not tokens:
                continue
            cmd = tokens[0].upper()

            # ---------------------------------------------------------- INIT
            if cmd == "INIT":
                acct = tokens[1]
                if acct in starting:
                    continue  # only the first INIT has an effect
                # Tolerate an optional currency token: take the first integer field.
                bal = 0
                for t in tokens[2:]:
                    try:
                        bal = int(t)
                        break
                    except ValueError:
                        continue
                starting[acct] = bal
                funds[acct] = []
                continue

            # -------------------------------------------------- timestamp
            ts = tokens[1]
            if "," in ts:
                day_str, hour_str = ts.split(",", 1)
                day, hour = int(day_str), int(hour_str)
            else:
                day, hour = int(ts), 0

            # ---------------------------------------------------------- FUND
            if cmd == "FUND":
                acct, method, amount = tokens[2], tokens[3].upper(), int(tokens[4])
                if acct not in starting or amount <= 0:
                    continue  # unknown account / non-positive amount: ignore

                if method == "STABLECOIN":
                    funds[acct].append((day, amount))
                    continue

                # Effective submission day for WIRE / ACH.
                cutoff = WIRE_CUTOFF if method == "WIRE" else ACH_CUTOFF
                dow = (day - 1) % 7 + 1               # 1 = Mon ... 7 = Sun
                if dow >= 6:
                    eff = day + (8 - dow)             # Sat -> +2, Sun -> +1 => Monday
                elif hour >= cutoff:
                    eff = day + 1
                    while (eff - 1) % 7 + 1 >= 6:
                        eff += 1
                else:
                    eff = day

                if method == "WIRE":
                    funds[acct].append((eff, amount))
                    continue

                # ACH: enforce daily + weekly limits on the effective day.
                week = (eff - 1) // 7
                d_key, w_key = (acct, eff), (acct, week)
                d_used = ach_daily.get(d_key, 0)
                w_used = ach_weekly.get(w_key, 0)
                if d_used + amount > ACH_DAILY_LIMIT or w_used + amount > ACH_WEEKLY_LIMIT:
                    continue  # rejected; consumes no limit, never settles
                ach_daily[d_key] = d_used + amount
                ach_weekly[w_key] = w_used + amount

                settle = eff + 1                      # one business day after eff
                while (settle - 1) % 7 + 1 >= 6:
                    settle += 1
                funds[acct].append((settle, amount))
                continue

            # ------------------------------------------------------- BALANCE
            if cmd == "BALANCE":
                acct = tokens[2]
                if acct not in starting:
                    results.append("FAILURE")
                    continue
                total = starting[acct]
                for settle_day, amount in funds[acct]:
                    if settle_day <= day:
                        total += amount
                results.append(str(total))

        return ",".join(results)


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().processLedger

    # Example 1
    assert f(["INIT acct_1 10000", "FUND 1 acct_1 WIRE 5000", "FUND 1 acct_1 ACH 3000",
              "BALANCE 1 acct_1", "BALANCE 2 acct_1"]) == "15000,18000"
    # Example 2
    assert f(["INIT acct_1 0", "FUND 5 acct_1 WIRE 5000", "BALANCE 5 acct_1",
              "FUND 6 acct_1 STABLECOIN 1000", "BALANCE 6 acct_1", "FUND 6 acct_1 ACH 2000",
              "BALANCE 8 acct_1", "BALANCE 9 acct_1"]) == "5000,6000,6000,8000"
    # Example 3
    assert f(["INIT acct_1 0", "FUND 1,16 acct_1 WIRE 5000", "FUND 1,17 acct_1 WIRE 3000",
              "BALANCE 1,18 acct_1", "BALANCE 2,0 acct_1"]) == "5000,8000"
    # Example 4
    assert f(["INIT acct_1 0", "FUND 1,10 acct_1 ACH 5000000", "FUND 1,11 acct_1 ACH 1000",
              "FUND 2,11 acct_1 ACH 4000000", "BALANCE 2,12 acct_1", "BALANCE 3,0 acct_1",
              "FUND 3,10 acct_1 ACH 2000000", "BALANCE 4,0 acct_1"]) == "5000000,9000000,9000000"

    # Unknown account -> FAILURE; funding unknown account ignored.
    assert f(["INIT a 5", "FUND 1 b WIRE 100", "BALANCE 1 b", "BALANCE 1 a"]) == "FAILURE,5"
    # Duplicate INIT ignored.
    assert f(["INIT a 5", "INIT a 99", "BALANCE 1 a"]) == "5"
    # No BALANCE -> empty string.
    assert f(["INIT a 5", "FUND 1 a WIRE 1"]) == ""
    # Friday wire at/after cutoff -> Monday (day 8).
    assert f(["INIT a 0", "FUND 5,17 a WIRE 10", "BALANCE 7 a", "BALANCE 8 a"]) == "0,10"
    # Friday ACH before cutoff: eff Fri (5), settles Mon (8).
    assert f(["INIT a 0", "FUND 5,10 a ACH 10", "BALANCE 7 a", "BALANCE 8 a"]) == "0,10"
    # Friday ACH after cutoff: eff Mon (8), settles Tue (9).
    assert f(["INIT a 0", "FUND 5,21 a ACH 10", "BALANCE 8 a", "BALANCE 9 a"]) == "0,10"
    # Sunday wire -> Monday.
    assert f(["INIT a 0", "FUND 7,3 a WIRE 10", "BALANCE 7,23 a", "BALANCE 8,0 a"]) == "0,10"
    # Rejected ACH consumes no limit: a later fitting request is still accepted.
    assert f(["INIT a 0", "FUND 1,1 a ACH 4000000", "FUND 1,2 a ACH 2000000",
              "FUND 1,3 a ACH 1000000", "BALANCE 2 a"]) == "5000000"
    # Weekly limit is per week bucket: day 8 starts a fresh week.
    assert f(["INIT a 0", "FUND 1 a ACH 5000000", "FUND 2 a ACH 5000000", "FUND 3 a ACH 1",
              "FUND 8 a ACH 5000000", "BALANCE 9 a"]) == "15000000"
    # Limits are per account.
    assert f(["INIT a 0", "INIT b 0", "FUND 1 a ACH 5000000", "FUND 1 b ACH 5000000",
              "BALANCE 2 a", "BALANCE 2 b"]) == "5000000,5000000"
    # Settlement is by day: a fund settling today counts even for an earlier-hour query later in stream.
    assert f(["INIT a 0", "FUND 1,5 a WIRE 10", "BALANCE 1,6 a"]) == "10"
    # Optional currency token in INIT is tolerated.
    assert f(["INIT a USD 7", "BALANCE 1 a"]) == "7"

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
            print(Solution().processLedger(data))
