import json
from types import SimpleNamespace
import httpx
import pytest
from app import llm
from app.config import settings
from app.schemas import Rules


def test_account_limit_auth_and_retry_headers():
    for status, payload in [(200, {"data": {"usage": 2.99}}), (401, {}), (200, {"data": {}})]:
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))) as client:
            with pytest.raises(llm.LLMError):
                llm.account_usage(client)
    assert llm.retry_delay("120") == 120
    assert llm.retry_delay("not-a-date") == 0


def test_missing_key_and_disallowed_model(monkeypatch):
    monkeypatch.setattr(settings(), "openrouter_api_key", "")
    with pytest.raises(llm.LLMError, match="Configura"):
        llm.analyze(None, {})
    monkeypatch.setattr(settings(), "openrouter_api_key", "fake")
    monkeypatch.setattr(settings(), "openrouter_model", "expensive/model")
    with pytest.raises(llm.LLMError, match="bajo costo"):
        llm.analyze(None, {})


@pytest.mark.parametrize("mode", ["valid", "bad_json", "fabricated_evidence", "timeout", "429", "401", "402"])
def test_real_adapter_failure_modes(monkeypatch, mode):
    monkeypatch.setattr(settings(), "openrouter_api_key", "fake-key-only-for-test")
    source = SimpleNamespace(id="source-1", content="Empresa Test busca un Finance Manager para controlar gastos corporativos.")
    lead = SimpleNamespace(company="Empresa Test", domain="empresa.example", contact="Ana", country="México", sources=[source])
    result = {"summary": "Resumen basado en el texto.", "angle": "Control del gasto corporativo.", "signals": [{"type": "finance_hiring", "source_id": source.id, "evidence": source.content}], "subject": "Control de gastos", "body": "Hola Ana, me gustaría conversar sobre el control de gastos."}
    if mode == "fabricated_evidence": result["signals"][0]["evidence"] = "La empresa ha recaudado mil millones de dólares."
    def handle(request):
        if request.url.path.endswith('/key'): return httpx.Response(200, json={"data": {"usage": 0}})
        if request.url.path.endswith('/models'): return httpx.Response(200, json={"data": [{"id": settings().openrouter_model, "pricing": {"prompt": "0.0000001", "completion": "0.0000004"}}]})
        payload = json.loads(request.content)
        assert payload["provider"]["max_price"] == {"prompt": 0.2, "completion": 0.5, "request": 0}
        if mode == "timeout": raise httpx.ReadTimeout("timeout")
        if mode in {"429", "401", "402"}: return httpx.Response(int(mode), json={}, headers={"Retry-After": "120"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "broken json" if mode == "bad_json" else json.dumps(result)}}], "model": "test", "usage": {"prompt_tokens": 50, "completion_tokens": 100, "cost": .001}})
    original = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    if mode == "valid":
        analysis, trace = llm.analyze(lead, Rules().model_dump())
        assert analysis.signals[0].source_id == "source-1"
        assert trace["cost_usd"] == .001
    else:
        with pytest.raises(llm.LLMError) as exc:
            llm.analyze(lead, Rules().model_dump())
        assert exc.value.retryable == (mode not in {"401", "402"})
        if mode == "429": assert exc.value.retry_after == 120

