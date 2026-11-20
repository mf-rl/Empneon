# Recall latency benchmark and FTS5 go/no-go

Reproduce with `python scripts/bench_recall.py` (add `--json out.json` for raw numbers). The script seeds
a throwaway database with synthetic `confirmed_interaction` events and times each recall path. It never
touches a real save.

## Method

- 20 agents (the SocietyBench ring size). One "hot" pair holds 5% of all events; the "cold" pair is an
  ordinary pair. Each event carries a 384-dimension vector, like the Sims 4 adapter's hashed vectors.
- Sizes: 1,000 / 10,000 / 50,000 / 100,000 events (databases of 2.6 / 23 / 114 / 228 MB).
- Three queries: `rare` (one matching topic), `common` (generic recall), `multi` (several terms).
- 1 warm-up call plus 20 timed calls per measurement, single process, warm page cache, fixed seed
  (`20260720`).
- Machine: Ryzen 7 4800H (16 threads), WSL2 on Windows, Python 3.11, SQLite via the standard library,
  database on the Linux filesystem. The WSL VM saw about 4 GB RAM, not the machine's 16 GB.

## Results (p50 ms, hot pair)

| Events | `recall_event_rows` (rare / common / multi) | FTS5 prototype (rare / common / multi) | `recalled_memories` (end to end, common) | `get_for_agent` limit=100 | vector search k=10 |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 3.2 / 3.5 / 3.9 | 0.2 / 0.6 / 1.0 | 5.2 | 0.8 | 0.9 |
| 10,000 | 21 / 23 / 29 | 3.0 / 8.7 / 10 | 30 | 7.0 | 8.7 |
| 50,000 | 91 / 105 / 122 | 15 / 43 / 50 | 118 | 34 | 48 |
| 100,000 | 180 / 203 / 252 | 28 / 80 / 97 | 210 | 66 | 85 |

p95 stays within about 10% of p50 in every row (full tables come from the script). Cold pairs behave the
same, because the current query scans every event row (`json_extract` on `description`) regardless of pair
size: cost grows linearly, roughly 1.8 to 2.5 ms per 1,000 events.

## Findings

1. The current pair-history scan costs about 2 ms per 1,000 events. End-to-end `recalled_memories`
   adds only 5 to 10 ms of Python ranking on top at every size.
2. An FTS5 prototype is 2.5x to 6x faster on the SQL step (more for rare terms, less for generic queries).
   It is not a free win: the build is cheap (0.8 s at 100k) but it needs a schema migration, triggers or
   explicit sync on insert and delete, and a tokenizer decision.
3. Unbounded `EpisodicMemoryStore.get_for_agent` and brute-force vector search also scale linearly
   (about 160 ms and 85 to 90 ms at 100k). Neither is made faster by FTS5.

## Recommendation: no-go for now

Do not build hybrid recall on latency grounds yet. Context: the only published provider latency is a
p50 of about 18.8 s per call (see `adapters/thesims4/docs/benchmark-results.md`), so recall at 10,000
events (about 30 ms) is roughly 0.2% of a request and invisible to a player. The cost only becomes
noticeable (above ~100 ms) past roughly 50,000 events.

Close or defer issue #40 unless one of these holds, then re-run this script on the real hardware:

- real saves reach 50,000 or more `events` rows (I did not measure typical save sizes; check a long-lived
  save with `SELECT count(*) FROM events`);
- recall moves onto a latency-critical path (for example, per-frame autonomy);
- hybrid recall is wanted for relevance (keyword plus vector ranking), which is a quality argument this
  benchmark does not address.

If latency does become a problem, try a cheaper fix first: the scan filters on `json_extract` of speaker and
listener with no index, so an indexed pair column or expression index may remove the full-table scan without
FTS5. I did not benchmark that.

## Limits of this evidence

- Synthetic text and uniformly random vectors; real distributions and term frequencies differ.
- The FTS5 prototype indexes only `message` and `dialogue`, uses `bm25` ordering, and omits the
  first/latest boundary-row union the Sims 4 query adds, so its advantage is somewhat overstated.
- Warm cache, single process, no concurrent writes, one machine, one run. Windows-native (non-WSL) I/O
  was not measured.
