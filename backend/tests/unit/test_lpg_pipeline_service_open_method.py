from app.services.lpg_playwright_pipeline import (
    TaxpayerPipelineResult,
    _taxpayer_result_to_dict,
)


def test_taxpayer_pipeline_result_defaults_service_open_method_to_none() -> None:
    result = TaxpayerPipelineResult(
        taxpayer_id=1,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20111111112",
    )

    assert result.service_open_method is None


def test_taxpayer_pipeline_result_serializes_service_open_method() -> None:
    result = TaxpayerPipelineResult(
        taxpayer_id=1,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20111111112",
    )
    result.service_open_method = "direct_url"

    payload = _taxpayer_result_to_dict(result)

    assert payload["service_open_method"] == "direct_url"
