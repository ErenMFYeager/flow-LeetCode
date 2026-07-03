import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))

from flowlauncher import FlowLauncher
import requests
import os

QUERY = """
query problemsetQuestionList {
  problemsetQuestionList: questionList(
    categorySlug: ""
    limit: 3000
    skip: 0
    filters: {}
  ) {
    questions: data {
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
                "Title": "Type a problem name...",
                "SubTitle": "e.g. lc two sum",
                "IcoPath": "SearchLeetCode.png"
            }]

        problems = self.fetch_problems()
        matches = [p for p in problems if param in p["title"].lower()]

        results = []
        for p in matches[:20]:
            lock = " 🔒" if p["isPaidOnly"] else ""
            results.append({
                "Title": f"{p['title']} ({p['difficulty']}){lock}",
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
                "SubTitle": f"No match for '{param}'",
                "IcoPath": "SearchLeetCode.png"
            })

        return results

    def open_url(self, url):
        os.startfile(url)

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