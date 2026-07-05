import json
import os
import random
import sys
import threading
import time
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

import requests
from flowlauncher import FlowLauncher
from rapidfuzz import fuzz, process

CACHE_FILE = os.path.join(os.path.dirname(__file__), "problems_cache.json")
CACHE_TTL = 604800

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


NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10"
}

class LeetCodeSearch(FlowLauncher):
    _fetching = False

    def query(self, param):
        try:
            param = param.lower().strip()
            if param == "daily":
                return self.handle_daily()
            
            problems = self.load_cache_only()

            if problems is None:
                if not LeetCodeSearch._fetching:
                    LeetCodeSearch._fetching = True
                    threading.Thread(target=self.background_fetch, daemon=True).start()
                
                return [{
                    "Title": "Indexing LeetCode problems for the first time...",
                    "SubTitle": "This takes ~20-30 seconds. Feel free to try searching again shortly!",
                    "IcoPath": "SearchLeetCode.png"
                }]
            
            if param == "random":
                return self.handle_random(problems)

            if not param:
                return [{
                    "Title": "Type a problem name or number...",
                    "SubTitle": "e.g. lc two sum  or  lc 1",
                    "IcoPath": "SearchLeetCode.png"
                }]

            clean_param = param.lstrip("#")

            if clean_param.isdigit():
                matches = [p for p in problems if p["questionFrontendId"] == clean_param]
            else:
                matches = self.fuzzy_search(param, problems)

            return self.build_results(matches)
        
        except Exception as e:
            # If ANYTHING crashes during the search, show it directly in Flow Launcher!
            error_msg = str(e)
            with open(os.path.join(os.path.dirname(__file__), "error.log"), "a") as f:
                f.write(traceback.format_exc() + "\n")
            return [{
                "Title": "Plugin Crashed!",
                "SubTitle": f"Error: {error_msg}",
                "IcoPath": "SearchLeetCode.png"
            }]

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

        scored = process.extract(
            param, titles, scorer=fuzz.ratio, limit=limit * 3
        )

        scored.sort(key=lambda x: x[1], reverse=True)
        matched = [
            problems[idx] for (title, score, idx) in scored if score >= threshold
        ][:limit]

        return matched

    def build_results(self, matches):
        results = []
        for p in matches[:20]:
            lock = " 🔒" if p["isPaidOnly"] else ""
            
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

    def background_fetch(self):
        try:
            problems = self.fetch_problems()
            if problems:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(problems, f)
        finally:
            LeetCodeSearch._fetching = False

    def fetch_problems(self):
        all_problems = []
        skip = 0
        batch_size = 100

        while True:
            try:
                resp = requests.post(
                    "https://leetcode.com/graphql",
                    json={
                        "query": QUERY,
                        "variables": {"skip": skip, "limit": batch_size}
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://leetcode.com",
                        "User-Agent": "Mozilla/5.0"
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                payload = resp.json()

                if "errors" in payload:
                    raise Exception(f"GraphQL error: {payload['errors']}")

                data = payload["data"]["problemsetQuestionList"]["questions"]
            except Exception as e:
                with open(os.path.join(os.path.dirname(__file__), "error.log"), "a") as f:
                    f.write(f"Network error at skip={skip}: {e}\n")
                break

            if not data:
                break

            all_problems.extend(data)
            skip += batch_size

            if len(data) < batch_size:
                break

            time.sleep(0.3)

        return all_problems
    
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
            lock = " 🔒" if q["isPaidOnly"] else ""
            ac_rate = f"{q['acRate']:.1f}%" if q.get("acRate") is not None else "N/A"

            return [{
                "Title": f"🔥 Today's Daily: {q['questionFrontendId']}. {q['title']} ({q['difficulty']}){lock}",
                "SubTitle": f"Acceptance: {ac_rate} — Press Enter to open",
                "IcoPath": "SearchLeetCode.png",
                "JsonRPCAction": {
                    "method": "open_url",
                    "parameters": [f"https://leetcode.com{daily['link']}"]
                }
            }]
        except Exception as e:
            with open(os.path.join(os.path.dirname(__file__), "error.log"), "a") as f:
                f.write(f"Daily fetch error: {e}\n")
            return [{
                "Title": "Couldn't fetch today's daily challenge",
                "SubTitle": "Check your connection and try again",
                "IcoPath": "SearchLeetCode.png"
            }]

    def handle_random(self, problems):
        free_problems = [p for p in problems if not p["isPaidOnly"]]
        pool = free_problems if free_problems else problems
        p = random.choice(pool)

        lock = " 🔒" if p["isPaidOnly"] else ""
        ac_rate = f"{p['acRate']:.1f}%" if p.get("acRate") is not None else "N/A"

        return [{
            "Title": f"🎲 {p['questionFrontendId']}. {p['title']} ({p['difficulty']}){lock}",
            "SubTitle": f"Acceptance: {ac_rate} — Press Enter to open, search 'lc random' again for another",
            "IcoPath": "SearchLeetCode.png",
            "JsonRPCAction": {
                "method": "open_url",
                "parameters": [f"https://leetcode.com/problems/{p['titleSlug']}/"]
            }
        }]

if __name__ == "__main__":
    LeetCodeSearch()