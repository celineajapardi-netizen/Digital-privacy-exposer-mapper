# SHADOW

*How harmless pieces of information become revealing when connected.*

**Live demo:** <https://digital-privacy-exposer-mapper.vercel.app>

A username, a school, a hobby and a city are each fairly harmless on their own. Together they
can tell a stranger where a person will be and when. SHADOW is a threat-modelling tool that
makes this visible: you tick which kinds of information about you are public, it draws them as
a network, and it shows how your exposure changes as pieces are added or removed.

Nothing personal is analysed. The app reasons only about *which categories* are public; any
values typed in are labels on the graph and never leave the browser.

## What the app does

1. **Add information.** Choose from twelve kinds of information a person might share online:
   username, real name, birthday, contact details, school, city, neighbourhood, hobby, weekly
   schedule, public profile, photos, tagged friends.
2. **See the graph.** Each piece is a node. Each line is a relation: a way that one piece leads
   to another, with a reason ("a username is the search key that finds the profile").
3. **Read the exposure.** A score from 0 to 100 and a level (Low, Moderate, High, Severe), with
   an explanation: how many pieces are linked, which combinations are more revealing together
   than apart, and whether a stranger could trace a path from an online handle to a real place.
4. **Experiment.** The app ranks what would happen if any single piece were removed or added.
   Pin the current state as "before", change something, and compare.

The sequence the app is built around:

| Public information | Exposure | What changed |
|---|---|---|
| School + City | **Low (3)** | Two facts, one weak link. |
| + Weekly schedule | **Moderate (14)** | City narrows the map, school fixes the place, schedule fixes the time. |
| + Username | **High (21)** | Someone who knows only the username can now work out where you will be and when. |
| + Public profile | **High (27)** | A trace appears: Username → Public profile → School. |

## How it works

SHADOW does not look anything up. It reasons over a written-down threat model, stored as data
so that every rule can be read and argued with.

**Nodes** ([`shadow/catalogue.py`](shadow/catalogue.py)). Each kind of information has a category
(identity, location, routine, social) and a sensitivity from 0 to 3 for how revealing it is on
its own. A hobby is 0; a phone number is 3.

**Edges** (`RELATIONS` in [`shadow/rules.py`](shadow/rules.py)). Pairs where one kind of
information leads to another, with a strength from 1 to 3 and a one-line reason. An edge is
active only when both ends are public.

**Patterns** (`COMBINATIONS` in [`shadow/rules.py`](shadow/rules.py)). Sets of information that
reveal something none of them reveals alone, each with a severity and an explanation:

```
school + schedule               → Predictable routine                    (medium)
username + school               → Identity correlation                   (medium)
username + school + schedule    → Strong chain: handle → school → routine (high)
city + school + schedule        → Physical location at specific times    (high)
real_name + birthday + city     → Identity triangulation                 (high)
```

Two rules keep the findings honest:

- **Only maximal patterns are reported.** When username, school and schedule are all public,
  the two smaller patterns inside the "strong chain" are absorbed by it, so one fact is not
  counted three times.
- **A superset is never less severe than its subset.** This is an invariant of the rule set,
  checked by a test, and it guarantees that sharing more can never lower the score.

Two graph algorithms, written from scratch in [`shadow/graph.py`](shadow/graph.py), run on top:

- **Breadth-first search** finds the *trace*: the shortest path from something a stranger might
  know first (username, profile, name) to a physical place (neighbourhood, school, city).
- **Connected components** detect when public information is still in separate clusters that
  nobody has joined up, which is often the most reassuring thing on the page.

### The score

```
raw   = Σ sensitivity of each item            (0–3)
      + Σ strength of each active edge        (1–3)
      + Σ weight of each maximal pattern      (low 3, medium 6, high 10)
      + 3 if a trace exists

score = 100 × raw / raw(everything public)
```

Pattern weights are deliberately larger than item sensitivities, so combinations dominate.
A test checks that city + school + schedule together score more than double the three alone.

Every term can only grow when an item is added, so exposure is monotonic. The test suite
verifies this exhaustively: for all 4,096 subsets of the catalogue and every item that could
be added to each, the score never decreases. The what-if panel is exact, not estimated: the
engine recomputes the score with each item removed and each absent item added, then ranks
the differences.

## Architecture

```
shadow/
  catalogue.py   information kinds (nodes) and their sensitivity
  rules.py       relations (edges) and risky patterns
  graph.py       Graph: adjacency list, BFS shortest path, connected components
  engine.py      analyse(items) → graph, findings, trace, score, what-if
  storage.py     SQLite store for saved scenarios
  cli.py         terminal interface
app.py           Flask API: /api/catalogue, /api/analyse, /api/scenarios
static/          single page: D3 force-directed graph and exposure panel
tests/           17 pytest tests
```

The browser never makes a decision. It sends the set of public keys to `/api/analyse` and
draws the result, so the web page, the command line and the tests all run the same engine.

## Running it

```bash
pip install -r requirements.txt
python app.py            # open http://127.0.0.1:5000
python -m pytest tests   # run the tests
python -m shadow.cli school city schedule   # same engine, in the terminal
```

Saved scenarios are kept in `shadow.db`, an SQLite file next to `app.py`. On the hosted demo
the disk is read-only, so scenarios fall back to a temporary folder and do not persist.

## Next steps

- **Editable rules.** The threat model is data; a rules editor would let a class debate whether
  `photos + city` deserves "medium", which is the conversation the app is meant to start.
- **Weighted trace.** The trace counts hops; using edge strength as cost would prefer the path
  a stranger would find easiest.
- **Minimal fix.** Ranking single changes is cheap. Finding the smallest set of items to remove
  to reach "Low" is a set-cover problem worth attempting.

## Limitations

- The rule weights are my judgement, not measured data. The score is a model for comparing
  before and after, not a prediction of harm.
- The scale is relative: 100 means everything in the catalogue is public. Real footprints
  include things the catalogue does not model, such as location tags and other people's posts.
- The catalogue is small on purpose. Twelve well-explained kinds are more useful than forty
  vague ones when the point is that a reader can follow every rule.
