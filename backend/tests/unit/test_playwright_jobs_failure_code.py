from app.services.extraction_failure_mapper import map_failure
from app.services.extraction_phases import ExtractionPhase


def test_map_failure_tuple_is_three():
    # Guardrail: el worker depende de desempaquetar 3 valores.
    result = map_failure(ExtractionPhase.LOGIN_START, "auth_failed")
    assert len(result) == 3
