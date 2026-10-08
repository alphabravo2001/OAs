"""
Stripe OA: Deployment Window Scheduler
https://www.fastprep.io/problems/stripe-deployment-window-scheduler

Time model
----------
Time is a "minute of week" integer in [0, 10079]: 0 = Monday 00:00,
60 = Monday 01:00, 1440 = Tuesday 00:00, 10079 = Sunday 23:59.
Every window is "start,end" and half-open [start, end): the start minute is
included, the end minute is not ("10,12" covers minutes 10 and 11).

scheduleDeploymentWindows(part, inputCsv) -> [[start, end], ...]
    `part` selects the stage ("part1" or "part2"); `inputCsv` holds the
    corresponding CSV rows.  The result is sorted by start time.

Part 1: Allowed Windows (Tests 1-4)
-----------------------------------
Every row is "start,end,type" with type "allowed" or "freeze".
A minute is deployable only when it is inside at least one allowed window
and inside no freeze window.  Allowed windows may overlap, freeze windows
may overlap, and adjacent deployable intervals are returned as one
continuous window.

    part1, ["540,600,allowed", "570,585,freeze"] -> [[540, 570], [585, 600]]

Part 2: Time Zones and Minimum Duration (Tests 5-11)
----------------------------------------------------
Row 0 is the header "utc_now,lead_time_minutes,min_continuous_minutes,k".
Every remaining row is "start,end,type,timezone_offset_minutes" where
start/end are LOCAL minute-of-week values and local = UTC + offset, so
UTC = local - offset.  Each window is converted to UTC and normalized over
the 10080-minute week; a converted interval that crosses the weekly
boundary is split at the boundary.

After conversion a minute is deployable when it is inside at least one
allowed window and inside no freeze window.  A returned UTC window must
  * start no earlier than utc_now + lead_time_minutes,
  * remain continuously deployable for at least min_continuous_minutes,
  * end no later than minute 10080.
Deployable intervals are clipped to the earliest permitted start, intervals
that are then too short are discarded, the survivors are sorted by start,
and at most the first k are returned (fewer when fewer exist).

    part2, ["1020,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]
        -> [[1020, 1030], [1045, 1080]]
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

MINUTES_PER_WEEK = 7 * 24 * 60  # 10080

Interval = Tuple[int, int]  # half-open [start, end)


class Solution:
    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def scheduleDeploymentWindows(self, part: str, inputCsv: List[str]) -> List[List[int]]:
        rows = [row.strip() for row in inputCsv if row and row.strip()]
        key = part.strip().lower().replace(" ", "").replace("_", "")
        if key in ("part1", "1"):
            return self._part1(rows)
        if key in ("part2", "2"):
            return self._part2(rows)
        raise ValueError(f"unknown part {part!r}")

    # ------------------------------------------------------------------ #
    # Part 1: allowed minus freeze, merged and sorted
    # ------------------------------------------------------------------ #
    def _part1(self, rows: List[str]) -> List[List[int]]:
        allowed: List[Interval] = []
        freeze: List[Interval] = []
        for row in rows:
            start, end, kind = self._parse_rule(row)
            (allowed if kind == "allowed" else freeze).append((start, end))
        return [list(w) for w in self._deployable(allowed, freeze)]

    # ------------------------------------------------------------------ #
    # Part 2: time zones, lead time, minimum duration, first k
    # ------------------------------------------------------------------ #
    def _part2(self, rows: List[str]) -> List[List[int]]:
        if not rows:
            return []
        utc_now, lead, min_dur, k = (int(p) for p in rows[0].split(",")[:4])
        earliest_start = utc_now + lead
        if k <= 0:
            return []

        allowed: List[Interval] = []
        freeze: List[Interval] = []
        for row in rows[1:]:
            start, end, kind, offset = self._parse_rule_tz(row)
            target = allowed if kind == "allowed" else freeze
            target.extend(self._local_to_utc(start, end, offset))

        result: List[List[int]] = []
        for start, end in self._deployable(allowed, freeze):
            start = max(start, earliest_start)        # clip to earliest permitted start
            end = min(end, MINUTES_PER_WEEK)          # never past the end of the week
            if end <= start or end - start < min_dur:  # discard what is now too short
                continue
            result.append([start, end])
            if len(result) == k:
                break
        return result

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_kind(kind: str, row: str) -> str:
        kind = kind.strip().lower()
        if kind not in ("allowed", "freeze"):
            raise ValueError(f"unknown window type {kind!r} in {row!r}")
        return kind

    def _parse_rule(self, row: str) -> Tuple[int, int, str]:
        parts = [p.strip() for p in row.split(",")]
        if len(parts) < 3:
            raise ValueError(f"expected 'start,end,type', got {row!r}")
        return int(parts[0]), int(parts[1]), self._parse_kind(parts[2], row)

    def _parse_rule_tz(self, row: str) -> Tuple[int, int, str, int]:
        parts = [p.strip() for p in row.split(",")]
        if len(parts) < 4:
            raise ValueError(f"expected 'start,end,type,offset', got {row!r}")
        return int(parts[0]), int(parts[1]), self._parse_kind(parts[2], row), int(parts[3])

    # ------------------------------------------------------------------ #
    # Interval helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _merge(intervals: Iterable[Interval]) -> List[Interval]:
        """Merge overlapping *and adjacent* half-open intervals, sorted by start."""
        merged: List[Interval] = []
        for start, end in sorted(intervals):
            if end <= start:  # empty interval
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _subtract(allowed: List[Interval], freeze: List[Interval]) -> List[Interval]:
        """allowed - freeze; both inputs must already be merged and sorted."""
        result: List[Interval] = []
        i = 0
        for start, end in allowed:
            cur = start
            while i < len(freeze) and freeze[i][1] <= start:
                i += 1  # this freeze ends before the allowed window starts
            j = i
            while j < len(freeze) and freeze[j][0] < end:
                f_start, f_end = freeze[j]
                if f_start > cur:
                    result.append((cur, f_start))
                cur = max(cur, f_end)
                if f_end >= end:
                    break
                j += 1
            if cur < end:
                result.append((cur, end))
        return result

    def _deployable(self, allowed: Iterable[Interval], freeze: Iterable[Interval]) -> List[Interval]:
        """Maximal continuous ranges that are allowed and not frozen."""
        return self._merge(self._subtract(self._merge(allowed), self._merge(freeze)))

    @staticmethod
    def _local_to_utc(start: int, end: int, offset: int) -> List[Interval]:
        """
        Convert a local half-open window to UTC (utc = local - offset) and
        normalize it into [0, 10080).  A window crossing the week boundary is
        split into two pieces; one covering a whole week becomes [0, 10080).
        """
        u_start, u_end = start - offset, end - offset
        if u_end <= u_start:
            return []
        if u_end - u_start >= MINUTES_PER_WEEK:
            return [(0, MINUTES_PER_WEEK)]
        shift = (u_start // MINUTES_PER_WEEK) * MINUTES_PER_WEEK
        u_start -= shift
        u_end -= shift
        if u_end <= MINUTES_PER_WEEK:
            return [(u_start, u_end)]
        return [(0, u_end - MINUTES_PER_WEEK), (u_start, MINUTES_PER_WEEK)]


# ---------------------------------------------------------------------- #
# Self-tests
# ---------------------------------------------------------------------- #
def _run_tests() -> None:
    s = Solution()

    # --- Examples from the problem page ----------------------------------
    assert s.scheduleDeploymentWindows(
        "part1", ["540,600,allowed", "570,585,freeze"]) == [[540, 570], [585, 600]]
    assert s.scheduleDeploymentWindows(
        "part2", ["1020,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030], [1045, 1080]]

    # --- Part 1 extras ----------------------------------------------------
    assert s.scheduleDeploymentWindows("part1", ["0,100,allowed", "50,200,allowed"]) == [[0, 200]]
    assert s.scheduleDeploymentWindows("part1", ["0,100,allowed", "100,200,allowed"]) == [[0, 200]]
    assert s.scheduleDeploymentWindows("part1", ["100,200,allowed", "0,10080,freeze"]) == []
    assert s.scheduleDeploymentWindows(
        "part1", ["100,200,allowed", "50,150,freeze", "180,250,freeze"]) == [[150, 180]]
    assert s.scheduleDeploymentWindows(
        "part1", ["0,100,allowed", "10,20,freeze", "30,40,freeze", "90,100,freeze"]) == \
        [[0, 10], [20, 30], [40, 90]]
    assert s.scheduleDeploymentWindows("part1", ["0,100,freeze"]) == []
    assert s.scheduleDeploymentWindows("part1", []) == []
    # Freeze that splits one allowed window into two adjacent allowed windows' union.
    assert s.scheduleDeploymentWindows(
        "part1", ["0,50,allowed", "50,100,allowed", "40,60,freeze"]) == [[0, 40], [60, 100]]

    # --- Part 2 extras ----------------------------------------------------
    # Lead time clips the first window; min duration drops the short one.
    assert s.scheduleDeploymentWindows(
        "part2", ["1000,25,20,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == [[1045, 1080]]
    # k limits the number of windows.
    assert s.scheduleDeploymentWindows(
        "part2", ["0,0,1,1", "540,600,allowed,-480", "550,565,freeze,-480"]) == [[1020, 1030]]
    # Earliest start inside a window clips it; remaining length checked afterwards.
    assert s.scheduleDeploymentWindows(
        "part2", ["1025,0,5,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1025, 1030], [1045, 1080]]
    assert s.scheduleDeploymentWindows(
        "part2", ["1026,0,5,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == [[1045, 1080]]
    # Wrap below zero: local Monday 00:00-01:00 at UTC+120 -> Sunday 22:00-23:00 UTC.
    assert s.scheduleDeploymentWindows("part2", ["0,0,1,5", "0,60,allowed,120"]) == [[9960, 10020]]
    # Wrap across the boundary splits into two pieces, sorted by start.
    assert s.scheduleDeploymentWindows(
        "part2", ["0,0,1,5", "0,120,allowed,60"]) == [[0, 60], [10020, 10080]]
    # Wrap above the week: local Sunday 23:30-24:00 at UTC-60 -> Monday 00:30-01:00 UTC.
    assert s.scheduleDeploymentWindows("part2", ["0,0,1,5", "10050,10080,allowed,-60"]) == [[30, 60]]
    # A freeze given in a different offset still applies after conversion.
    assert s.scheduleDeploymentWindows(
        "part2", ["0,0,1,5", "540,600,allowed,-480", "1030,1045,freeze,0"]) == \
        [[1020, 1030], [1045, 1080]]
    # Windows from different zones merge into one UTC calendar.
    assert s.scheduleDeploymentWindows(
        "part2", ["0,0,1,5", "0,60,allowed,0", "120,180,allowed,60"]) == [[0, 120]]
    # Nothing starts late enough.
    assert s.scheduleDeploymentWindows("part2", ["10000,100,1,5", "0,60,allowed,0"]) == []
    # Whole-week allowed window with a freeze.
    assert s.scheduleDeploymentWindows(
        "part2", ["0,0,1,5", "0,10080,allowed,300", "100,200,freeze,0"]) == [[0, 100], [200, 10080]]
    # k = 0 returns nothing; header only returns nothing.
    assert s.scheduleDeploymentWindows("part2", ["0,0,1,0", "0,60,allowed,0"]) == []
    assert s.scheduleDeploymentWindows("part2", ["0,0,1,5"]) == []

    print("All tests passed.")


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    elif len(sys.argv) > 1:
        # Usage: python stripe_deployment_window_scheduler.py part1 < rows.csv
        rows = [line.rstrip("\n") for line in sys.stdin if line.strip()]
        print(json.dumps(Solution().scheduleDeploymentWindows(sys.argv[1], rows)))
    else:
        _run_tests()
