import sys
import os
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

from flowlauncher import FlowLauncher
from rapidfuzz import fuzz, process
import requests
import json
import time

CACHE_FILE = os.path.join(os.path.dirname(__file__), "problems_cache.json")
CACHE_TTL = 86400

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

class LeetCodeSearch(FlowLauncher):
    _fetching = False

    def query(self, param):
        param = param.lower().strip()
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

    def fuzzy_search(self, param, problems, limit=20, threshold=55):
        exact_matches = [p for p in problems if param in p["title"].lower()]
        if exact_matches:
            return exact_matches[:limit]
        
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
                    f.write(f"Error at skip={skip}: {e}\n")
                break

            if not data:
                break

            all_problems.extend(data)
            skip += batch_size

            if len(data) < batch_size:
                break

            time.sleep(0.3)

        return all_problems

if __name__ == "__main__":
    LeetCodeSearch()