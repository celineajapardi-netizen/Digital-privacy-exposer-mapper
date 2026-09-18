"""
The catalogue: every kind of information SHADOW knows about.

Each entry is a *node type*. The user never types anything sensitive into the
app — they only say *which kinds* of information are public. The example value
is just a label to make the graph feel real.

`sensitivity` is how revealing a piece of information is **on its own**, from 0
(a hobby says almost nothing) to 3 (a phone number is a direct line to you).
The point of the whole project is that these numbers are small compared with
what the *combinations* in rules.py add.
"""

from __future__ import annotations

from dataclasses import dataclass

# The four categories are used for colour in the graph and for the "trace"
# algorithm in engine.py, which looks for a path from an *identity* to a *location*.
CATEGORIES = ("identity", "location", "routine", "social")


@dataclass(frozen=True)
class InfoType:
    key: str            # short id used everywhere in code, e.g. "school"
    label: str          # what the user sees
    category: str       # one of CATEGORIES
    sensitivity: int    # 0-3, how revealing it is by itself
    description: str    # one sentence for the tooltip
    example: str        # a made-up example value


CATALOGUE: tuple[InfoType, ...] = (
    InfoType("username", "Username", "identity", 1,
             "The handle you use online. Easy to search for.", "alex2008"),
    InfoType("real_name", "Real name", "identity", 2,
             "Your full name, as it appears on official lists.", "Alex Tan"),
    InfoType("birthday", "Birthday / age", "identity", 2,
             "Your date of birth or exact age.", "14 March 2008"),
    InfoType("contact", "Phone / email", "identity", 3,
             "A direct way to reach you.", "alex2008@mail.com"),
    InfoType("school", "School", "location", 2,
             "Where you study. Fixes both a place and a daily routine.", "ABC School"),
    InfoType("city", "City", "location", 1,
             "Where you live, roughly.", "Jakarta"),
    InfoType("neighbourhood", "Neighbourhood", "location", 3,
             "The part of the city you live in.", "Kemang"),
    InfoType("hobby", "Hobby / activity", "routine", 0,
             "Something you do regularly.", "Orchestra"),
    InfoType("schedule", "Weekly schedule", "routine", 2,
             "When your regular activities happen.", "Every Saturday, 9am"),
    InfoType("public_profile", "Public profile", "social", 1,
             "A social media account that anyone can view.", "@alex2008 on Instagram"),
    InfoType("photos", "Photos with backgrounds", "social", 1,
             "Pictures that show places, uniforms, street signs.", "Photo in school uniform"),
    InfoType("friends", "Tagged friends", "social", 1,
             "Friends tagged or visible in your posts.", "@sam_h, @priya.k"),
)

# Fast lookup by key, e.g. CATALOGUE_BY_KEY["school"].label == "School"
CATALOGUE_BY_KEY: dict[str, InfoType] = {info.key: info for info in CATALOGUE}

ALL_KEYS: frozenset[str] = frozenset(CATALOGUE_BY_KEY)
