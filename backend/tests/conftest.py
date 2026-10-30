import pytest


@pytest.fixture(autouse=True)
def no_external_model_by_default(monkeypatch):
    # Real service checks are run explicitly; normal game regressions stay deterministic and offline.
    monkeypatch.setenv('LIFE_COACH_ENABLED', '0')
    monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED', '0')
    # Mock-provider tests must not depend on a developer's private ai-config.json.
    monkeypatch.setenv('LIFE_COACH_BASE_URL', 'http://127.0.0.1:9/api/v1')

    monkeypatch.setenv('LIFE_EMAIL_MODE', 'development')
    monkeypatch.setenv('LIFE_DEVELOPMENT_MODE', '1')
    monkeypatch.setenv('LIFE_SKIP_EMAIL_VERIFICATION', '1')
