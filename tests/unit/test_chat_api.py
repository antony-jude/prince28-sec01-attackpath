from attackpath.llm.gateway import FakeLLM, LLMGateway


def test_chat_endpoint_uses_configured_gateway(client):
    client.app.state.gateway = LLMGateway([FakeLLM("fake", script=["mapped T1566.001"])])

    response = client.post(
        "/v1/chat",
        json={"message": "Map this phishing attachment", "stream": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "mapped T1566.001"
    assert body["provider"] == "fake"
    assert body["fallback_used"] is False


def test_streaming_chat_returns_deltas_and_done_summary(client):
    client.app.state.gateway = LLMGateway([FakeLLM("fake", script=["hello world"])])

    response = client.post(
        "/v1/chat",
        json={"message": "Say hello", "stream": True},
    )

    assert response.status_code == 200
    assert '"delta": "hello "' in response.text
    assert '"event": "done"' not in response.text
    assert "event: done" in response.text
