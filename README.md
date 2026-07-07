# LeetCode Search for Flow Launcher

Search, filter, and open LeetCode problems instantly — right from [Flow Launcher](https://www.flowlauncher.com/), without touching your browser first.

![LeetCode Search](SearchLeetCode.png)

## Features

- 🔍 **Fuzzy search by title** — typos and partial titles still find the right problem (e.g. `two som` → *Two Sum*)
- 🔢 **Search by problem number** — `lc 1` opens *Two Sum* directly
- 🔥 **Daily Challenge** — `lc daily` opens today's LeetCode Daily Challenge
- 🎲 **Random problem** — `lc random` opens a random free problem, great for warm-ups
- 🏷️ **Topic filters** — `lc topic:dp` or `lc tag:graph` surfaces problems by topic
- 🎯 **Difficulty & access filters** — combine `easy`, `medium`, `hard`, `free`, `paid` with any search (e.g. `lc topic:array hard`)
- ⚡ **Local caching** — problem list is cached for 7 days after first index, so searches are instant
- 🔤 **Number-word normalization** — `lc three sum` correctly finds *3Sum*
- 🧩 **Typo-tolerant topics** — `lc topic:dinamic` still finds Dynamic Programming
- 🔄 **Manual refresh** — `lc refresh` rebuilds the local index on demand

## Usage

| Command | Result |
|---|---|
| `lc two sum` | Opens *Two Sum* |
| `lc 1` or `lc #1` | Opens problem #1 |
| `lc daily` | Opens today's Daily Challenge |
| `lc random` | Opens a random free problem |
| `lc topic:dp` | Random sample of Dynamic Programming problems |
| `lc easy` | Random sample of Easy problems |
| `lc topic:graph hard` | Hard-difficulty Graph problems |
| `lc free topic:tree` | Free-to-access Tree problems |
| `lc random hard` | Random Hard problem |
| `lc random topic:graph` | Random problem from the Graph topic |
| `lc topic:dinamic` | Typos in topic names are tolerated (fuzzy-matches to `dynamic-programming`) |
| `lc refresh` | Force a fresh re-index instead of waiting for the 7-day cache to expire |

## First-time setup

On first use, the plugin indexes LeetCode's full problem list (~3,000+ problems) for fast local search. This happens automatically in the background across your first few searches — you'll see an "Indexing... X problems loaded so far" message until it completes (usually 1–3 searches). After that, results are instant, and the cache refreshes automatically every 7 days.

## Installation

**Via Flow Launcher Plugin Store** *(once approved)*:
```
pm install LeetCode Search
```

**Manual install:**
```
pm install https://github.com/ErenMFYeager/flow-LeetCode/releases/latest/download/LeetCodeSearch.zip
```

## Why this plugin?

Built by a competitive programmer, for competitive programmers — jumping between practice problems shouldn't require opening a browser tab and typing out a search every time.

## Contributing

Issues and PRs welcome. Ideas for future features:
- Solved/unsolved status (opt-in, via personal session)
- Company-tag filtering
- Contest reminders

## License

MIT
