import json
import os
import random
import subprocess
import sys
import time
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

import requests
from flowlauncher import FlowLauncher
from rapidfuzz import fuzz, process

CACHE_FILE = os.path.join(os.path.dirname(__file__), "problems_cache.json")
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "fetch_progress.json")
LOCK_FILE = os.path.join(os.path.dirname(__file__), "indexing.lock")
LOG_FILE = os.path.join(os.path.dirname(__file__), "error.log")
CACHE_TTL = 604800  # 7 days

HEARTBEAT_STALE_SECONDS = 15

QUERY = """
query problemsetQuestionList($skip: Int, $limit: Int) {
  problemsetQuestionList: questionList(
    categorySlug: ""
    limit: $limit
    skip: $skip
    filters: {}
  ) {
    questions: data {
      questionFrontendId
      title
      titleSlug
      difficulty
      acRate
      isPaidOnly
      topicTags {
        name
        slug
      }
    }
  }
}
"""

DAILY_QUERY = """
query questionOfToday {
  activeDailyCodingChallengeQuestion {
    date
    link
    question {
      questionFrontendId
      title
      titleSlug
      difficulty
      acRate
      isPaidOnly
    }
  }
}
"""

DIFFICULTIES = {"easy", "medium", "hard"}

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10"
}

TOPIC_ALIASES = {
    "dp": "dynamic-programming",
    "graph": "graph",
    "greedy": "greedy",
    "tree": "tree",
    "array": "array",
    "string": "string",
    "hashmap": "hash-table",
    "hash": "hash-table",
    "stack": "stack",
    "queue": "queue",
    "heap": "heap-priority-queue",
    "binary search": "binary-search",
    "binary": "binary-search",
    "bfs": "breadth-first-search",
    "dfs": "depth-first-search",
    "linked list": "linked-list",
    "backtracking": "backtracking",
    "recursion": "backtracking",
    "sliding window": "sliding-window",
    "two pointers": "two-pointers",
    "bit": "bit-manipulation",
    "math": "math",
    "sort": "sorting",
    "trie": "trie",
}


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%X')} - {msg}\n")
    except Exception:
        pass


class LeetCodeSearch(FlowLauncher):

    def query(self, param):
        try:
            param = param.lower().strip()

            if param == "daily":
                return self.handle_daily()

            if param == "refresh":
                return self.force_refresh()

            problems = self.load_cache_only()

            if problems is None:
                return self.continue_indexing()

            if not param:
                return [{
                    "Title": "Type a problem name or number...",
                    "SubTitle": "e.g. lc two sum | lc 1 | lc daily | lc random | lc topic:dp | lc refresh",
                    "IcoPath": "SearchLeetCode.png"
                }]

            clean_param = param.lstrip("#")
            tokens = clean_param.split()
            tokens, filters = self.extract_filters(tokens)
            clean_param = " ".join(tokens).strip()

            if clean_param == "random" or (clean_param.startswith("random ") or clean_param.endswith(" random")):
                # allow "random" combined with difficulty/paid/free/topic filters
                remaining = [t for t in clean_param.split() if t != "random"]
                if remaining and (remaining[0].startswith("topic:") or remaining[0].startswith("tag:")):
                    topic_query = remaining[0].split(":", 1)[1].strip()
                    pool = self.filter_by_topic(topic_query, problems, apply_limit=False)
                else:
                    pool = problems
                pool = self.apply_filters(pool, filters)
                return self.handle_random(pool)

            if clean_param.startswith("topic:") or clean_param.startswith("tag:"):
                topic_query = clean_param.split(":", 1)[1].strip()
                matches = self.filter_by_topic(topic_query, problems, apply_limit=False)
                matches = self.apply_filters(matches, filters)
                random.shuffle(matches)
                return self.build_results(matches)

            if clean_param.isdigit():
                matches = [p for p in problems if p["questionFrontendId"] == clean_param]
            elif not clean_param:
                # e.g. "lc medium" alone with no title/topic — just filter the whole set
                matches = self.apply_filters(problems, filters)
                random.shuffle(matches)
            else:
                matches = self.fuzzy_search(clean_param, problems)
                matches = self.apply_filters(matches, filters)

            return self.build_results(matches)

        except Exception:
            log("QUERY CRASHED:\n" + traceback.format_exc())
            return [{
                "Title": "Plugin crashed — check error.log",
                "SubTitle": str(sys.exc_info()[1]),
                "IcoPath": "SearchLeetCode.png"
            }]

    # ---------- Indexing ----------
    #
    # A fresh Python process runs per query, so an in-process thread dies the
    # instant query() returns. Instead: spawn a genuinely detached OS
    # subprocess (this same script, run with --index-worker) that keeps
    # fetching independently of Flow Launcher's process lifecycle, writing
    # progress to PROGRESS_FILE as it goes. Each query() call just checks
    # that file — it never blocks on the network itself.

    def continue_indexing(self):
        if not self._worker_alive():
            self._spawn_worker()

        count = self._progress_count()

        return [{
            "Title": f"Indexing... {count} problems loaded so far",
            "SubTitle": "Running in the background — check back in a bit, no need to keep typing",
            "IcoPath": "SearchLeetCode.png"
        }]

    def _worker_alive(self):
        if not os.path.exists(LOCK_FILE):
            return False
        try:
            age = time.time() - os.path.getmtime(LOCK_FILE)
        except Exception:
            return False
        return age < HEARTBEAT_STALE_SECONDS

    def _progress_count(self):
        if not os.path.exists(PROGRESS_FILE):
            return 0
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return len(json.load(f).get("problems", []))
        except Exception:
            return 0

    def _spawn_worker(self):
        try:
            with open(LOCK_FILE, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except Exception as e:
            log(f"Couldn't write lock file: {e}")
            return

        script_path = os.path.abspath(__file__)
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "cwd": os.path.dirname(script_path),
            "close_fds": True,
        }
        if os.name == "nt":
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True

        try:
            subprocess.Popen([sys.executable, script_path, "--index-worker"], **kwargs)
            log("Spawned detached indexing worker")
        except Exception as e:
            log(f"Failed to spawn indexing worker: {e}")


    def force_refresh(self):
        """lc refresh — wipes the cache and kicks off re-indexing immediately."""
        for f in (CACHE_FILE, PROGRESS_FILE, LOCK_FILE):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    log(f"force_refresh couldn't remove {f}: {e}")
        return self.continue_indexing()

    def load_cache_only(self):
        if os.path.exists(CACHE_FILE):
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    return None
        return None

    # ---------- Search ----------

    def normalize_numbers(self, text):
        words = text.split()
        converted = [NUMBER_WORDS.get(w, w) for w in words]
        joined_with_space = " ".join(converted)
        joined_no_space = "".join(converted)
        return joined_with_space, joined_no_space

    def fuzzy_search(self, param, problems, limit=20, threshold=55):
        exact_matches = [p for p in problems if param in p["title"].lower()]
        if exact_matches:
            return exact_matches[:limit]

        normalized_space, normalized_nospace = self.normalize_numbers(param)
        for candidate in {normalized_space, normalized_nospace}:
            if candidate != param:
                normalized_matches = [p for p in problems if candidate in p["title"].lower()]
                if normalized_matches:
                    return normalized_matches[:limit]

        titles = [p["title"] for p in problems]
        scored = process.extract(param, titles, scorer=fuzz.ratio, limit=limit * 3)
        scored.sort(key=lambda x: x[1], reverse=True)
        matched = [problems[idx] for (title, score, idx) in scored if score >= threshold][:limit]
        return matched

    def filter_by_topic(self, topic_query, problems, apply_limit=True):
        slug = TOPIC_ALIASES.get(topic_query, topic_query.replace(" ", "-"))

        # exact slug match first
        matches = [
            p for p in problems
            if any(tag["slug"] == slug for tag in p.get("topicTags", []))
        ]

        # fall back to fuzzy matching against known topic slugs (typo tolerance,
        # e.g. "topic:dinamic" -> dynamic-programming) if nothing matched exactly
        if not matches:
            all_slugs = {tag["slug"] for p in problems for tag in p.get("topicTags", [])}
            all_slugs.update(TOPIC_ALIASES.values())
            best = process.extractOne(slug, list(all_slugs), scorer=fuzz.partial_ratio)
            if best and best[1] >= 80:
                fuzzy_slug = best[0]
                matches = [
                    p for p in problems
                    if any(tag["slug"] == fuzzy_slug for tag in p.get("topicTags", []))
                ]

        if apply_limit:
            random.shuffle(matches)
            return matches[:20]
        return matches

    def build_results(self, matches):
        results = []
        for p in matches[:20]:
            lock = " \U0001F512" if p["isPaidOnly"] else ""
            ac_rate_val = p.get('acRate')
            ac_rate_str = f"{ac_rate_val:.1f}%" if ac_rate_val is not None else "N/A"

            results.append({
                "Title": f"{p['questionFrontendId']}. {p['title']} ({p['difficulty']}){lock}",
                "SubTitle": f"Acceptance: {ac_rate_str}",
                "IcoPath": "SearchLeetCode.png",
                "JsonRPCAction": {
                    "method": "open_url",
                    "parameters": [f"https://leetcode.com/problems/{p['titleSlug']}/"]
                }
            })
        if not results:
            results.append({
                "Title": "No problems found",
                "SubTitle": "Try a different search term",
                "IcoPath": "SearchLeetCode.png"
            })
        return results

    def open_url(self, url):
        os.startfile(url)

    # ---------- Daily ----------

    def fetch_daily(self):
        resp = requests.post(
            "https://leetcode.com/graphql",
            json={"query": DAILY_QUERY},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://leetcode.com",
                "User-Agent": "Mozilla/5.0"
            },
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload["data"]["activeDailyCodingChallengeQuestion"]

    def handle_daily(self):
        try:
            daily = self.fetch_daily()
            q = daily["question"]
            lock = " \U0001F512" if q["isPaidOnly"] else ""
            ac_rate = f"{q['acRate']:.1f}%" if q.get("acRate") is not None else "N/A"

            return [{
                "Title": f"\U0001F525 Today's Daily: {q['questionFrontendId']}. {q['title']} ({q['difficulty']}){lock}",
                "SubTitle": f"Acceptance: {ac_rate} — Press Enter to open",
                "IcoPath": "SearchLeetCode.png",
                "JsonRPCAction": {
                    "method": "open_url",
                    "parameters": [f"https://leetcode.com{daily['link']}"]
                }
            }]
        except Exception as e:
            log(f"Daily fetch error: {e}")
            return [{
                "Title": "Couldn't fetch today's daily challenge",
                "SubTitle": "Check your connection and try again",
                "IcoPath": "SearchLeetCode.png"
            }]

    # ---------- Random ----------

    def handle_random(self, problems):
        if not problems:
            return [{
                "Title": "No problems match those filters",
                "SubTitle": "Try loosening the difficulty/topic/paid filters",
                "IcoPath": "SearchLeetCode.png"
            }]

        free_problems = [p for p in problems if not p["isPaidOnly"]]
        pool = free_problems if free_problems else problems
        p = random.choice(pool)

        lock = " \U0001F512" if p["isPaidOnly"] else ""
        ac_rate = f"{p['acRate']:.1f}%" if p.get("acRate") is not None else "N/A"

        return [{
            "Title": f"\U0001F3B2 {p['questionFrontendId']}. {p['title']} ({p['difficulty']}){lock}",
            "SubTitle": f"Acceptance: {ac_rate} — Press Enter to open, search 'lc random' again for another",
            "IcoPath": "SearchLeetCode.png",
            "JsonRPCAction": {
                "method": "open_url",
                "parameters": [f"https://leetcode.com/problems/{p['titleSlug']}/"]
            }
        }]

    def extract_filters(self, tokens):
        """Pulls out difficulty/paid/free keywords, returns (remaining_tokens, filters_dict)"""
        filters = {"difficulty": None, "paid": None}
        remaining = []
        for t in tokens:
            if t in DIFFICULTIES:
                filters["difficulty"] = t
            elif t == "paid":
                filters["paid"] = True
            elif t == "free":
                filters["paid"] = False
            else:
                remaining.append(t)
        return remaining, filters

    def apply_filters(self, problems, filters):
        result = problems
        if filters["difficulty"]:
            result = [p for p in result if p["difficulty"].lower() == filters["difficulty"]]
        if filters["paid"] is True:
            result = [p for p in result if p["isPaidOnly"]]
        elif filters["paid"] is False:
            result = [p for p in result if not p["isPaidOnly"]]
        return result


def run_index_worker():
    """Entry point for the detached background process (invoked as
    `python main.py --index-worker`). Fetches the whole problem list,
    resuming from PROGRESS_FILE if a previous run left one, and writes a
    heartbeat to LOCK_FILE after every batch so query() calls know it's
    still alive and don't spawn a duplicate worker."""
    skip = 0
    problems = []
    batch_size = 100

    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                skip = state.get("skip", 0)
                problems = state.get("problems", [])
        except Exception:
            skip = 0
            problems = []

    while True:
        try:
            resp = requests.post(
                "https://leetcode.com/graphql",
                json={"query": QUERY, "variables": {"skip": skip, "limit": batch_size}},
                headers={
                    "Content-Type": "application/json",
                    "Referer": "https://leetcode.com",
                    "User-Agent": "Mozilla/5.0"
                },
                timeout=8,
            )
            resp.raise_for_status()
            payload = resp.json()
            if "errors" in payload:
                raise Exception(f"GraphQL error: {payload['errors']}")
            data = payload["data"]["problemsetQuestionList"]["questions"]
        except Exception as e:
            log(f"Indexing worker error at skip={skip}: {e}")
            break

        if not data:
            break

        problems.extend(data)
        skip += batch_size

        # Persist progress and refresh the heartbeat after every batch, so a
        # concurrently-running query() sees the count grow and knows the
        # worker is still alive.
        try:
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump({"skip": skip, "problems": problems}, f)
            with open(LOCK_FILE, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except Exception as e:
            log(f"Indexing worker couldn't persist progress: {e}")

        if len(data) < batch_size:
            break

    if problems:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(problems, f)
        log(f"Indexing worker complete, {len(problems)} problems")
    else:
        log("Indexing worker finished with no problems loaded")

    for f in (PROGRESS_FILE, LOCK_FILE):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--index-worker":
        run_index_worker()
    else:
        LeetCodeSearch()