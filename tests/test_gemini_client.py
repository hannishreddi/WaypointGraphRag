"""GeminiClient over a fake transport and a fake clock: parsing, safety, pacing, 429 handling."""
from __future__ import annotations

import json

import httpx
import pytest

from waypoint.llm.client import DailyQuotaExceeded, LLMError, QuotaTooSmall
from waypoint.llm.gemini import GeminiClient, parse_quota_error
from waypoint.llm.ratelimit import RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def ok(text: str = '{"a": 1}', **usage: int) -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": text}]},
                        "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 7, "thoughtsTokenCount": 3,
                          "cachedContentTokenCount": 40, **usage}})


def quota(quota_id: str, delay: str | None = None, value: str = "5") -> httpx.Response:
    details: list[dict] = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": quota_id, "quotaValue": value}]}]
    if delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    return httpx.Response(429, json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                               "message": "quota", "details": details}})


PER_MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
PER_DAY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"


def make(responses: list[httpx.Response], **kw: object) -> tuple[GeminiClient, list[httpx.Request], FakeTime]:
    seen: list[httpx.Request] = []
    replies = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return replies.pop(0)

    t = FakeTime()
    client = GeminiClient("test-key", transport=httpx.MockTransport(handler), clock=t.clock, sleep=t.sleep,
                          **kw)  # type: ignore[arg-type]
    return client, seen, t


def call(client: GeminiClient, json_mode: bool = True) -> object:
    return client.complete(model="m-answer", system="sys", prompt="p", max_tokens=64, json_mode=json_mode)


def test_request_shape_and_usage() -> None:
    client, seen, _ = make([ok('{"answer": "x"}')])
    c = call(client)
    assert c.text == '{"answer": "x"}'  # thought parts dropped
    assert (c.input_tokens, c.output_tokens, c.cached_input_tokens) == (100, 10, 40)
    req = seen[0]
    assert req.url.path == "/v1beta/models/m-answer:generateContent"
    assert req.headers["x-goog-api-key"] == "test-key" and "key=" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "p"}]}]
    gc = body["generationConfig"]
    assert gc["temperature"] == 0 and gc["maxOutputTokens"] == 64
    assert gc["responseMimeType"] == "application/json" and gc["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert client.calls == {"m-answer": 1} and client.total_requests() == 1


def test_no_json_mode_and_no_thinking_level() -> None:
    client, seen, _ = make([ok("plain")], thinking_level="")
    call(client, json_mode=False)
    gc = json.loads(seen[0].content)["generationConfig"]
    assert "responseMimeType" not in gc and "thinkingConfig" not in gc


@pytest.mark.parametrize("payload", [
    {"promptFeedback": {"blockReason": "SAFETY"}},
    {"candidates": [{"content": {"parts": [{"text": "partial"}]}, "finishReason": "PROHIBITED_CONTENT"}]},
    {"candidates": [{"finishReason": "SAFETY"}]},
    {"candidates": []},
])
def test_safety_blocks_raise(payload: dict) -> None:
    client, seen, t = make([httpx.Response(200, json=payload)])
    with pytest.raises(LLMError):
        call(client)
    assert len(seen) == 1 and t.sleeps == []  # not retried


def test_limiter_spaces_requests() -> None:
    client, _, t = make([ok(), ok(), ok()], rpm=5)
    for _ in range(3):
        call(client)
    assert t.sleeps == [12.0, 12.0]


def test_limiters_are_per_model() -> None:
    client, _, t = make([ok(), ok()], rpm=5)
    client.complete(model="a", system="s", prompt="p", max_tokens=8)
    client.complete(model="b", system="s", prompt="p", max_tokens=8)
    assert t.sleeps == [] and client.calls == {"a": 1, "b": 1}


def test_per_minute_429_slows_down_and_honours_retry_delay() -> None:
    client, seen, t = make([quota(PER_MINUTE, delay="90s"), ok()], rpm=5)
    assert call(client).text == '{"a": 1}'
    assert len(seen) == 2 and t.sleeps == [90.0]
    assert client.limiter("m-answer").rpm == 2.5 and client.rate_limited == {"m-answer": 1}


def test_per_minute_429_waits_at_least_a_minute_window() -> None:
    client, _, t = make([quota(PER_MINUTE, delay="3s"), ok()])
    call(client)
    assert t.sleeps == [65.0]


def test_retry_after_header() -> None:
    resp = httpx.Response(429, headers={"retry-after": "120"}, json={"error": {"message": "slow down"}})
    q = parse_quota_error(resp)
    assert q.retry_after_s == 120.0 and not q.daily


def test_daily_quota_stops_without_retry() -> None:
    client, seen, t = make([quota(PER_DAY, delay="30s", value="250")])
    with pytest.raises(DailyQuotaExceeded, match="midnight Pacific"):
        call(client)
    assert len(seen) == 1 and t.sleeps == []


def test_daily_quota_from_message_when_no_details() -> None:
    resp = httpx.Response(429, json={"error": {"message": "You exceeded your daily quota"}})
    assert parse_quota_error(resp).daily


def test_request_too_large_for_minute_quota_stops() -> None:
    """After a full idle minute the request still gets a per-minute 429: stop, no loop."""
    tpm = "GenerateContentInputTokensPerModelPerMinute-FreeTier"
    client, seen, t = make([quota(tpm, value="250000"), quota(tpm, value="250000"), ok()])
    with pytest.raises(QuotaTooSmall, match="250000"):
        call(client)
    assert len(seen) == 2 and t.sleeps == [65.0]


def test_repeated_429_gives_up_after_max_retries() -> None:
    # The fake clock never lets a full minute of idle pass: each 429 comes "too early".
    client, seen, t = make([quota(PER_MINUTE)] * 3, max_retries=2)
    client._sleep = lambda s: t.sleeps.append(s)  # time stands still
    with pytest.raises(LLMError, match="still rate limited"):
        call(client)
    assert len(seen) == 3


def test_5xx_backoff_then_success() -> None:
    client, seen, t = make([httpx.Response(503, text="busy"), httpx.Response(500, text="x"), ok()], rpm=1000)
    call(client)
    assert len(seen) == 3 and t.sleeps == [5.0, 10.0]


def test_4xx_raises_immediately() -> None:
    client, seen, _ = make([httpx.Response(400, json={"error": {"message": "bad model"}})])
    with pytest.raises(LLMError, match="400"):
        call(client)
    assert len(seen) == 1


def test_count_tokens_and_model_info() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 81234})
        return httpx.Response(200, json={"name": "models/m", "inputTokenLimit": 1048576})

    client = GeminiClient("k", transport=httpx.MockTransport(handler))
    assert client.count_tokens(model="m", system="s", prompt="p") == 81234
    body = json.loads(seen[0].content)["generateContentRequest"]
    assert body["model"] == "models/m" and body["contents"][0]["parts"][0]["text"] == "p"
    assert client.model_info("m")["inputTokenLimit"] == 1048576
    assert client.total_requests() == 0  # neither counts as a generation call


def test_rate_limiter_floor() -> None:
    t = FakeTime()
    lim = RateLimiter(2, min_rpm=1, clock=t.clock, sleep=t.sleep)
    for _ in range(3):
        lim.slow_down()
    assert lim.rpm == 1
    assert lim.wait() is None and lim.wait() == 60.0 and t.sleeps == [60.0]
    assert lim.waited_s == 60.0  # pacing sleep is counted (latency excl. wait in the eval)

