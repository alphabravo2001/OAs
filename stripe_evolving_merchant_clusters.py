"""
Stripe OA: Evolving Merchant Clusters and Persistent Pins
https://www.fastprep.io/problems/stripe-evolving-merchant-clusters

evolvingMerchantClusters(day1, day2, day3) -> String[]

Each daily batch holds records "merchant_id,link_type,duration" first reported on
that day.  A record is active from its report day for `duration` days (1..3,
clipped to day 3); a (merchant, link_type) pair is active on a day covered by at
least one of its reported lifetimes.  A merchant enters the system on the first
day it appears and never leaves.

Each day, over all merchants seen so far:
* two distinct merchants are adjacent when they share at least one active
  link_type (every active link type forms a clique);
* a cluster is a connected component with at least two merchants;
* a merchant's degree is its number of distinct adjacent merchants.

Pin lifecycle (per cluster, days processed in order).  Candidates are the
previous day's pins that belong to the current component:
    none      -> fresh pin: greatest degree, ties -> lexicographically smaller id
    exactly 1 -> preserved (growth, or the side of a split that kept its pin)
    2 or more -> merge: among those pins, greatest degree, ties -> smaller id

Output, flattened: "Day X:" then one line per cluster, ordered by decreasing size
then increasing pin id, each "pin:id1,id2,..." with ids sorted lexicographically.
Singleton components are not printed.

    ["acct_a,address:main,2", "acct_b,address:main,2"],
    ["acct_b,email:team,2", "acct_c,email:team,2"], []
        -> ["Day 1:", "acct_a:acct_a,acct_b",
            "Day 2:", "acct_a:acct_a,acct_b,acct_c",
            "Day 3:", "acct_b:acct_b,acct_c"]
"""

from typing import List


class Solution:
    def evolvingMerchantClusters(self, day1: List[str], day2: List[str],
                                 day3: List[str]) -> List[str]:
        NUM_DAYS = 3
        batches = [day1 or [], day2 or [], day3 or []]

        first_seen = {}      # merchant -> first day it appears
        active_days = {}     # (merchant, link_type) -> set of days the pair is active
        for day, batch in enumerate(batches, start=1):
            for raw in batch:
                line = raw.strip() if raw else ""
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                merchant = parts[0].strip()
                link = ",".join(parts[1:-1]).strip()
                try:
                    duration = int(parts[-1].strip())
                except ValueError:
                    duration = 1
                first_seen.setdefault(merchant, day)
                days = active_days.setdefault((merchant, link), set())
                days.update(range(day, min(NUM_DAYS, day + max(duration, 1) - 1) + 1))

        out = []
        prev_pins = set()
        for day in range(1, NUM_DAYS + 1):
            merchants = [m for m, d in first_seen.items() if d <= day]

            # Members of every link type that is active today.
            members = {}
            for (merchant, link), days in active_days.items():
                if day in days:
                    members.setdefault(link, set()).add(merchant)

            # Adjacency: each active link type is a clique.
            adj = {m: set() for m in merchants}
            for group in members.values():
                if len(group) >= 2:
                    for m in group:
                        adj[m] |= group
            for m in merchants:
                adj[m].discard(m)

            # Connected components with at least two merchants.
            clusters, seen = [], set()
            for start in merchants:
                if start in seen or not adj[start]:
                    continue
                component, stack = {start}, [start]
                seen.add(start)
                while stack:
                    for nxt in adj[stack.pop()]:
                        if nxt not in seen:
                            seen.add(nxt)
                            component.add(nxt)
                            stack.append(nxt)
                clusters.append(component)

            # Pins: previous pins inside the component, else a fresh choice.
            new_pins, lines = set(), []
            for component in clusters:
                candidates = [p for p in prev_pins if p in component]
                pool = candidates if candidates else component
                pin = min(pool, key=lambda m: (-len(adj[m]), m))
                new_pins.add(pin)
                lines.append((-len(component), pin, ",".join(sorted(component))))

            out.append(f"Day {day}:")
            for _, pin, ids in sorted(lines):
                out.append(f"{pin}:{ids}")
            prev_pins = new_pins

        return out


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().evolvingMerchantClusters

    # Example 1 (growth preserves the pin; expiry forces a fresh pin)
    assert f(["acct_a,address:main,2", "acct_b,address:main,2"],
             ["acct_b,email:team,2", "acct_c,email:team,2"], []) == \
        ["Day 1:", "acct_a:acct_a,acct_b", "Day 2:", "acct_a:acct_a,acct_b,acct_c",
         "Day 3:", "acct_b:acct_b,acct_c"]
    # Example 2 (merge picks the prior pin with the higher degree)
    assert f(["a1,left,3", "a2,left,3", "b1,right,3", "b2,right,3"],
             ["a2,bridge,2", "b1,bridge,2"], []) == \
        ["Day 1:", "a1:a1,a2", "b1:b1,b2", "Day 2:", "b1:a1,a2,b1,b2", "Day 3:", "b1:a1,a2,b1,b2"]
    # Example 3 (empty day, size ordering, one-day links)
    assert f([], ["m1,z,1", "m2,z,1", "a,x,2", "b,x,2", "c,x,2"], []) == \
        ["Day 1:", "Day 2:", "a:a,b,c", "m1:m1,m2", "Day 3:", "a:a,b,c"]

    # No records at all: three headers.
    assert f([], [], []) == ["Day 1:", "Day 2:", "Day 3:"]
    # Split: q (degree 3) is the day-1 pin; on day 2 only p-q remains and keeps q.
    assert f(["p,l1,3", "q,l1,3", "q,l2,1", "r,l2,1", "s,l2,1"], [], []) == \
        ["Day 1:", "q:p,q,r,s", "Day 2:", "q:p,q", "Day 3:", "q:p,q"]
    # Split where the old pin leaves: the pin-less side chooses a fresh pin.
    assert f(["a,l1,1", "b,l1,1", "c,l2,3", "d,l2,3", "b,l3,1", "c,l3,1"], [], []) == \
        ["Day 1:", "b:a,b,c,d", "Day 2:", "c:c,d", "Day 3:", "c:c,d"]
    # Merge tie on degree -> lexicographically smaller prior pin.
    assert f(["x1,l,3", "x2,l,3", "y1,m,3", "y2,m,3"], ["x1,bridge,1", "y1,bridge,1"], []) == \
        ["Day 1:", "x1:x1,x2", "y1:y1,y2", "Day 2:", "x1:x1,x2,y1,y2",
         "Day 3:", "x1:x1,x2", "y1:y1,y2"]
    # Degree counts distinct neighbours, not shared link types: b has 2 neighbours, a has 1
    # even though a-b share two links.
    assert f(["a,l1,1", "b,l1,1", "a,l2,1", "b,l2,1", "b,l3,1", "c,l3,1"], [], []) == \
        ["Day 1:", "b:a,b,c", "Day 2:", "Day 3:"]
    # Only the previous day's pins count: a day-1 pin whose cluster vanished on day 2 is not
    # a candidate on day 3 (fresh choice falls to the smaller id of a tie).
    assert f(["z,l,1", "y,l,1"], [], ["z,l,1", "y,l,1"]) == \
        ["Day 1:", "y:y,z", "Day 2:", "Day 3:", "y:y,z"]
    assert f(["z,l,1", "y,l,1", "z,k,1", "w,k,1"], [], ["z,l,1", "y,l,1"]) == \
        ["Day 1:", "z:w,y,z", "Day 2:", "Day 3:", "y:y,z"]
    # Renewal: a later record extends the same pair, keeping the cluster alive.
    assert f(["a,l,1", "b,l,3"], ["a,l,2"], []) == \
        ["Day 1:", "a:a,b", "Day 2:", "a:a,b", "Day 3:", "a:a,b"]
    # A merchant seen only on day 3 does not exist on earlier days; its link type matching an
    # expired one does not connect it to anybody.
    assert f(["a,l,1"], [], ["b,l,1"]) == ["Day 1:", "Day 2:", "Day 3:"]
    # Cluster ordering: size descending, then pin id ascending.
    assert f(["b,l,1", "c,l,1", "a,m,1", "d,m,1", "e,n,1", "f,n,1", "g,n,1"], [], []) == \
        ["Day 1:", "e:e,f,g", "a:a,d", "b:b,c", "Day 2:", "Day 3:"]

    # ---- Randomized cross-check against a pairwise / union-find reference ----
    import random

    def ref_clusters(d1, d2, d3):
        batches = [d1, d2, d3]
        recs = []   # (merchant, link, first_day, last_day)
        for day, batch in enumerate(batches, 1):
            for row in batch:
                m, l, dur = row.split(",")
                recs.append((m, l, day, min(3, day + int(dur) - 1)))
        out, prev = [], set()
        for day in range(1, 4):
            ms = sorted({m for m, _, d0, _ in recs if d0 <= day})
            act = {(m, l) for m, l, a, b in recs if a <= day <= b}
            links = {l for _, l in act}

            def adjacent(u, v):
                return any((u, l) in act and (v, l) in act for l in links)

            parent = {m: m for m in ms}

            def find(x):
                while parent[x] != x:
                    x = parent[x]
                return x

            deg = {m: 0 for m in ms}
            for i, u in enumerate(ms):
                for v in ms[i + 1:]:
                    if adjacent(u, v):
                        deg[u] += 1
                        deg[v] += 1
                        parent[find(u)] = find(v)
            comps = {}
            for m in ms:
                comps.setdefault(find(m), set()).add(m)
            rows, new_prev = [], set()
            for comp in comps.values():
                if len(comp) < 2:
                    continue
                inside = sorted(p for p in prev if p in comp)
                if len(inside) == 0:
                    pin = sorted(comp, key=lambda m: (-deg[m], m))[0]
                elif len(inside) == 1:
                    pin = inside[0]
                else:
                    pin = sorted(inside, key=lambda m: (-deg[m], m))[0]
                new_prev.add(pin)
                rows.append((-len(comp), pin, ",".join(sorted(comp))))
            out.append(f"Day {day}:")
            out.extend(f"{p}:{ids}" for _, p, ids in sorted(rows))
            prev = new_prev
        return out

    rng = random.Random(21)
    ids = ["a", "b", "ab", "m1", "m2", "m10", "z_9"]
    links = ["l1", "l2", "addr:x", "e mail"]
    for _ in range(600):
        days = []
        for _ in range(3):
            pairs = set()
            batch = []
            for _ in range(rng.randint(0, 6)):
                m, l = rng.choice(ids), rng.choice(links)
                if (m, l) in pairs:
                    continue
                pairs.add((m, l))
                batch.append(f"{m},{l},{rng.randint(1, 3)}")
            days.append(batch)
        assert f(*days) == ref_clusters(*days), days
    print("All tests passed (including randomized cross-checks).")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        # stdin format: three batches separated by a line containing only "---"
        text = sys.stdin.read()
        if not text.strip():
            _run_tests()
        else:
            batches = [[l for l in part.split("\n") if l.strip()] for part in text.split("---")]
            while len(batches) < 3:
                batches.append([])
            print("\n".join(Solution().evolvingMerchantClusters(*batches[:3])))
