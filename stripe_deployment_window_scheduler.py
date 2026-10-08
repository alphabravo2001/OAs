"""
Stripe OA: Deployment Window Scheduler
https://www.fastprep.io/problems/stripe-deployment-window-scheduler

Time model
----------
Time is a "minute of week" integer in [0, 10079]: 0 = Monday 00:00,
1440 = Tuesday 00:00, 10079 = Sunday 23:59.  Every window is half-open
[start, end): the start minute is included, the end minute is not.

Part 1
------
Input lines look like "start,end,type" where type is "allowed" or "freeze".
A minute is deployable iff it lies inside at least one allowed window and
inside no freeze window.  Return the sorted list of maximal continuous
deployable windows as [start, end] pairs (adjacent pieces are merged).

    ["540,600,allowed", "570,585,freeze"]  ->  [[540, 570], [585, 600]]

Part 2
------
The first line is a header "utc_now,lead_time_minutes,min_continuous_minutes,k".
Every following line is "start,end,type,offset" where start/end are LOCAL
minute-of-week values and local = utc + offset, so utc = local - offset.
A window converted to UTC may fall before minute 0 or past minute 10080;
it then wraps around the week and is split at the boundary.

A returned window must
  * start at or after utc_now + lead_time_minutes,
  * be at least min_continuous_minutes long,
  * end by minute 10080.
Return at most the first k such windows sorted by start time.

    ["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]
        -> [[1020, 1030], [1045, 1080]]
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

MINUTES_PER_WEEK = 7 * 24 * 60  # 10080

Interval = Tuple[int, int]  # half-open [start, end)


# --------------------------------------------------------------------------- #
# Interval helpers
# --------------------------------------------------------------------------- #
def merge(intervals: Iterable[Interval]) -> List[Interval]:
    """Merge overlapping *and adjacent* half-open intervals, sorted by start."""
    merged: List[Interval] = []
    for start, end in sorted(intervals):
        if end <= start:  # empty interval, ignore
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(allowed: List[Interval], freeze: List[Interval]) -> List[Interval]:
    """allowed - freeze.  Both inputs must already be merged/sorted."""
    result: List[Interval] = []
    i = 0
    for start, end in allowed:
        cur = start
        # Skip freezes that end before this allowed window starts.
        while i < len(freeze) and freeze[i][1] <= start:
            i += 1
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


def deployable_windows(allowed: Iterable[Interval],
                       freeze: Iterable[Interval]) -> List[Interval]:
    """Maximal continuous ranges that are allowed and not frozen."""
    return merge(subtract(merge(allowed), merge(freeze)))


# --------------------------------------------------------------------------- #
# Part 1
# --------------------------------------------------------------------------- #
def parse_rule(line: str) -> Tuple[int, int, str]:
    start, end, kind = (p.strip() for p in line.split(",")[:3])
    kind = kind.lower()
    if kind not in ("allowed", "freeze"):
        raise ValueError(f"unknown window type {kind!r} in {line!r}")
    return int(start), int(end), kind


def schedule_part1(lines: Iterable[str]) -> List[List[int]]:
    allowed: List[Interval] = []
    freeze: List[Interval] = []
    for line in lines:
        if not line.strip():
            continue
        start, end, kind = parse_rule(line)
        (allowed if kind == "allowed" else freeze).append((start, end))
    return [list(w) for w in deployable_windows(allowed, freeze)]


# --------------------------------------------------------------------------- #
# Part 2
# --------------------------------------------------------------------------- #
def local_to_utc(start: int, end: int, offset: int) -> List[Interval]:
    """
    Convert a local half-open window to UTC and wrap it into [0, 10080).
    A window that crosses the week boundary is split into two pieces.
    """
    u_start, u_end = start - offset, end - offset
    if u_end <= u_start:
        return []
    # Shift by whole weeks so the start lands inside [0, 10080).
    shift = (u_start // MINUTES_PER_WEEK) * MINUTES_PER_WEEK
    u_start -= shift
    u_end -= shift
    if u_end <= MINUTES_PER_WEEK:
        return [(u_start, u_end)]
    if u_end - u_start >= MINUTES_PER_WEEK:  # covers the whole week
        return [(0, MINUTES_PER_WEEK)]
    return [(u_start, MINUTES_PER_WEEK), (0, u_end - MINUTES_PER_WEEK)]


def schedule_part2(lines: List[str],
                   split_into_min_chunks: bool = False) -> List[List[int]]:
    """
    lines[0]  = "utc_now,lead_time_minutes,min_continuous_minutes,k"
    lines[1:] = "start,end,type,offset"   (local minute-of-week, utc = local - offset)

    split_into_min_chunks=False (FastPrep behaviour): each surviving window is
        returned whole, e.g. [1045, 1080].
    split_into_min_chunks=True (variant some candidates report): every window
        is cut into back-to-back pieces of exactly min_continuous_minutes
        until k windows have been produced.
    """
    lines = [l for l in lines if l.strip()]
    utc_now, lead, min_dur, k = (int(p) for p in lines[0].split(",")[:4])
    earliest_start = utc_now + lead

    allowed: List[Interval] = []
    freeze: List[Interval] = []
    for line in lines[1:]:
        start, end, kind, offset = (p.strip() for p in line.split(",")[:4])
        kind = kind.lower()
        if kind not in ("allowed", "freeze"):
            raise ValueError(f"unknown window type {kind!r} in {line!r}")
        target = allowed if kind == "allowed" else freeze
        target.extend(local_to_utc(int(start), int(end), int(offset)))

    result: List[List[int]] = []
    for start, end in deployable_windows(allowed, freeze):
        start = max(start, earliest_start)
        end = min(end, MINUTES_PER_WEEK)
        if end - start < max(min_dur, 1):
            continue
        if split_into_min_chunks:
            while end - start >= min_dur and len(result) < k:
                result.append([start, start + min_dur])
                start += min_dur
        else:
            result.append([start, end])
        if len(result) >= k:
            break
    return result[:k]


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    # Part 1 example from the problem statement.
    assert schedule_part1(["540,600,allowed", "570,585,freeze"]) == [[540, 570], [585, 600]]
    # Overlapping allowed windows merge; adjacent pieces merge.
    assert schedule_part1(["0,100,allowed", "50,200,allowed"]) == [[0, 200]]
    assert schedule_part1(["0,100,allowed", "100,200,allowed"]) == [[0, 200]]
    # Freeze that covers everything -> nothing deployable.
    assert schedule_part1(["100,200,allowed", "0,10080,freeze"]) == []
    # Freeze that straddles the start / end of an allowed window.
    assert schedule_part1(["100,200,allowed", "50,150,freeze", "180,250,freeze"]) == [[150, 180]]
    # Multiple freezes inside one allowed window.
    assert schedule_part1(["0,100,allowed", "10,20,freeze", "30,40,freeze", "90,100,freeze"]) == \
        [[0, 10], [20, 30], [40, 90]]
    # No allowed windows at all.
    assert schedule_part1(["0,100,freeze"]) == []

    # Part 2 example from the problem statement (offset -480 => utc = local + 480).
    assert schedule_part2(["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030], [1045, 1080]]
    # Lead time clips the first window; min duration drops the short one.
    assert schedule_part2(["1000,25,20,5", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1045, 1080]]
    # k limits the number of windows.
    assert schedule_part2(["0,0,1,1", "540,600,allowed,-480", "550,565,freeze,-480"]) == \
        [[1020, 1030]]
    # Wrap below zero: local Monday 00:00-01:00 at UTC+120 -> Sunday 22:00-23:00 UTC.
    assert schedule_part2(["0,0,1,5", "0,60,allowed,120"]) == [[9960, 10020]]
    # Wrap across the boundary splits into two pieces.
    assert schedule_part2(["0,0,1,5", "0,120,allowed,60"]) == [[0, 60], [10020, 10080]]
    # Wrap above the week: local Sunday 23:30-24:00 at UTC-60 -> Monday 00:30-01:00 UTC.
    assert schedule_part2(["0,0,1,5", "10050,10080,allowed,-60"]) == [[30, 60]]
    # A freeze given in a different offset still applies after conversion.
    assert schedule_part2(["0,0,1,5", "540,600,allowed,-480", "1030,1045,freeze,0"]) == \
        [[1020, 1030], [1045, 1080]]
    # Chunking variant.
    assert schedule_part2(["0,0,10,5", "540,600,allowed,-480", "550,565,freeze,-480"],
                          split_into_min_chunks=True) == \
        [[1020, 1030], [1045, 1055], [1055, 1065], [1065, 1075]]

    print("All tests passed.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        # Read input lines from stdin.  If the first line has 4 numeric fields
        # it is treated as a Part 2 header, otherwise the input is Part 1.
        data = [l.rstrip("\n") for l in sys.stdin if l.strip()]
        if not data:
            _run_tests()
        else:
            first = data[0].split(",")
            if len(first) == 4 and all(p.strip().lstrip("-").isdigit() for p in first):
                print(schedule_part2(data))
            else:
                print(schedule_part1(data))
