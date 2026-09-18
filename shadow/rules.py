"""
The rules: how pieces of information relate, and which combinations are risky.

This is the "threat model". Nothing here is hacked or looked up — it is a
written-down description of how someone could join dots. Two kinds of rule:

* A `Relation` is an **edge** in the graph: two kinds of information that lead
  to each other. `strength` (1-3) says how directly one leads to the other.

* A `Combination` is a **pattern**: a set of information kinds that, when *all*
  present, reveal something none of them reveals alone. `severity` (1-3) is
  low / medium / high.

Invariant (checked by the tests): if one combination is a superset of another,
its severity is at least as high. This keeps the exposure score from ever going
*down* when more information is shared.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Relation:
    a: str
    b: str
    strength: int   # 1 = loose link, 3 = one directly leads to the other
    reason: str     # shown when you hover the edge


@dataclass(frozen=True)
class Combination:
    items: frozenset[str]
    severity: int   # 1 = low, 2 = medium, 3 = high
    title: str
    explanation: str


SEVERITY_LABEL = {1: "low", 2: "medium", 3: "high"}


def _rel(a: str, b: str, strength: int, reason: str) -> Relation:
    return Relation(a, b, strength, reason)


def _combo(items: list[str], severity: int, title: str, explanation: str) -> Combination:
    return Combination(frozenset(items), severity, title, explanation)


# --------------------------------------------------------------------------
# Relations (edges). Order does not matter; the graph is undirected.
# --------------------------------------------------------------------------
RELATIONS: tuple[Relation, ...] = (
    _rel("username", "public_profile", 3, "A username is the search key that finds the profile."),
    _rel("username", "real_name", 2, "Links the online identity to the real one."),
    _rel("username", "contact", 1, "People often reuse the same handle for their email."),
    _rel("public_profile", "school", 2, "Profiles often mention or show the school."),
    _rel("public_profile", "hobby", 2, "Posts show what you do."),
    _rel("public_profile", "photos", 3, "Photos are posted on the profile."),
    _rel("public_profile", "friends", 2, "Tagged friends appear on the profile."),
    _rel("public_profile", "birthday", 1, "Birthday posts reveal the date."),
    _rel("public_profile", "contact", 2, "An email or number in the bio."),
    _rel("school", "schedule", 3, "School fixes a large part of the weekly routine."),
    _rel("school", "city", 2, "A school pins you to one part of a city."),
    _rel("school", "real_name", 2, "Prize lists, sports results and yearbooks name pupils."),
    _rel("school", "friends", 2, "Friends' profiles usually share the same school."),
    _rel("school", "photos", 2, "Uniforms and buildings identify a school."),
    _rel("hobby", "schedule", 2, "A hobby happens at regular times."),
    _rel("schedule", "city", 2, "A time plus a city gives a place to look."),
    _rel("schedule", "neighbourhood", 3, "A time plus a neighbourhood gives a place to wait."),
    _rel("photos", "city", 2, "Signs and landmarks in backgrounds reveal the city."),
    _rel("photos", "neighbourhood", 3, "Street names and shop fronts reveal the neighbourhood."),
    _rel("city", "neighbourhood", 2, "The neighbourhood is inside the city."),
    _rel("real_name", "birthday", 2, "Name and date of birth appear together on records."),
    _rel("real_name", "contact", 3, "A name attached to a number or email."),
)


# --------------------------------------------------------------------------
# Combinations (risky patterns). Keep supersets at least as severe as subsets.
# --------------------------------------------------------------------------
COMBINATIONS: tuple[Combination, ...] = (
    _combo(["school", "schedule"], 2, "Predictable routine",
           "Knowing the school and the weekly schedule shows where you are expected to be on most days."),
    _combo(["city", "schedule"], 2, "Location at known times",
           "A schedule on its own is just times. Add the city and it becomes places where you can actually be found."),
    _combo(["username", "school"], 2, "Identity correlation",
           "A username search that leads to a school connects an anonymous handle to a real group of people."),
    _combo(["username", "school", "schedule"], 3, "Strong chain: handle → school → routine",
           "Someone who only knows your username could work out where you will be and when."),
    _combo(["city", "school", "schedule"], 3, "Physical location at specific times",
           "City narrows the map, school fixes the place, schedule fixes the time."),
    _combo(["real_name", "birthday", "city"], 3, "Identity triangulation",
           "Name, date of birth and city are the three things most account-recovery and security questions ask for."),
    _combo(["username", "real_name"], 2, "Online ↔ offline identity link",
           "Everything ever posted under the username can now be attributed to a real person."),
    _combo(["public_profile", "photos", "city"], 2, "Photo geolocation",
           "Street signs, shop fronts and landmarks in photos, combined with the city, narrow down to a neighbourhood."),
    _combo(["hobby", "schedule"], 1, "Recurring activity",
           "A hobby plus its timetable is a regular, repeatable event."),
    _combo(["public_profile", "hobby", "schedule"], 2, "Public timetable",
           "A public profile that shows an activity and when it happens is a timetable anyone can read."),
    _combo(["friends", "school"], 1, "Social confirmation",
           "Tagged friends make it easy to confirm which school a profile belongs to, even if you never say it."),
    _combo(["photos", "school"], 1, "Uniform reveal",
           "A uniform or a building in a photo identifies the school even if it is never named."),
    _combo(["birthday", "school", "city"], 2, "Narrow group",
           "Age, school and city together describe a group of maybe a few dozen people."),
    _combo(["contact", "real_name"], 3, "Direct reach",
           "A name plus a phone number or email is enough to contact, impersonate or phish you directly."),
    _combo(["neighbourhood", "schedule"], 3, "Home area at known times",
           "Neighbourhood plus schedule gives both where you live and when you leave."),
    _combo(["contact", "username", "public_profile"], 2, "Handle reuse",
           "The same handle across email and profiles ties every account together."),
)


def matching_combinations(selected: frozenset[str]) -> list[Combination]:
    """
    Return the combinations whose items are all present in `selected`, keeping
    only the *maximal* ones.

    Example: with username + school + schedule present, "Identity correlation"
    (username + school) and "Predictable routine" (school + schedule) both
    match, but they are swallowed by the bigger "Strong chain" pattern, so only
    that one is reported. This stops the same fact being counted three times.
    """
    matched = [c for c in COMBINATIONS if c.items <= selected]
    maximal = []
    for c in matched:
        absorbed = any(c.items < other.items for other in matched)   # strict subset?
        if not absorbed:
            maximal.append(c)
    # Most severe first, then larger patterns first.
    maximal.sort(key=lambda c: (-c.severity, -len(c.items), c.title))
    return maximal


def active_relations(selected: frozenset[str]) -> list[Relation]:
    """Edges whose both ends are present."""
    return [r for r in RELATIONS if r.a in selected and r.b in selected]
