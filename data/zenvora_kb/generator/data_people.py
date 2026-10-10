# -*- coding: utf-8 -*-
from data_people_a import PEOPLE_A
from data_people_b import PEOPLE_B

PEOPLE = PEOPLE_A + PEOPLE_B

# Assign employee IDs in order of joining date (ties broken by slug)
_order = sorted(PEOPLE, key=lambda p: (p["joined"], p["slug"]))
for _i, _p in enumerate(_order, start=1):
    _p["id"] = f"ZV-{1000 + _i}"

BY_SLUG = {p["slug"]: p for p in PEOPLE}
