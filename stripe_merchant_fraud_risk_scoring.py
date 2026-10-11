"""
Stripe OA: Merchant Fraud Risk Scoring
https://www.fastprep.io/problems/stripe-merchant-fraud-risk-scoring

calculateMerchantFraudScores(transactions, merchantIds, baseScores, rules) -> long[]

transactions[i] = [customer_id, merchant_id, hour, amount]      (hour, amount: strings)
rules[i]        = [min_transaction_amount, multiplicative_factor, additive_factor, penalty]
                  and belongs to transactions[i].
merchantIds[j] starts at baseScores[j].

Three passes, each scanning the whole transaction list from left to right:
1. Amount pass       amount > min_transaction_amount  ->  score *= multiplicative_factor
2. Repeat-customer   group by (customer, merchant).  On a group's third transaction add
                     the additive factors of its first three transactions; every later
                     transaction of the group adds only its own additive factor.
3. Same-hour         group by (customer, merchant, hour) with the same third-transaction
                     rule on the penalties, applied with a sign chosen by the hour:
                         12..17 -> add      9..11 or 18..21 -> subtract      else -> nothing
Return the final scores in merchantIds order.

    [["c1","m1","13","120"], ["c1","m1","13","80"], ["c1","m1","13","90"], ["c2","m2","9","50"]],
    ["m1","m2"], [10, 5], [[100,2,3,4], [100,3,5,6], [100,2,7,8], [40,2,1,9]]  ->  [53, 10]
"""

from typing import List


def _hour_sign(hour: int) -> int:
    if 12 <= hour <= 17:
        return 1
    if 9 <= hour <= 11 or 18 <= hour <= 21:
        return -1
    return 0


class Solution:
    def calculateMerchantFraudScores(self, transactions: List[List[str]], merchantIds: List[str],
                                     baseScores: List[int], rules: List[List[int]]) -> List[int]:
        score = {}
        for merchant, base in zip(merchantIds, baseScores):
            score.setdefault(merchant, int(base))

        rows = []   # (customer, merchant, hour, amount, min_amount, factor, additive, penalty)
        for i, tx in enumerate(transactions or []):
            if not tx or len(tx) < 4:
                continue
            rule = list(rules[i]) if i < len(rules) and rules[i] else []
            rule += [0] * (4 - len(rule))
            rows.append((str(tx[0]), str(tx[1]), int(str(tx[2])), int(str(tx[3])),
                         int(rule[0]), int(rule[1]), int(rule[2]), int(rule[3])))

        # ---- pass 1: amount thresholds ------------------------------------------
        for customer, merchant, hour, amount, min_amount, factor, additive, penalty in rows:
            if amount > min_amount and merchant in score:
                score[merchant] *= factor

        # ---- pass 2: repeat customers ---------------------------------------------
        self._third_transaction_pass(rows, score, key_fields=2, value_index=6, signed=False)

        # ---- pass 3: same-hour bursts ---------------------------------------------
        self._third_transaction_pass(rows, score, key_fields=3, value_index=7, signed=True)

        return [score[m] for m in merchantIds]

    @staticmethod
    def _third_transaction_pass(rows, score, key_fields, value_index, signed):
        """Add a group's first three values on its third row, then each later value."""
        count, held = {}, {}
        for row in rows:
            key = row[:key_fields]
            value = row[value_index]
            if signed:
                value *= _hour_sign(row[2])
            n = count.get(key, 0) + 1
            count[key] = n
            if n < 3:
                held.setdefault(key, []).append(value)
                continue
            if n == 3:
                value += sum(held.pop(key, ()))
            merchant = row[1]
            if merchant in score:
                score[merchant] += value


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().calculateMerchantFraudScores

    # Example 1
    assert f([["c1", "m1", "13", "120"], ["c1", "m1", "13", "80"], ["c1", "m1", "13", "90"],
              ["c2", "m2", "9", "50"]], ["m1", "m2"], [10, 5],
             [[100, 2, 3, 4], [100, 3, 5, 6], [100, 2, 7, 8], [40, 2, 1, 9]]) == [53, 10]
    # Example 2 (subtractive hour)
    assert f([["c", "m", "10", "50"]] * 3, ["m"], [4],
             [[100, 2, 1, 10], [100, 2, 2, 20], [100, 2, 3, 30]]) == [-50]
    # Example 3 (fourth transaction adds only its own values)
    assert f([["c", "m", "12", "101"]] * 4, ["m"], [2],
             [[100, 2, 1, 1], [100, 3, 1, 2], [100, 2, 1, 3], [100, 2, 5, 4]]) == [66]

    # Amount must be strictly greater than the threshold.
    assert f([["c", "m", "0", "100"]], ["m"], [7], [[100, 5, 1, 1]]) == [7]
    assert f([["c", "m", "0", "101"]], ["m"], [7], [[100, 5, 1, 1]]) == [35]
    # Two transactions of a pair contribute nothing; the third releases all three.
    assert f([["c", "m", "1", "1"]] * 2, ["m"], [0], [[9, 1, 5, 5]] * 2) == [0]
    assert f([["c", "m", "1", "1"]] * 3, ["m"], [0], [[9, 1, 5, 5]] * 3) == [15]
    # Neutral hours (0-8, 22-23) apply no penalty; boundaries 9/11/12/17/18/21 are inclusive.
    for hour, expect in [(8, 0), (9, -3), (11, -3), (12, 3), (17, 3), (18, -3), (21, -3), (22, 0)]:
        assert f([["c", "m", str(hour), "0"]] * 3, ["m"], [0], [[1, 1, 0, 1]] * 3) == [expect], hour
    # Repeat-customer groups ignore the hour; same-hour groups split by hour.
    assert f([["c", "m", "12", "0"], ["c", "m", "13", "0"], ["c", "m", "14", "0"]], ["m"], [0],
             [[1, 1, 2, 100]] * 3) == [6]
    # Multiplication happens before any additions (pass order).
    assert f([["c", "m", "12", "5"]] * 3, ["m"], [1], [[1, 10, 1, 0]] * 3) == [1003]
    # Output follows merchantIds order; merchants without transactions keep their base.
    assert f([["c", "b", "0", "0"]], ["a", "b", "c"], [1, 2, 3], [[0, 1, 0, 0]]) == [1, 2, 3]
    assert f([["c", "b", "0", "1"]], ["a", "b", "c"], [1, 2, 3], [[0, 4, 0, 0]]) == [1, 8, 3]
    # Empty input.
    assert f([], ["m"], [5], []) == [5]

    # ---- Randomized cross-check against a closed-form reference ----
    # A group of n >= 3 rows contributes the sum of all its values; fewer rows contribute 0.
    import random

    def ref(transactions, merchant_ids, base_scores, rules):
        score = dict(zip(merchant_ids, base_scores))
        for (c, m, h, a), (mn, mul, add, pen) in zip(transactions, rules):
            if int(a) > mn:
                score[m] *= mul
        groups = {}
        for (c, m, h, a), (mn, mul, add, pen) in zip(transactions, rules):
            groups.setdefault(("pair", c, m), []).append((m, add))
            groups.setdefault(("hour", c, m, h), []).append((m, pen * _hour_sign(int(h))))
        for key, items in groups.items():
            if len(items) >= 3:
                score[items[0][0]] += sum(v for _, v in items)
        return [score[m] for m in merchant_ids]

    rng = random.Random(13)
    for _ in range(600):
        merchants = ["m1", "m2", "m3"]
        tx, rules = [], []
        for _ in range(rng.randint(0, 14)):
            tx.append([rng.choice(["c1", "c2"]), rng.choice(merchants), str(rng.choice([8, 9, 11, 12, 17, 18, 21, 22])),
                       str(rng.randint(0, 120))])
            rules.append([rng.randint(0, 120), rng.randint(1, 3), rng.randint(0, 9), rng.randint(0, 9)])
        bases = [rng.randint(0, 20) for _ in merchants]
        assert f(tx, merchants, bases, rules) == ref(tx, merchants, bases, rules), (tx, bases, rules)
    print("All tests passed (including randomized cross-checks).")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        _run_tests()
