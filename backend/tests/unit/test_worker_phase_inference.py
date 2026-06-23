from app.services.extraction_failure_mapper import map_failure, infer_phase_from_technical
from app.services.extraction_phases import ExtractionPhase


def test_inference_changes_unknown_to_specific_code():
    # Without phase + generic technical → UNKNOWN_ERROR (current behavior)
    _, _, code_generic = map_failure(None, "timeout")
    assert code_generic == "UNKNOWN_ERROR"

    # With technical text that hints at login, inferred phase changes the code
    tech = 'Locator.fill: Timeout waiting for textbox "TU CLAVE"'
    inferred = infer_phase_from_technical(tech)
    assert inferred == ExtractionPhase.LOGIN_START
    _, _, code_inferred = map_failure(inferred, "timeout")
    assert code_inferred != "UNKNOWN_ERROR"
    assert code_inferred == "TRANSIENT_LOGIN"
