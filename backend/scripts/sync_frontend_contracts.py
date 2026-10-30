"""Copy backend content/contract JSON into the frontend.

backend/data is the single source of truth. The frontend keeps byte-identical
copies so it can be built and served without the backend checkout.

    python backend/scripts/sync_frontend_contracts.py          # copy
    python backend/scripts/sync_frontend_contracts.py --check  # fail on drift
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / 'backend' / 'data'
FRONTEND = REPO / 'life-reroll-frontend-20261016-212920'

PAIRS = {
    BACKEND / 'events.json': FRONTEND / 'content' / 'events.json',
    BACKEND / 'api_registry.json': FRONTEND / 'lib' / 'contracts' / 'operations.json',
    BACKEND / 'schema_reference.json': FRONTEND / 'lib' / 'contracts' / 'schema.json',
    BACKEND / 'hospital_events.json': FRONTEND / 'lib' / 'contracts' / 'hospital-events.json',
}


def drifted() -> list[tuple[Path, Path]]:
    return [(src, dst) for src, dst in PAIRS.items() if not dst.exists() or dst.read_bytes() != src.read_bytes()]


def main(argv: list[str]) -> int:
    stale = drifted()
    if '--check' in argv:
        for src, dst in stale:
            print(f'out of sync: {dst.relative_to(REPO)} (source {src.relative_to(REPO)})')
        if stale:
            print('Run: python backend/scripts/sync_frontend_contracts.py')
        return 1 if stale else 0
    for src, dst in stale:
        dst.write_bytes(src.read_bytes())
        print(f'updated {dst.relative_to(REPO)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
