"""
Stripe: Request Routing System
https://www.fastprep.io/problems/stripe-request-routing-system

solveRequestRoutingSystem(input) -> String[]

The input is the whole newline-separated command stream as one string; one output
string is returned per command.

    REGISTER name lat lon capacity   OK and add when name is new, lat in [-90, 90],
                                     lon in [-180, 180], capacity a positive integer;
                                     otherwise ERROR.  New datacenters are healthy, load 0.
    SET_HEALTHY name value           OK and set health from case-insensitive true/false
                                     for an existing datacenter; otherwise ERROR.
    DISTANCE lat1 lon1 lat2 lon2     Haversine distance, Earth radius 6371 km, rounded to
                                     the nearest integer; ERROR for invalid coordinates.
    ROUTE lat lon                    Healthy datacenters sorted by exact distance, ties by
                                     name.  Pick the first with load < capacity, increment
                                     its load and return "name rounded_distance candidates"
                                     (candidates = all healthy names, comma-joined, in that
                                     order).  All full -> "None candidates".  No healthy
                                     datacenters -> exactly "None".

    "REGISTER node-A 0 0 1\nREGISTER node-B 0 0 1\nROUTE 0 0"
        -> ["OK", "OK", "node-A 0 node-A,node-B"]
"""

import math
from typing import List


class Solution:
    def solveRequestRoutingSystem(self, input: str) -> List[str]:
        EARTH_RADIUS_KM = 6371.0

        datacenters = {}   # name -> {"lat", "lon", "capacity", "healthy", "load"}
        output = []

        def parse_coord(lat_s, lon_s):
            """Return (lat, lon) as floats, or None if either is out of range / not numeric."""
            try:
                lat, lon = float(lat_s), float(lon_s)
            except ValueError:
                return None
            if math.isnan(lat) or math.isnan(lon):
                return None
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                return None
            return lat, lon

        def haversine(lat1, lon1, lat2, lon2):
            p1, p2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlmb = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
            a = min(1.0, max(0.0, a))
            return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

        def display(km):
            return str(int(math.floor(km + 0.5)))   # nearest integer, halves up

        for raw in (input or "").split("\n"):
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].upper()

            # ---------------------------------------------------------- REGISTER
            if cmd == "REGISTER":
                if len(parts) != 5:
                    output.append("ERROR")
                    continue
                name, lat_s, lon_s, cap_s = parts[1:5]
                coords = parse_coord(lat_s, lon_s)
                try:
                    capacity = int(cap_s)
                except ValueError:
                    capacity = 0
                if name in datacenters or coords is None or capacity <= 0:
                    output.append("ERROR")
                    continue
                datacenters[name] = {"lat": coords[0], "lon": coords[1],
                                     "capacity": capacity, "healthy": True, "load": 0}
                output.append("OK")
                continue

            # ------------------------------------------------------- SET_HEALTHY
            if cmd == "SET_HEALTHY":
                if len(parts) != 3 or parts[1] not in datacenters:
                    output.append("ERROR")
                    continue
                value = parts[2].lower()
                if value not in ("true", "false"):
                    output.append("ERROR")
                    continue
                datacenters[parts[1]]["healthy"] = (value == "true")
                output.append("OK")
                continue

            # ---------------------------------------------------------- DISTANCE
            if cmd == "DISTANCE":
                if len(parts) != 5:
                    output.append("ERROR")
                    continue
                c1 = parse_coord(parts[1], parts[2])
                c2 = parse_coord(parts[3], parts[4])
                if c1 is None or c2 is None:
                    output.append("ERROR")
                    continue
                output.append(display(haversine(c1[0], c1[1], c2[0], c2[1])))
                continue

            # ------------------------------------------------------------- ROUTE
            if cmd == "ROUTE":
                if len(parts) != 3:
                    output.append("ERROR")
                    continue
                coords = parse_coord(parts[1], parts[2])
                if coords is None:
                    output.append("ERROR")
                    continue
                lat, lon = coords
                ranked = sorted(
                    ((haversine(lat, lon, dc["lat"], dc["lon"]), name)
                     for name, dc in datacenters.items() if dc["healthy"]),
                    key=lambda t: (t[0], t[1]),
                )
                if not ranked:
                    output.append("None")
                    continue
                candidates = ",".join(name for _, name in ranked)
                chosen = None
                for dist, name in ranked:
                    dc = datacenters[name]
                    if dc["load"] < dc["capacity"]:
                        dc["load"] += 1
                        chosen = (name, dist)
                        break
                if chosen is None:
                    output.append(f"None {candidates}")
                else:
                    output.append(f"{chosen[0]} {display(chosen[1])} {candidates}")
                continue

            output.append("ERROR")  # unknown command

        return output


# --------------------------------------------------------------------------- #
# Self-tests
# --------------------------------------------------------------------------- #
def _run_tests() -> None:
    f = Solution().solveRequestRoutingSystem

    # Example 1
    assert f("REGISTER us-west 38 -122 100\nREGISTER us-east 41 -74 150\nREGISTER us-west 50 -100 50\n"
             "REGISTER invalid-node 91 0 100\nREGISTER invalid-cap 0 0 0\nSET_HEALTHY us-east false\n"
             "SET_HEALTHY fake-node true") == ["OK", "OK", "ERROR", "ERROR", "ERROR", "OK", "ERROR"]
    # Example 2
    assert f("DISTANCE 38 -122 41 -74\nDISTANCE 0 0 0 0\nDISTANCE 91 0 0 0") == ["4080", "0", "ERROR"]
    # Example 3
    assert f("REGISTER node-A 0 0 1\nREGISTER node-B 0 0 1\nREGISTER node-C 10 10 100\n"
             "SET_HEALTHY node-C false\nROUTE 0 0\nROUTE 0 0\nROUTE 0 0") == \
        ["OK", "OK", "OK", "OK", "node-A 0 node-A,node-B", "node-B 0 node-A,node-B", "None node-A,node-B"]

    # No healthy datacenters -> exactly "None".
    assert f("ROUTE 0 0") == ["None"]
    assert f("REGISTER a 0 0 5\nSET_HEALTHY a FALSE\nROUTE 0 0") == ["OK", "OK", "None"]
    # Case-insensitive health values; anything else is an error.
    assert f("REGISTER a 0 0 5\nSET_HEALTHY a TrUe\nSET_HEALTHY a yes") == ["OK", "OK", "ERROR"]
    # Routing prefers the nearer datacenter; a full one is skipped for the next nearest.
    assert f("REGISTER near 0 1 1\nREGISTER far 0 2 1\nROUTE 0 0\nROUTE 0 0\nROUTE 0 0") == \
        ["OK", "OK", "near 111 near,far", "far 222 near,far", "None near,far"]
    # Re-enabling health brings a datacenter back into the candidate list.
    assert f("REGISTER a 0 0 1\nSET_HEALTHY a false\nROUTE 0 0\nSET_HEALTHY a true\nROUTE 0 0") == \
        ["OK", "OK", "None", "OK", "a 0 a"]
    # Boundary coordinates are valid; just outside is not.
    assert f("REGISTER p 90 180 1\nREGISTER q -90 -180 1\nREGISTER r 0 180.5 1\nREGISTER s -90.1 0 1") == \
        ["OK", "OK", "ERROR", "ERROR"]
    # Negative / non-integer capacity and malformed commands are errors.
    assert f("REGISTER a 0 0 -3\nREGISTER b 0 0 2.5\nREGISTER c 0 0\nFOO bar\nDISTANCE 0 0 0") == \
        ["ERROR", "ERROR", "ERROR", "ERROR", "ERROR"]
    # Antipodal distance is half the Earth's circumference (~20015 km).
    assert f("DISTANCE 0 0 0 180") == ["20015"]
    # Blank lines are skipped; empty input gives no output.
    assert f("REGISTER a 0 0 1\n\nROUTE 0 0\n") == ["OK", "a 0 a"]
    assert f("") == []

    print("All tests passed.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        data = sys.stdin.read()
        if not data.strip():
            _run_tests()
        else:
            print("\n".join(Solution().solveRequestRoutingSystem(data)))
