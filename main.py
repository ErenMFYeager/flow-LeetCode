import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

from flowlauncher import FlowLauncher
from rapidfuzz import fuzz, process
import requests
import json
import time

CACHE_FILE = os.path.join(os.path.dirname(__file__), "problems_cache.json")
CACHE_TTL = 86400  # 24 hours

QUERY = """
query problemsetQuestionList {
  problemsetQuestionList: questionList(
    categorySlug: ""
    limit: 3000
    skip: 0
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
    def query(self, param):
        param = param.lower().strip()
        if not param:
            return [{
                "Title": "Type a problem name or number...",
                "SubTitle": "e.g. lc two sum  or  lc 1",
                "IcoPath": "SearchLeetCode.png"
            }]

        problems = self.get_problems()
        clean_param = param.lstrip("#")

        if clean_param.isdigit():
            matches = [p for p in problems if p["questionFrontendId"] == clean_param]
        else:
            matches = self.fuzzy_search(param, problems)

        return self.build_results(matches)

    def fuzzy_search(self, param, problems, limit=20, threshold=60):
        titles = [p["title"] for p in problems]
        scored = process.extract(
            param, titles, scorer=fuzz.WRatio, limit=limit
        )
        matched = [
            problems[idx] for title, score, idx in scored if score >= threshold
        ]
        return matched

    def build_results(self, matches):
        results = []
        for p in matches[:20]:
            lock = " 🔒" if p["isPaidOnly"] else ""
            results.append({
                "Title": f"{p['questionFrontendId']}. {p['title']} ({p['difficulty']}){lock}",
                "SubTitle": f"Acceptance: {p['acRate']:.1f}%",
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

    def get_problems(self):
        if os.path.exists(CACHE_FILE):
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)

        problems = self.fetch_problems()
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(problems, f)
        return problems

    def fetch_problems(self):
        resp = requests.post(
            "https://leetcode.com/graphql",
            json={"query": QUERY},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"]["problemsetQuestionList"]["questions"]

if __name__ == "__main__":
    LeetCodeSearch()