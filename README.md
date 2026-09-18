# SHADOW

*How can seemingly harmless information become risky when connected?*

Most online-safety advice is a list of things not to share. SHADOW asks a different question:

> **A username, a school, a hobby and a city each seem harmless on their own.
> What do they reveal once someone joins them up?**

The app lets you tick which *kinds* of information about you are public, draws them as a
network, and shows how your exposure changes as pieces are added or removed. Nothing you type
is analysed or sent anywhere — SHADOW only reasons about which categories are public, and the
values you type are just labels on the graph.

```
                 Username
                    │
                    ↓
               Public profile
                    │
              ┌─────┴─────┐
              ↓           ↓
           School       Hobby
              │           │
              └─────┬─────┘
                    ↓
                Schedule
                    │
                    ↓
                 Location
```

---

## Contents

- [What it does](#what-it-does)
- [How the threat model works](#how-the-threat-model-works)
- [The exposure score](#the-exposure-score)
- [Running it](#running-it)
- [Project layout](#project-layout)
- [Tests](#tests)
- [What I'd do next](#what-id-do-next)
- [Limitations and honesty notes](#limitations-and-honesty-notes)

---

## What it does

1. **Add information.** Tick the kinds of information someone could find about you: username,
   real name, school, city, weekly schedule, public profile, photos, tagged friends, and so on.
2. **See your information graph.** Every piece is a node. Every line is a *relation* — a way
   that one piece leads to another ("a username is the search key that finds the profile").
3. **Read your exposure.** A score from 0 to 100 with a level (Low / Moderate / High / Severe)
   and, more importantly, *why*: how many pieces are connected, how many relationships were
   found, and which **combinations** are more revealing together than apart.
4. **Experiment.** The app already knows what would happen if you removed or added any single
   piece, and ranks the changes. Pin the current state as "before", change something, and
   watch the score and the graph move.

The demo story the app is built around:

| Public information | Exposure | What changed |
|---|---|---|
| School + City | **Low (3)** | Two facts, one weak link. |
| + Weekly schedule | **Moderate (14)** | "City narrows the map, school fixes the place, schedule fixes the time." |
| + Username | **High (21)** | "Someone who only knows your username could work out where you will be and when." |
| + Public profile | **High (27)** | A *trace* appears: Username → Public profile → School. A stranger can now walk from a handle to a real place. |

## How the threat model works

Nothing is hacked or looked up. The "cybersecurity" is a **written-down threat model** that the
program reasons over — the same idea as threat modelling in real security work, scaled down to a
teenager's digital footprint.

There are three ingredients, each in its own file so it can be read and argued with:

**Nodes — [`shadow/catalogue.py`](shadow/catalogue.py).** Twelve kinds of information, each
with a category (identity / location / routine / social) and a *sensitivity* from 0 to 3 for
how revealing it is **on its own**. A hobby is 0. A phone number is 3.

**Edges — `RELATIONS` in [`shadow/rules.py`](shadow/rules.py).** Pairs of information kinds
where one leads to the other, with a strength from 1 to 3 and a one-line reason. For example
`school ↔ schedule` (3, "School fixes a large part of the weekly routine"). Only edges whose
both ends are public appear in the graph.

**Risky patterns — `COMBINATIONS` in [`shadow/rules.py`](shadow/rules.py).** Sets of information
kinds that reveal something none of them reveals alone, with a severity and an explanation:

```
school + schedule                → Predictable routine                   (medium)
city + schedule                  → Location at known times               (medium)
username + school                → Identity correlation                  (medium)
username + school + schedule     → Strong chain: handle → school → routine (high)
city + school + schedule         → Physical location at specific times   (high)
real_name + birthday + city      → Identity triangulation                (high)
```

Two algorithmic details make the findings honest rather than noisy:

- **Only maximal patterns are reported.** With username + school + schedule public, the two
  smaller patterns inside the "strong chain" are swallowed by it, so one fact is not counted
  three times. (`matching_combinations` in `rules.py`.)
- **Supersets are never less severe than their subsets.** This is an invariant of the rule
  set, checked by a test, and it is what guarantees the score can never *drop* when you share
  more.

On top of the rules, the engine runs two graph algorithms from
[`shadow/graph.py`](shadow/graph.py), written from scratch:

- **Breadth-first search** to find the **trace**: the shortest path from something a stranger
  might know first (username, profile, name…) to a physical place (neighbourhood, school,
  city). The UI animates it as a dashed white line.
- **Connected components**, to point out when your public information is still in separate
  clusters that nobody has joined yet — often the most reassuring thing on the page.

## The exposure score

```
raw  =  Σ sensitivity of each item          (0-3 each, small)
     +  Σ strength of each active edge      (1-3 each)
     +  Σ weight of each maximal pattern    (low 3 / medium 6 / high 10 — the big part)
     +  3 if a trace exists

score = 100 × raw / raw(everything public)
```

The weights are chosen so that **combinations dominate** — that is the thesis of the project.
`test_combinations_dominate_individual_points` checks that city + school + schedule together
score more than double the sum of the three alone.

Because every term can only grow when an item is added, exposure is monotonic. The test suite
proves this exhaustively: for all 4 096 subsets of the catalogue and every item that could be
added to each, the score never decreases.

The "what if" panel is not a heuristic. For the current selection the engine recomputes the
score with each item removed and with each absent item added, and ranks the differences.

## Running it

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>. The web app is a small Flask server around the engine plus
a single page that draws the graph with D3. Saved scenarios go into `shadow.db`, an SQLite
file created next to `app.py`.

The same engine runs in the terminal:

```bash
python -m shadow.cli school city schedule
python -m shadow.cli --list
python -m shadow.cli --json username public_profile school
```

## Project layout

```
shadow/
  catalogue.py   the kinds of information (nodes) and their sensitivity
  rules.py       relations (edges) and risky combinations (patterns)
  graph.py       Graph class: adjacency list, BFS shortest path, components, density
  engine.py      analyse(items) -> Analysis: graph, findings, trace, score, what-if
  storage.py     SQLite store for saved scenarios
  cli.py         terminal interface
app.py           Flask API: /api/catalogue, /api/analyse, /api/scenarios
static/
  index.html     the page
  style.css      dark theme, category and level colours as CSS variables
  app.js         D3 force graph + exposure panel; no analysis happens here
tests/
  test_shadow.py
```

The split matters: the browser never decides anything. It sends the set of public keys to
`/api/analyse` and draws whatever comes back, so the CLI, the tests and the web page all use
one engine.

## Tests

```bash
python -m pytest tests -q
```

Seventeen tests cover the rule set's consistency (valid keys, no duplicate edges, superset
severity), the graph algorithms (BFS finds the fewest hops, components, density), the engine
(empty = 0, everything = 100, the demo story climbs Low → Moderate → High, the trace, what-if
agrees with recomputing), the monotonicity property over every subset, and the SQLite store.

## What I'd do next

- **Let users edit the threat model.** The rules are data; a rules editor would let a class
  argue about whether `photos + city` really deserves "medium", which is the conversation the
  app is trying to start.
- **Weighted shortest path.** The trace currently counts hops; using edge strength as a cost
  would prefer the path a stranger would actually find easiest.
- **Multi-step what-if.** Ranking single changes is exact and cheap; finding the *smallest set*
  of items to remove to reach "Low" is a set-cover-style search worth trying.
- **A real-data mode**, with consent, that reads a public profile and pre-ticks what it sees —
  the step from "model" to "tool".

## Limitations and honesty notes

- The rules are my judgement, not measured data. The score is a *model* of exposure, useful
  for comparing before and after, not a prediction of harm.
- The scale is relative: 100 means every kind of information in the catalogue is public. Real
  footprints include things the catalogue does not model (location tags, live stories, other
  people's posts).
- The catalogue is small on purpose. Twelve well-explained kinds beat forty vague ones for a
  project whose point is that the reader can follow every rule.
