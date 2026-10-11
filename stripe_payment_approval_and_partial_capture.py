"""
Stripe OA: Payment Approval and Partial Capture
https://www.fastprep.io/problems/stripe-payment-approval-and-partial-capture

processPayments(commands) -> String[]

Every command has five string fields:
    ["CREATE",  id, payer, payee, amount]
    ["APPROVE", id, "",    "",    amount]
    ["CAPTURE", id, "",    "",    amount]
    ["CANCEL",  id, "",    "",    ""]
One response per command: the payment's resulting state, or "ERROR" for an invalid
command.  Invalid commands change nothing.

    CREATE   id never used before (a cancelled id stays used), non-empty payer and
             payee, positive integer amount                     -> CREATED
    APPROVE  only in CREATED; positive amount <= created amount -> APPROVED
    CAPTURE  only in APPROVED / PARTIALLY_CAPTURED; positive amount; the captured
             total may not exceed the approved amount           -> SUCCEEDED when the
             total equals the approved amount, else PARTIALLY_CAPTURED
    CANCEL   only in CREATED                                    -> CANCELLED
Unknown ids, repeated approval, over-capture and anything after SUCCEEDED or
CANCELLED are errors.

    [["CREATE","p1","alice","bob","100"], ["APPROVE","p1","","","80"],
     ["CAPTURE","p1","","","30"], ["CAPTURE","p1","","","50"], ["CANCEL","p1","","",""]]
        -> ["CREATED", "APPROVED", "PARTIALLY_CAPTURED", "SUCCEEDED", "ERROR"]
"""

from typing import List, Optional


def _positive_int(text: str) -> Optional[int]:
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class Solution:
    def processPayments(self, commands: List[List[str]]) -> List[str]:
        payments = {}   # id -> {"state", "created", "approved", "captured"}
        out = []

        for command in commands or []:
            fields = ["" if f is None else str(f) for f in (command or [])]
            fields += [""] * (5 - len(fields))
            action, pid = fields[0].strip().upper(), fields[1]
            payment = payments.get(pid)

            if action == "CREATE":
                amount = _positive_int(fields[4])
                if not pid or pid in payments or not fields[2] or not fields[3] or amount is None:
                    out.append("ERROR")
                    continue
                payments[pid] = {"state": "CREATED", "created": amount, "approved": 0, "captured": 0}
                out.append("CREATED")

            elif action == "APPROVE":
                amount = _positive_int(fields[4])
                if payment is None or payment["state"] != "CREATED" or amount is None \
                        or amount > payment["created"]:
                    out.append("ERROR")
                    continue
                payment["approved"] = amount
                payment["state"] = "APPROVED"
                out.append("APPROVED")

            elif action == "CAPTURE":
                amount = _positive_int(fields[4])
                if payment is None or payment["state"] not in ("APPROVED", "PARTIALLY_CAPTURED") \
                        or amount is None or payment["captured"] + amount > payment["approved"]:
                    out.append("ERROR")
                    continue
                payment["captured"] += amount
                payment["state"] = ("SUCCEEDED" if payment["captured"] == payment["approved"]
                                    else "PARTIALLY_CAPTURED")
                out.append(payment["state"])

            elif action == "CANCEL":
                if payment is None or payment["state"] != "CREATED":
                    out.append("ERROR")
                    continue
                payment["state"] = "CANCELLED"
                out.append("CANCELLED")

            else:
                out.append("ERROR")

        return out


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().processPayments

    # Example 1
    assert f([["CREATE", "p1", "alice", "bob", "100"], ["APPROVE", "p1", "", "", "80"],
              ["CAPTURE", "p1", "", "", "30"], ["CAPTURE", "p1", "", "", "50"],
              ["CANCEL", "p1", "", "", ""]]) == \
        ["CREATED", "APPROVED", "PARTIALLY_CAPTURED", "SUCCEEDED", "ERROR"]
    # Example 2 (invalid commands leave state unchanged; cancelled id stays used)
    assert f([["CREATE", "p1", "a", "b", "10"], ["CAPTURE", "p1", "", "", "3"],
              ["APPROVE", "p1", "", "", "11"], ["CANCEL", "p1", "", "", ""],
              ["CREATE", "p1", "a", "b", "5"]]) == ["CREATED", "ERROR", "ERROR", "CANCELLED", "ERROR"]
    # Example 3
    assert f([]) == []

    # CREATE validation: empty payer/payee, zero/negative/blank/non-numeric amounts.
    assert f([["CREATE", "p", "", "b", "5"], ["CREATE", "p", "a", "", "5"], ["CREATE", "p", "a", "b", "0"],
              ["CREATE", "p", "a", "b", "-4"], ["CREATE", "p", "a", "b", ""], ["CREATE", "p", "a", "b", "x"],
              ["CREATE", "p", "a", "b", "5"]]) == ["ERROR"] * 6 + ["CREATED"]
    # A failed CREATE does not consume the id (shown above); a successful one does.
    assert f([["CREATE", "p", "a", "b", "5"], ["CREATE", "p", "c", "d", "9"]]) == ["CREATED", "ERROR"]
    # APPROVE: equal to created amount is fine; zero, negative, over, and repeat are errors.
    assert f([["CREATE", "p", "a", "b", "10"], ["APPROVE", "p", "", "", "0"], ["APPROVE", "p", "", "", "-1"],
              ["APPROVE", "p", "", "", "10"], ["APPROVE", "p", "", "", "5"]]) == \
        ["CREATED", "ERROR", "ERROR", "APPROVED", "ERROR"]
    # CAPTURE: exact remainder succeeds, over-capture is rejected without changing the total,
    # and nothing is allowed after SUCCEEDED.
    assert f([["CREATE", "p", "a", "b", "10"], ["APPROVE", "p", "", "", "6"], ["CAPTURE", "p", "", "", "7"],
              ["CAPTURE", "p", "", "", "4"], ["CAPTURE", "p", "", "", "3"], ["CAPTURE", "p", "", "", "2"],
              ["CAPTURE", "p", "", "", "1"], ["CANCEL", "p", "", "", ""], ["APPROVE", "p", "", "", "1"]]) == \
        ["CREATED", "APPROVED", "ERROR", "PARTIALLY_CAPTURED", "ERROR", "SUCCEEDED", "ERROR", "ERROR", "ERROR"]
    # Zero or negative capture amounts are invalid.
    assert f([["CREATE", "p", "a", "b", "10"], ["APPROVE", "p", "", "", "6"], ["CAPTURE", "p", "", "", "0"],
              ["CAPTURE", "p", "", "", "-2"]]) == ["CREATED", "APPROVED", "ERROR", "ERROR"]
    # CANCEL only from CREATED; nothing works after CANCELLED; unknown ids are errors.
    assert f([["CANCEL", "zz", "", "", ""], ["APPROVE", "zz", "", "", "1"], ["CAPTURE", "zz", "", "", "1"],
              ["CREATE", "p", "a", "b", "3"], ["CANCEL", "p", "", "", ""], ["CANCEL", "p", "", "", ""],
              ["APPROVE", "p", "", "", "1"]]) == ["ERROR", "ERROR", "ERROR", "CREATED", "CANCELLED", "ERROR", "ERROR"]
    # Approved payments cannot be cancelled.
    assert f([["CREATE", "p", "a", "b", "3"], ["APPROVE", "p", "", "", "3"], ["CANCEL", "p", "", "", ""]]) == \
        ["CREATED", "APPROVED", "ERROR"]
    # Payments are independent.
    assert f([["CREATE", "p1", "a", "b", "3"], ["CREATE", "p2", "a", "b", "4"], ["APPROVE", "p2", "", "", "4"],
              ["CAPTURE", "p2", "", "", "4"], ["CANCEL", "p1", "", "", ""]]) == \
        ["CREATED", "CREATED", "APPROVED", "SUCCEEDED", "CANCELLED"]

    # ---- Randomized cross-check against a transition-table reference ----
    import random

    def ref(commands):
        allowed = {"APPROVE": {"CREATED"}, "CAPTURE": {"APPROVED", "PARTIALLY_CAPTURED"}, "CANCEL": {"CREATED"}}
        used, st, created, approved, captured, out = set(), {}, {}, {}, {}, []
        for action, pid, payer, payee, amount in commands:
            amt = int(amount) if amount.lstrip("-").isdigit() else None
            if action == "CREATE":
                ok = pid not in used and payer != "" and payee != "" and amt is not None and amt > 0
                if ok:
                    used.add(pid); st[pid] = "CREATED"; created[pid] = amt; approved[pid] = 0; captured[pid] = 0
            else:
                ok = st.get(pid) in allowed[action]
                if ok and action == "APPROVE":
                    ok = amt is not None and 0 < amt <= created[pid]
                    if ok:
                        approved[pid] = amt; st[pid] = "APPROVED"
                elif ok and action == "CAPTURE":
                    ok = amt is not None and amt > 0 and captured[pid] + amt <= approved[pid]
                    if ok:
                        captured[pid] += amt
                        st[pid] = "SUCCEEDED" if captured[pid] == approved[pid] else "PARTIALLY_CAPTURED"
                elif ok:
                    st[pid] = "CANCELLED"
            out.append(st[pid] if ok else "ERROR")
        return out

    rng = random.Random(17)
    for _ in range(800):
        cmds = []
        for _ in range(rng.randint(0, 25)):
            action = rng.choice(["CREATE", "APPROVE", "CAPTURE", "CANCEL"])
            pid = rng.choice(["p1", "p2", "p3"])
            amount = rng.choice(["", "0", "-3", "1", "2", "3", "5", "8", "13"])
            if action == "CREATE":
                cmds.append([action, pid, rng.choice(["a", ""]), rng.choice(["b", ""]), amount])
            elif action == "CANCEL":
                cmds.append([action, pid, "", "", ""])
            else:
                cmds.append([action, pid, "", "", amount])
        assert f(cmds) == ref(cmds), cmds
    print("All tests passed (including randomized cross-checks).")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        _run_tests()
