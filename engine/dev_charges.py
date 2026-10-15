"""Development charges on a new home in Pickering, from the pamphlets scripts/dev_charges.py stores.

Three authorities charge per new dwelling: the City (city-wide, or the Seaton lands), the Region of
Durham (region-wide services, plus water and sewer where those services are planned; in Seaton
the water and sewer come from its own area-specific schedule) and the two school boards.
"""
import json
from functools import lru_cache
from pathlib import Path

# Development Charges Act, 1997, s. 2(3.2) and (3.3): a second or third unit in a house, or one
# unit in a building ancillary to it, does not trigger municipal development charges.
ARU_EXEMPTION = 'Development Charges Act, 1997, s. 2(3.2)–(3.3)'
WATER_SEWER = ('water', 'sewer', 'sewage')


@lru_cache(maxsize=4)
def _load(path: str, stamp: int) -> dict | None:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load(store: Path) -> dict | None:
    path = store / 'dev_charges.json'
    return _load(str(path), path.stat().st_mtime_ns) if path.exists() else None


def for_lot(store: Path, seaton: bool, serviced: bool | None, kind: str = 'single_semi') -> dict | None:
    """Each authority's charge on one new dwelling of this kind, its services, and the pamphlet it is from."""
    data = load(store)
    if not data:
        return None
    lines = []
    for s in data['schedules']:
        regional = s['authority'] == 'Region of Durham'
        if regional and s['area'] == 'seaton':
            if not seaton:
                continue
            services = s['services']  # Seaton's own water and sewer
        elif s['area'] != ('seaton' if seaton and not regional else 'citywide'):
            continue
        else:
            # The region-wide water and sewer charges are not paid in Seaton, nor where the services are not planned.
            drop = regional and (seaton or serviced is False)
            services = {k: v for k, v in s['services'].items() if not (drop and any(w in k.lower() for w in WATER_SEWER))}
        amounts = {k: v[kind] for k, v in services.items() if kind in v}
        lines.append({'authority': s['authority'], 'area': s['area'], 'amount': round(sum(amounts.values())),
                      'services': amounts, 'effective': s.get('effective'), 'url': s['url']})
    school = next((s['education'] for s in data['schedules'] if s.get('education')), None)
    if school:
        lines.append({'authority': 'School boards (public and Catholic)', 'amount': round(school['total']),
                      'services': {'Public': school['public'], 'Catholic': school['catholic']},
                      'url': next(s['url'] for s in data['schedules'] if s.get('education'))})
    return {'kind': kind, 'lines': lines, 'total': sum(l['amount'] for l in lines), 'retrieved_at': data['retrieved_at'],
            'garden_suite': {'municipal': 0, 'basis': ARU_EXEMPTION,
                             'school_boards': round(school['total']) if school else None}}
