"""
Stripe OA: Subscription and Usage-Based Billing Calculator
https://www.fastprep.io/problems/stripe-subscription-and-usage-billing-calculator

calculateMonthlyCharges(subscriptions, changes, pricing, usage) -> String[][]

Billing cycle = days 1..30, money in USD cents.

subscriptions : "user_id,subscription_id,monthly_cost"           active from day 1
changes       : "user_id,old_subscription_id,new_subscription_id,new_monthly_cost,change_day"
                On change_day the old subscription ends (last active day = change_day - 1)
                and the new one starts (active from change_day through day 30 unless it is
                itself replaced later).  old_subscription_id == "-" adds a subscription
                without replacing one.  Changes may be out of order; IDs are globally unique.
pricing       : "product_id,upper_bound,unit_price"   marginal tiers, may be unordered;
                upper_bound -1 = unlimited (exactly one per product).  Units 1..b1 cost
                p1 each, units b1+1..b2 cost p2 each, ... remaining units cost the
                unlimited tier's price.
usage         : "user_id,product_id,quantity"   summed per (user, product) before tiering.

A version active from day a through day b contributes monthly_cost * (b - a + 1) / 30.
Each user's combined total (subscriptions + usage) is floored ONCE at the end.
Output rows [user_id, total_as_string] sorted lexicographically by user_id; users with a
zero total are included; empty array when there are no users.

    ["u1,s1,1000","u1,s2,2000"], ["u1,s1,s1_plus,2000,15"],
    ["api,3,100","api,-1,50"],   ["u1,api,2","u1,api,5"]      -> [["u1","4033"]]
"""

from typing import List


class Solution:
    def calculateMonthlyCharges(self,
                                subscriptions: List[str],
                                changes: List[str],
                                pricing: List[str],
                                usage: List[str]) -> List[List[str]]:
        CYCLE_DAYS = 30
        LAST_DAY = 30

        # Everything is accumulated as integer cents scaled by 30 so that the single
        # final floor is exact:  total_cents = scaled // 30.
        scaled = {}  # user_id -> total * 30

        # ------------------------------------------------------------------
        # 1. Build every subscription version: id -> [user, cost, start, end]
        # ------------------------------------------------------------------
        versions = {}
        for raw in subscriptions or []:
            if not raw or not raw.strip():
                continue
            user, sub_id, cost = (p.strip() for p in raw.split(",")[:3])
            versions[sub_id] = [user, int(cost), 1, LAST_DAY]
            scaled.setdefault(user, 0)

        parsed_changes = []
        for raw in changes or []:
            if not raw or not raw.strip():
                continue
            user, old_id, new_id, cost, day = (p.strip() for p in raw.split(",")[:5])
            parsed_changes.append((user, old_id, new_id, int(cost), int(day)))
            scaled.setdefault(user, 0)

        # New IDs are globally unique, so creating all new versions first and then
        # closing the old ones is independent of the order changes were given in.
        for user, old_id, new_id, cost, day in parsed_changes:
            versions[new_id] = [user, cost, day, LAST_DAY]
        for user, old_id, new_id, cost, day in parsed_changes:
            if old_id != "-" and old_id in versions:
                versions[old_id][3] = min(versions[old_id][3], day - 1)

        # ------------------------------------------------------------------
        # 2. Prorated subscription contributions (scaled by 30).
        # ------------------------------------------------------------------
        for user, cost, start, end in versions.values():
            days_active = end - start + 1
            if days_active > 0:
                scaled[user] = scaled.get(user, 0) + cost * days_active

        # ------------------------------------------------------------------
        # 3. Pricing tiers per product: sorted finite bounds, then unlimited.
        # ------------------------------------------------------------------
        tiers = {}  # product_id -> [(upper_bound or None, unit_price), ...]
        for raw in pricing or []:
            if not raw or not raw.strip():
                continue
            product, bound, price = (p.strip() for p in raw.split(",")[:3])
            tiers.setdefault(product, []).append((int(bound), int(price)))
        for product in tiers:
            finite = sorted(t for t in tiers[product] if t[0] >= 0)
            unlimited = [t for t in tiers[product] if t[0] < 0]
            tiers[product] = finite + [(None, unlimited[0][1])] if unlimited else finite

        # ------------------------------------------------------------------
        # 4. Usage: aggregate per (user, product), then charge marginally.
        # ------------------------------------------------------------------
        quantities = {}
        for raw in usage or []:
            if not raw or not raw.strip():
                continue
            user, product, qty = (p.strip() for p in raw.split(",")[:3])
            quantities[(user, product)] = quantities.get((user, product), 0) + int(qty)
            scaled.setdefault(user, 0)

        for (user, product), qty in quantities.items():
            remaining, prev_bound, charge = qty, 0, 0
            for bound, price in tiers.get(product, []):
                if remaining <= 0:
                    break
                units = remaining if bound is None else min(remaining, bound - prev_bound)
                if units > 0:
                    charge += units * price
                    remaining -= units
                if bound is not None:
                    prev_bound = max(prev_bound, bound)
            scaled[user] += charge * CYCLE_DAYS

        # ------------------------------------------------------------------
        # 5. Floor once per user, sort by user id.
        # ------------------------------------------------------------------
        return [[user, str(scaled[user] // CYCLE_DAYS)] for user in sorted(scaled)]


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().calculateMonthlyCharges

    # Example 1 (Part 1)
    assert f(["user_1,sub_a,1000", "user_1,sub_b,2500", "user_2,sub_c,500",
              "user_2,sub_d,3000", "user_2,sub_e,1500", "user_3,sub_f,2000"], [], [], []) == \
        [["user_1", "3500"], ["user_2", "5000"], ["user_3", "2000"]]
    # Example 2 (change + tiered usage)
    assert f(["u1,s1,1000", "u1,s2,2000"], ["u1,s1,s1_plus,2000,15"],
             ["api,3,100", "api,-1,50"], ["u1,api,2", "u1,api,5"]) == [["u1", "4033"]]
    # Example 3 (floor once, not per subscription)
    assert f(["u,s1,1000", "u,s2,2000"],
             ["u,s2,s2_plus,3000,29", "u,s1,s1_plus,2000,29"], [], []) == [["u", "3133"]]
    # Example 4 (chained changes)
    assert f(["user_1,sub_a,1000", "user_1,sub_b,2500", "user_2,sub_c,500", "user_3,sub_d,2000"],
             ["user_1,sub_a,sub_a_plus,1500,11", "user_1,sub_a_plus,sub_a_pro,3000,21",
              "user_2,sub_c,sub_c_premium,1200,16"], [], []) == \
        [["user_1", "4333"], ["user_2", "850"], ["user_3", "2000"]]

    # Chained changes given out of order give the same answer.
    assert f(["user_1,sub_a,1000"],
             ["user_1,sub_a_plus,sub_a_pro,3000,21", "user_1,sub_a,sub_a_plus,1500,11"], [], []) == \
        [["user_1", str((10 * 1000 + 10 * 1500 + 10 * 3000) // 30)]]
    # "-" adds a subscription without replacing one: 3000 full + 3000 for days 16..30.
    assert f(["u,s,3000"], ["u,-,s2,3000,16"], [], []) == [["u", "4500"]]
    # Change on day 1 replaces the initial price entirely (old gets 0 days).
    assert f(["u,s,1000"], ["u,s,s2,2000,1"], [], []) == [["u", "2000"]]
    # Change on day 30: old 29 days, new 1 day.
    assert f(["u,s,3000"], ["u,s,s2,6000,30"], [], []) == [["u", str((29 * 3000 + 6000) // 30)]]
    # Usage without any subscription; unordered tiers; flat (unlimited-only) product.
    assert f([], [], ["api,-1,50", "api,3,100", "storage,-1,2"],
             ["v,api,2", "v,api,5", "v,storage,10"]) == [["v", "520"]]
    # Tier allowances are per user, not shared.
    assert f([], [], ["api,3,100", "api,-1,50"], ["a,api,3", "b,api,3"]) == \
        [["a", "300"], ["b", "300"]]
    # Usage within the first tier only; three tiers.
    assert f([], [], ["s,100,10", "s,1000,5", "s,-1,1"], ["u,s,50"]) == [["u", "500"]]
    assert f([], [], ["s,100,10", "s,1000,5", "s,-1,1"], ["u,s,1500"]) == [["u", "6000"]]
    # Zero-total users are included; output sorted lexicographically.
    assert f(["b,s,0"], ["a,-,s2,0,5"], [], ["c,api,0"]) == [["a", "0"], ["b", "0"], ["c", "0"]]
    # No users at all -> empty array.
    assert f([], [], [], []) == []
    # Flooring example from the general constraints: 1066.666 + 2066.666 -> 3133.
    assert f(["u,a,1000", "u,b,2000"], ["u,a,a2,1100,3", "u,b,b2,2100,3"], [], []) == \
        [["u", str((2 * 1000 + 28 * 1100 + 2 * 2000 + 28 * 2100) // 30)]]


    # ---- Randomized cross-check against a day-by-day / unit-by-unit reference ----
    import random
    from fractions import Fraction

    def ref_billing(subs, chg, pricing, usage):
        users = set()
        versions = {}  # id -> [user, cost, start, end]
        for r in subs:
            u, sid, c = r.split(","); versions[sid] = [u, int(c), 1, 30]; users.add(u)
        parsed = [r.split(",") for r in chg]
        for u, old, new, c, d in parsed:
            versions[new] = [u, int(c), int(d), 30]; users.add(u)
        for u, old, new, c, d in parsed:
            if old != "-":
                versions[old][3] = int(d) - 1
        total = {u: Fraction(0) for u in users}
        for u, c, s, e in versions.values():
            for day in range(1, 31):
                if s <= day <= e:
                    total[u] += Fraction(c, 30)
        tiers = {}
        for r in pricing:
            p, b, pr = r.split(","); tiers.setdefault(p, []).append((int(b), int(pr)))
        qty = {}
        for r in usage:
            u, p, q = r.split(","); qty[(u, p)] = qty.get((u, p), 0) + int(q); users.add(u); total.setdefault(u, Fraction(0))
        for (u, p), q in qty.items():
            finite = sorted(t for t in tiers[p] if t[0] >= 0)
            unl = [t for t in tiers[p] if t[0] < 0][0][1]
            for unit in range(1, q + 1):  # unit-by-unit
                price = unl
                for b, pr in finite:
                    if unit <= b:
                        price = pr; break
                total[u] += price
        return [[u, str(int(total[u]))] for u in sorted(users)]  # int() floors non-negative Fractions

    rng = random.Random(11)
    for _ in range(300):
        users = ["u1", "u2", "u3"]
        subs, chg, next_id = [], [], 0
        active = {}  # sid -> (user, last_change_day)
        for u in users:
            for _ in range(rng.randint(0, 2)):
                sid = f"s{next_id}"; next_id += 1
                subs.append(f"{u},{sid},{rng.randint(0, 5000)}"); active[sid] = (u, 0)
        for _ in range(rng.randint(0, 5)):
            new = f"s{next_id}"; next_id += 1
            day = rng.randint(1, 30)
            if active and rng.random() < 0.7:
                old = rng.choice(list(active))
                u, last = active.pop(old)
                if day <= last:
                    day = min(30, last + 1)
                chg.append(f"{u},{old},{new},{rng.randint(0, 5000)},{day}")
            else:
                u = rng.choice(users); chg.append(f"{u},-,{new},{rng.randint(0, 5000)},{day}")
            active[new] = (u, day)
        rng.shuffle(chg)
        pricing = ["api,-1,%d" % rng.randint(0, 9), "api,3,%d" % rng.randint(0, 9), "api,10,%d" % rng.randint(0, 9),
                   "gb,-1,%d" % rng.randint(0, 9)]
        rng.shuffle(pricing)
        usage = [f"{rng.choice(users + ['u9'])},{rng.choice(['api', 'gb'])},{rng.randint(0, 25)}" for _ in range(rng.randint(0, 5))]
        assert f(subs, chg, pricing, usage) == ref_billing(subs, chg, pricing, usage), (subs, chg, pricing, usage)
    print("All tests passed (including randomized cross-checks).")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        # stdin: four sections separated by blank lines:
        # subscriptions / changes / pricing / usage
        sections, cur = [], []
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line.strip():
                cur.append(line)
            else:
                sections.append(cur)
                cur = []
        sections.append(cur)
        while len(sections) < 4:
            sections.append([])
        if not any(sections):
            _run_tests()
        else:
            print(Solution().calculateMonthlyCharges(*sections[:4]))
