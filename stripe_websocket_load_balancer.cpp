// Stripe OA: WebSocket Load Balancer (Parts 1-5)  --  C++ port of
// stripe_websocket_load_balancer.py (see that file for the full rule summary).
// https://www.fastprep.io/problems/stripe-websocket-load-balancer
//
// Same algorithm: least-loaded routing through a lazily refreshed (load, target)
// min-heap, object affinity, capacity rejection, duplicate-id re-logging and
// temporary shutdown eviction followed by a reroute in ascending connection-id
// order.  Written to test whether FastPrep's C++ runner avoids the 64 KB per-run
// output cap that stops the Python version on hidden case 9: it does not (same
// verdict, 8/21, runtime 2 ms), so the cap is a judge-wide limit.
#include <algorithm>
#include <cctype>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using namespace std;

class Solution {
public:
    vector<string> routeRequests(int numTargets, int maxConnectionsPerTarget,
                                 const vector<string>& requests) {
        struct Conn { string user; string obj; int target; };
        const long long capacity = maxConnectionsPerTarget;

        vector<int> load(numTargets + 1, 0);              // load[t]: active connections on t
        unordered_map<int, unordered_set<string>> members; // t -> connection ids on t
        unordered_map<string, Conn> conns;                 // connection id -> record
        unordered_map<string, int> affinity;               // object -> target while active
        unordered_map<string, int> objCount;               // object -> active connections
        vector<string> log;

        // Min-heap of (load, target).  Every load change pushes a fresh entry; an entry
        // is trusted only while it still matches load[target].
        using Entry = pair<int, int>;
        priority_queue<Entry, vector<Entry>, greater<Entry>> heap;
        for (int t = 1; t <= numTargets; ++t) heap.emplace(0, t);

        auto leastLoaded = [&](int excluded) -> int {
            while (!heap.empty()) {
                Entry e = heap.top();
                if (e.second == excluded || e.first != load[e.second]) { heap.pop(); continue; }
                return e.second;
            }
            return 0;                                       // nothing eligible
        };

        auto attach = [&](const string& cid, const string& user, const string& obj, int excluded) {
            auto it = conns.find(cid);
            if (it != conns.end()) {                        // Part 4: duplicate active id
                log.push_back(cid + "," + it->second.user + "," + to_string(it->second.target));
                return;
            }
            int target;
            auto af = affinity.find(obj);
            if (af == affinity.end()) {                     // Part 1: least loaded
                target = leastLoaded(excluded);
                if (target == 0) return;
            } else {                                        // Part 3: affinity
                target = af->second;
                if (target == excluded) return;             // defensive; cannot occur
            }
            if (load[target] >= capacity) return;           // Part 4: full -> reject
            conns.emplace(cid, Conn{user, obj, target});
            members[target].insert(cid);
            load[target] += 1;
            heap.emplace(load[target], target);
            affinity[obj] = target;
            objCount[obj] += 1;
            log.push_back(cid + "," + user + "," + to_string(target));
        };

        auto detach = [&](const string& cid) {
            auto it = conns.find(cid);
            if (it == conns.end()) return;                  // Part 2: unknown id is a no-op
            Conn c = it->second;
            conns.erase(it);
            members[c.target].erase(cid);
            load[c.target] -= 1;
            heap.emplace(load[c.target], c.target);
            auto oc = objCount.find(c.obj);
            if (oc != objCount.end() && --(oc->second) == 0) {
                objCount.erase(oc);
                affinity.erase(c.obj);                      // last connection of the object
            }
        };

        auto trim = [](const string& s) {
            size_t a = s.find_first_not_of(" \t\r\n");
            if (a == string::npos) return string();
            size_t b = s.find_last_not_of(" \t\r\n");
            return s.substr(a, b - a + 1);
        };

        for (const string& raw : requests) {
            string line = trim(raw);
            if (line.empty()) continue;
            vector<string> parts;
            for (size_t start = 0;;) {
                size_t pos = line.find(',', start);
                if (pos == string::npos) { parts.push_back(line.substr(start)); break; }
                parts.push_back(line.substr(start, pos - start));
                start = pos + 1;
            }
            string cmd = trim(parts[0]);
            for (char& ch : cmd) ch = static_cast<char>(toupper(static_cast<unsigned char>(ch)));

            if (cmd == "CONNECT") {
                if (parts.size() < 4) continue;
                string obj = parts[3];
                for (size_t i = 4; i < parts.size(); ++i) obj += "," + parts[i];
                attach(parts[1], parts[2], obj, 0);
            } else if (cmd == "DISCONNECT") {
                if (parts.size() >= 2) detach(parts[1]);
            } else if (cmd == "SHUTDOWN") {                 // Part 5
                if (parts.size() < 2) continue;
                int target;
                try { target = stoi(trim(parts[1])); } catch (...) { continue; }
                if (target < 1 || target > numTargets) continue;
                vector<pair<string, pair<string, string>>> evicted;   // cid -> (user, obj)
                auto mit = members.find(target);
                if (mit != members.end()) {
                    for (const string& cid : mit->second) {
                        const Conn& c = conns[cid];
                        evicted.push_back({cid, {c.user, c.obj}});
                    }
                }
                sort(evicted.begin(), evicted.end());       // ascending connection id
                for (const auto& e : evicted) detach(e.first);
                for (const auto& e : evicted) attach(e.first, e.second.first, e.second.second, target);
                heap.emplace(load[target], target);         // available again
            }
        }
        return log;
    }
};
