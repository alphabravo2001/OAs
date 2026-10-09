"""
Stripe OA: Deployment Window Scheduler
https://www.fastprep.io/problems/stripe-deployment-window-scheduler

Time is a "minute of week" integer in [0, 10079] (0 = Monday 00:00).
Every window is half-open [start, end): the start minute is included, the
end minute is not.  Results are [[start, end], ...] sorted by start.

part == "part1"
    rows: "start,end,type"           type in {"allowed", "freeze"}
    A minute is deployable iff it lies inside at least one allowed window
    and inside no freeze window.  Return the maximal continuous deployable
    windows (adjacent / overlapping pieces are merged).

        ["540,600,allowed", "570,585,freeze"] -> [[540, 570], [585, 600]]

part == "part2"
    rows[0]:  "utc_now,lead_time_minutes,min_continuous_minutes,k"
    rows[1:]: "start,end,type,offset"   start/end are LOCAL minute-of-week,
              local = utc + offset  =>  utc = local - offset.
    A window converted to UTC may fall outside [0, 10080); it wraps around
    the week and is split at the boundary.  Keep only windows that start at
    or after utc_now + lead_time_minutes, are at least min_continuous_minutes
    long and end by 10080.  Return at most the first k of them.

        ["1020,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]
            -> [[1020, 1030], [1045, 1080]]
"""

from typing import List


class Solution:
    def scheduleDeploymentWindows(self, part: str, inputCsv: List[str]) -> List[List[int]]:
        WEEK = 7 * 24 * 60  # 10080 minutes

        rows = [line.strip() for line in inputCsv if line and line.strip()]
        part_key = (part or "").strip().lower().replace("_", "").replace(" ", "").replace("-", "")
        if part_key in ("part2", "2", "p2", "two"):
            is_part2 = True
        elif part_key in ("part1", "1", "p1", "one"):
            is_part2 = False
        else:
            # Unrecognised label: a leading all-numeric row can only be a part-2 header.
            first = [p.strip() for p in rows[0].split(",")] if rows else []
            is_part2 = len(first) >= 4 and all(p.lstrip("-").isdigit() for p in first)

        # ------------------------------------------------------------------
        # 1. Parse the header (part 2 only) and the window rows.
        # ------------------------------------------------------------------
        earliest_start = 0
        min_duration = 1
        k = None  # None => unlimited (part 1)
        if is_part2:
            if not rows:
                return []
            header = [p.strip() for p in rows[0].split(",")]
            utc_now, lead_time, min_duration, k = (int(x) for x in header[:4])
            earliest_start = utc_now + lead_time
            min_duration = max(min_duration, 1)
            rows = rows[1:]

        allowed = []  # list of (start, end) in UTC minute-of-week
        freeze = []
        for row in rows:
            fields = [p.strip() for p in row.split(",")]
            start, end = int(fields[0]), int(fields[1])
            kind = fields[2].lower()
            if kind not in ("allowed", "freeze"):
                raise ValueError(f"unknown window type {kind!r} in {row!r}")
            bucket = allowed if kind == "allowed" else freeze

            if not is_part2:
                if end > start:
                    bucket.append((start, end))
                continue

            # Part 2: convert local -> UTC and wrap into [0, WEEK).
            offset = int(fields[3]) if len(fields) > 3 and fields[3] else 0
            u_start, u_end = start - offset, end - offset
            if u_end <= u_start:
                continue
            shift = (u_start // WEEK) * WEEK  # whole weeks so start lands in [0, WEEK)
            u_start -= shift
            u_end -= shift
            if u_end - u_start >= WEEK:  # covers the whole week
                bucket.append((0, WEEK))
            elif u_end <= WEEK:
                bucket.append((u_start, u_end))
            else:  # crosses Sunday 23:59 -> Monday 00:00
                bucket.append((u_start, WEEK))
                bucket.append((0, u_end - WEEK))

        # ------------------------------------------------------------------
        # 2. Merge overlapping / adjacent intervals in each bucket.
        # ------------------------------------------------------------------
        merged_allowed = []
        for s, e in sorted(allowed):
            if merged_allowed and s <= merged_allowed[-1][1]:
                merged_allowed[-1][1] = max(merged_allowed[-1][1], e)
            else:
                merged_allowed.append([s, e])

        merged_freeze = []
        for s, e in sorted(freeze):
            if merged_freeze and s <= merged_freeze[-1][1]:
                merged_freeze[-1][1] = max(merged_freeze[-1][1], e)
            else:
                merged_freeze.append([s, e])

        # ------------------------------------------------------------------
        # 3. Subtract freezes from allowed windows (two-pointer sweep).
        # ------------------------------------------------------------------
        deployable = []
        fi = 0
        for a_start, a_end in merged_allowed:
            cur = a_start
            while fi < len(merged_freeze) and merged_freeze[fi][1] <= a_start:
                fi += 1  # freeze ends before this allowed window starts
            j = fi
            while j < len(merged_freeze) and merged_freeze[j][0] < a_end:
                f_start, f_end = merged_freeze[j]
                if f_start > cur:
                    deployable.append([cur, f_start])
                cur = max(cur, f_end)
                if f_end >= a_end:
                    break
                j += 1
            if cur < a_end:
                deployable.append([cur, a_end])

        # Pieces from different allowed windows may now touch; merge again.
        windows = []
        for s, e in sorted(deployable):
            if windows and s <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], e)
            else:
                windows.append([s, e])

        if not is_part2:
            return windows

        # ------------------------------------------------------------------
        # 4. Part 2 filters: lead time, minimum duration, week end, top-k.
        # ------------------------------------------------------------------
        result = []
        for s, e in windows:
            if len(result) >= k:
                break
            s = max(s, earliest_start)
            e = min(e, WEEK)
            if e - s < min_duration:
                continue
            result.append([s, e])
        return result


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().scheduleDeploymentWindows

    # ---- Part 1 ----
    assert f("part1", ["540,600,allowed", "570,585,freeze"]) == [[540, 570], [585, 600]]
    assert f("part1", ["0,100,allowed", "50,200,allowed"]) == [[0, 200]]          # overlap merges
    assert f("part1", ["0,100,allowed", "100,200,allowed"]) == [[0, 200]]         # adjacent merges
    assert f("part1", ["100,200,allowed", "0,10080,freeze"]) == []                # fully frozen
    assert f("part1", ["100,200,allowed", "50,150,freeze", "180,250,freeze"]) == [[150, 180]]
    assert f("part1", ["0,100,allowed", "10,20,freeze", "30,40,freeze", "90,100,freeze"]) == \
        [[0, 10], [20, 30], [40, 90]]
    assert f("part1", ["0,100,freeze"]) == []                                     # no allowed
    assert f("part1", ["0,100,allowed", "20,30,freeze", "25,40,freeze"]) == [[0, 20], [40, 100]]
    assert f("part1", []) == []

    # ---- Part 2 ----
    # Page example (utc_now = 1020, no lead time, min 10 minutes, k = 5).
    assert f("part2", ["1020,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030], [1045, 1080]]
    assert f("part2", ["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030], [1045, 1080]]
    # lead time clips the first window, min duration drops it
    assert f("part2", ["1000,25,20,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1045, 1080]]
    # k caps the count
    assert f("part2", ["0,0,1,1", "540,600,allowed,-480", "550,565,freeze,-480"]) == [[1020, 1030]]
    # wrap below zero: local Mon 00:00-01:00 at UTC+2 -> Sun 22:00-23:00 UTC
    assert f("part2", ["0,0,1,5", "0,60,allowed,120"]) == [[9960, 10020]]
    # wrap across boundary splits in two
    assert f("part2", ["0,0,1,5", "0,120,allowed,60"]) == [[0, 60], [10020, 10080]]
    # wrap above the week: local Sun 23:30-24:00 at UTC-1 -> Mon 00:30-01:00 UTC
    assert f("part2", ["0,0,1,5", "10050,10080,allowed,-60"]) == [[30, 60]]
    # freeze expressed in another offset still applies after conversion
    assert f("part2", ["0,0,1,5", "540,600,allowed,-480", "1030,1045,freeze,0"]) == \
        [[1020, 1030], [1045, 1080]]
    # utc_now + lead past every window -> nothing
    assert f("part2", ["10000,100,1,5", "540,600,allowed,-480"]) == []
    assert f("part2", ["0,0,1,5"]) == []
    # k == 0 returns nothing; min_continuous exactly equal to the window length is kept.
    assert f("part2", ["0,0,10,0", "540,600,allowed,-480"]) == []
    assert f("part2", ["0,0,60,5", "540,600,allowed,-480"]) == [[1020, 1080]]
    assert f("part2", ["0,0,61,5", "540,600,allowed,-480"]) == []
    # Lead time landing exactly on a window start keeps the whole window.
    assert f("part2", ["1000,20,1,5", "540,600,allowed,-480"]) == [[1020, 1080]]
    # Lead time clips a window that already started.
    assert f("part2", ["1000,30,1,5", "540,600,allowed,-480"]) == [[1030, 1080]]
    # Positive offset (east of UTC): local 600-660 at UTC+60 -> 540-600 UTC.
    assert f("part2", ["0,0,1,5", "600,660,allowed,60"]) == [[540, 600]]
    # A freeze that wraps the week boundary cuts both ends of the week.
    assert f("part2", ["0,0,1,5", "0,10080,allowed,0", "10050,10110,freeze,0"]) == [[30, 10050]]
    # An allowed window covering more than a whole week is the whole week.
    assert f("part2", ["0,0,1,5", "0,20000,allowed,0"]) == [[0, 10080]]
    # Rows may arrive unsorted and overlapping; adjacent deployable pieces merge across wrap pieces.
    assert f("part2", ["0,0,1,5", "100,200,allowed,0", "0,100,allowed,0", "150,160,freeze,0"]) == \
        [[0, 150], [160, 200]]
    # Part label variants are accepted; an unlabeled numeric header is detected as part 2.
    assert f("PART_2", ["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030], [1045, 1080]]
    assert f("Part 1", ["540,600,allowed", "570,585,freeze"]) == [[540, 570], [585, 600]]
    assert f("", ["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030], [1045, 1080]]
    assert f("", ["540,600,allowed", "570,585,freeze"]) == [[540, 570], [585, 600]]
    # Whitespace around fields is tolerated.
    assert f("part1", [" 540 , 600 , allowed ", "570,585, freeze"]) == [[540, 570], [585, 600]]

    # ---- Brute-force cross-check on random inputs (minute-by-minute simulation) ----
    import random

    WEEK = 10080

    def runs(mask):
        out, start = [], None
        for m in range(WEEK + 1):
            on = m < WEEK and mask[m]
            if on and start is None:
                start = m
            elif not on and start is not None:
                out.append([start, m])
                start = None
        return out

    def brute1(rows):
        allowed = [False] * WEEK
        frozen = [False] * WEEK
        for r in rows:
            s, e, kind = r.split(",")
            for m in range(int(s), int(e)):
                (allowed if kind == "allowed" else frozen)[m] = True
        return runs([a and not z for a, z in zip(allowed, frozen)])

    def brute2(rows):
        utc_now, lead, min_dur, k = (int(x) for x in rows[0].split(","))
        allowed = [False] * WEEK
        frozen = [False] * WEEK
        for r in rows[1:]:
            s, e, kind, off = r.split(",")
            for m in range(int(s), int(e)):
                (allowed if kind == "allowed" else frozen)[(m - int(off)) % WEEK] = True
        out = []
        for s, e in runs([a and not z for a, z in zip(allowed, frozen)]):
            s = max(s, utc_now + lead)
            if e - s >= max(min_dur, 1):
                out.append([s, e])
        return out[:k]

    rng = random.Random(2026)
    for _ in range(300):
        rows = []
        for _ in range(rng.randint(0, 6)):
            s = rng.randint(0, WEEK - 1)
            e = rng.randint(s, min(WEEK, s + 3000))
            rows.append(f"{s},{e},{rng.choice(['allowed', 'freeze'])}")
        assert f("part1", rows) == brute1(rows), rows

    for _ in range(300):
        utc_now = rng.randint(0, WEEK - 1)
        header = f"{utc_now},{rng.randint(0, 500)},{rng.randint(0, 200)},{rng.randint(0, 6)}"
        rows = [header]
        for _ in range(rng.randint(0, 6)):
            s = rng.randint(0, WEEK - 1)
            e = rng.randint(s, min(WEEK, s + 3000))
            off = rng.choice([-720, -480, -300, 0, 60, 120, 330, 540, 780])
            rows.append(f"{s},{e},{rng.choice(['allowed', 'freeze'])},{off}")
        assert f("part2", rows) == brute2(rows), rows

    print("All tests passed (including 600 randomized brute-force comparisons).")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        # stdin: first line is the part ("part1"/"part2"), remaining lines are the CSV rows.
        data = [l.rstrip("\n") for l in sys.stdin if l.strip()]
        if not data:
            _run_tests()
        else:
            print(Solution().scheduleDeploymentWindows(data[0], data[1:]))
