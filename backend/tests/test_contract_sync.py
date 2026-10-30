import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'sync_frontend_contracts.py'


def load():
    spec = importlib.util.spec_from_file_location('sync_frontend_contracts', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontend_copies_match_backend_source():
    stale = load().drifted()
    assert not stale, f'run backend/scripts/sync_frontend_contracts.py: {stale}'


def test_medical_expense_events_never_add_cash():
    from app.content import EVENTS

    gains = [e['id'] for e in EVENTS if '醫療' in e['source_impact'] and e['effect']['cash_delta_minor'] > 0]
    assert gains == []
