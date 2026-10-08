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

        ["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]
            -> [[1020, 1030], [1045, 1080]]
"""

from typing import List


class Solution:
    def scheduleDeploymentWindows(self, part: str, inputCsv: List[str]) -> List[List[int]]:
        WEEK = 7 * 24 * 60  # 10080 minutes

        rows = [line.strip() for line in inputCsv if line and line.strip()]
        part = part.strip().lower().replace("_", "").replace(" ", "")
        is_part2 = part in ("part2", "2", "p2")

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
            s = max(s, earliest_start)
            e = min(e, WEEK)
            if e - s < min_duration:
                continue
            result.append([s, e])
            if len(result) >= k:
                break
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

    print("All tests passed.")


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
