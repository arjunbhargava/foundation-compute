import email.message
import io
import json
import urllib.error
import urllib.request
from typing import Any

import agent_spend
import pytest

# Fabricated response bodies for the two pages of a usage-events request,
# with the fields the report reads; costs are in US cents. Run bc-run-a has
# an event on each page. Run bc-run-b's event was billed per request, so it
# has no tokenUsage. Run bc-run-c is missing from the agent listing below. The
# editor and Bugbot events came from no cloud agent run.
USAGE_EVENT_PAGES = [
    """{"pagination": {"hasNextPage": true}, "usageEvents": [
  {"timestamp": "1790935200000", "model": "claude-opus-5-5-xhigh", "cloudAgentId": "bc-run-a", "chargedCents": 3550.0,
   "tokenUsage": {"inputTokens": 100, "outputTokens": 2000, "cacheWriteTokens": 3000, "cacheReadTokens": 40000}},
  {"timestamp": "1790845200000", "model": "composer-2.5", "chargedCents": 125.0,
   "tokenUsage": {"inputTokens": 10, "outputTokens": 20, "cacheWriteTokens": 30, "cacheReadTokens": 40}}
]}""",
    """{"pagination": {"hasNextPage": false}, "usageEvents": [
  {"timestamp": "1790933400000", "model": "claude-sonnet-5-5-high", "cloudAgentId": "bc-run-a", "chargedCents": 50.0,
   "tokenUsage": {"inputTokens": 1, "outputTokens": 2, "cacheWriteTokens": 3, "cacheReadTokens": 4}},
  {"timestamp": "1790769600000", "model": "claude-sonnet-5-5-high", "cloudAgentId": "bc-run-b", "chargedCents": 400.0},
  {"timestamp": "1790700000000", "model": "composer-2.5", "cloudAgentId": "bc-run-c", "chargedCents": 25.0,
   "tokenUsage": {"inputTokens": 5, "outputTokens": 6, "cacheWriteTokens": 7, "cacheReadTokens": 8}},
  {"timestamp": "1790869500000", "model": "github_bugbot", "chargedCents": 0,
   "tokenUsage": {"inputTokens": 500, "outputTokens": 600, "cacheWriteTokens": 0, "cacheReadTokens": 700}}
]}""",
]

# Fabricated pages of the Cloud Agents API's agent listing, with the fields
# the report reads. Run bc-run-a is on the first page and bc-run-b on the
# second; the listing also has an agent no usage event mentions, and a name
# that contains a Markdown table separator.
AGENT_LISTING_PAGES = [
    """{"agents": [
  {"id": "bc-other", "name": "Unrelated", "source": {"repository": "github.com/owner/other", "ref": "main"},
   "target": {"branchName": "cursor/unrelated"}},
  {"id": "bc-run-a", "name": "Label spend", "source": {"repository": "github.com/owner/foundation", "ref": "main"},
   "target": {"branchName": "cursor/label-spend"}}
], "nextCursor": "cursor-2"}""",
    """{"agents": [
  {"id": "bc-run-b", "name": "Fix a|b", "source": {"repository": "github.com/owner/other", "ref": "main"},
   "target": {"branchName": "cursor/fix-a-b"}}
]}""",
]

REPORT_START = """\
Cursor usage from 2026-09-26 00:00 UTC up to 2026-10-03 00:00 UTC.
"""

EXPECTED_LABELLED_REPORT = (
    REPORT_START
    + """
| Cloud agent run | Task | Repository | Branch | First event (UTC) | Models | Events | Input tokens | Output tokens | Cache write tokens | Cache read tokens | Cost ($) |
|---|---|---|---|---|---|--:|--:|--:|--:|--:|--:|
| bc-run-a | Label spend | github.com/owner/foundation | cursor/label-spend | 2026-10-02 09:30 | claude-opus-5-5-xhigh, claude-sonnet-5-5-high | 2 | 101 | 2,002 | 3,003 | 40,004 | 36.00 |
| bc-run-b | Fix a\\|b | github.com/owner/other | cursor/fix-a-b | 2026-09-30 12:00 | claude-sonnet-5-5-high | 1 | 0 | 0 | 0 | 0 | 4.00 |
| bc-run-c | unknown | unknown | unknown | 2026-09-29 16:40 | composer-2.5 | 1 | 5 | 6 | 7 | 8 | 0.25 |

| Total | Events | Input tokens | Output tokens | Cache write tokens | Cache read tokens | Cost ($) |
|---|--:|--:|--:|--:|--:|--:|
| All 3 cloud agent runs | 4 | 106 | 2,008 | 3,010 | 40,012 | 40.25 |
| Repository github.com/owner/foundation, 1 run | 2 | 101 | 2,002 | 3,003 | 40,004 | 36.00 |
| Repository github.com/owner/other, 1 run | 1 | 0 | 0 | 0 | 0 | 4.00 |
| Repository unknown, 1 run | 1 | 5 | 6 | 7 | 8 | 0.25 |
| Usage outside cloud agent runs | 2 | 510 | 620 | 30 | 740 | 1.25 |
| All usage | 6 | 616 | 2,628 | 3,040 | 40,752 | 41.50 |
"""
)

EXPECTED_UNLABELLED_REPORT = (
    REPORT_START
    + """Task and repository labels need CURSOR_API_KEY, which is not set.

| Cloud agent run | First event (UTC) | Models | Events | Input tokens | Output tokens | Cache write tokens | Cache read tokens | Cost ($) |
|---|---|---|--:|--:|--:|--:|--:|--:|
| bc-run-a | 2026-10-02 09:30 | claude-opus-5-5-xhigh, claude-sonnet-5-5-high | 2 | 101 | 2,002 | 3,003 | 40,004 | 36.00 |
| bc-run-b | 2026-09-30 12:00 | claude-sonnet-5-5-high | 1 | 0 | 0 | 0 | 0 | 4.00 |
| bc-run-c | 2026-09-29 16:40 | composer-2.5 | 1 | 5 | 6 | 7 | 8 | 0.25 |

| Total | Events | Input tokens | Output tokens | Cache write tokens | Cache read tokens | Cost ($) |
|---|--:|--:|--:|--:|--:|--:|
| All 3 cloud agent runs | 4 | 106 | 2,008 | 3,010 | 40,012 | 40.25 |
| Usage outside cloud agent runs | 2 | 510 | 620 | 30 | 740 | 1.25 |
| All usage | 6 | 616 | 2,628 | 3,040 | 40,752 | 41.50 |
"""
)

ADMIN_KEY_AUTHORIZATION = "Basic dGVzdC1rZXk6"  # "test-key:"
AGENTS_KEY_AUTHORIZATION = "Basic YWdlbnRzLWtleTo="  # "agents-key:"


class FakeApis:
    """Stands in for ``urllib.request.urlopen``, serving both Cursor APIs' fabricated pages.

    ``requests`` records each call as the URL, the Authorization header, and
    the JSON body (``None`` for a GET).
    """

    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None, dict[str, Any] | None]] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        body = json.loads(request.data) if isinstance(request.data, bytes) else None
        self.requests.append(
            (request.full_url, request.get_header("Authorization"), body)
        )
        if request.full_url == agent_spend.USAGE_EVENTS_URL:
            assert body is not None
            page: int = body["page"]
            return io.BytesIO(USAGE_EVENT_PAGES[page - 1].encode())
        listing_page = 1 if "cursor=" not in request.full_url else 2
        assert request.full_url.startswith(agent_spend.AGENTS_URL + "?limit=100")
        return io.BytesIO(AGENT_LISTING_PAGES[listing_page - 1].encode())


# endDate is a millisecond before --until, because the API includes it.
USAGE_WINDOW = {"startDate": 1790380800000, "endDate": 1790985599999, "pageSize": 1000}
USAGE_REQUESTS = [
    (
        agent_spend.USAGE_EVENTS_URL,
        ADMIN_KEY_AUTHORIZATION,
        {**USAGE_WINDOW, "page": 1},
    ),
    (
        agent_spend.USAGE_EVENTS_URL,
        ADMIN_KEY_AUTHORIZATION,
        {**USAGE_WINDOW, "page": 2},
    ),
]


def test_report_labels_each_run_with_its_agent_and_totals_each_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    apis = FakeApis()
    monkeypatch.setenv("CURSOR_ADMIN_API_KEY", "test-key")
    monkeypatch.setenv("CURSOR_API_KEY", "agents-key")
    monkeypatch.setattr(urllib.request, "urlopen", apis)

    exit_code = agent_spend.main(["--since", "2026-09-26", "--until", "2026-10-03"])

    assert exit_code == 0
    assert capsys.readouterr().out == EXPECTED_LABELLED_REPORT
    # Basic authentication with each key as the user name and no password.
    # bc-run-c is in neither listing page, so the listing is read to its end.
    assert apis.requests == [
        *USAGE_REQUESTS,
        (agent_spend.AGENTS_URL + "?limit=100", AGENTS_KEY_AUTHORIZATION, None),
        (
            agent_spend.AGENTS_URL + "?limit=100&cursor=cursor-2",
            AGENTS_KEY_AUTHORIZATION,
            None,
        ),
    ]


def test_report_has_no_labels_and_says_why_when_the_agents_key_is_not_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    apis = FakeApis()
    monkeypatch.setenv("CURSOR_ADMIN_API_KEY", "test-key")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", apis)

    exit_code = agent_spend.main(["--since", "2026-09-26", "--until", "2026-10-03"])

    assert exit_code == 0
    assert capsys.readouterr().out == EXPECTED_UNLABELLED_REPORT
    assert apis.requests == USAGE_REQUESTS


def test_listing_is_read_only_until_every_run_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apis = FakeApis()
    monkeypatch.setattr(urllib.request, "urlopen", apis)

    labels = agent_spend.fetch_run_labels("agents-key", {"bc-run-a"})

    assert labels == {
        "bc-run-a": agent_spend.RunLabel(
            "Label spend", "github.com/owner/foundation", "cursor/label-spend"
        )
    }
    assert len(apis.requests) == 1


def test_report_fails_without_calling_the_api_when_the_key_is_not_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        raise AssertionError("the report called the Admin API without a key")

    monkeypatch.delenv("CURSOR_ADMIN_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    assert agent_spend.main([]) == 1
    assert "error: CURSOR_ADMIN_API_KEY is not set." in capsys.readouterr().err


def test_report_fails_with_the_api_error_text_when_the_api_rejects_the_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rejection = b'{"code":"error","message":"Invalid Team API Key"}'

    def reject_urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        headers = email.message.Message()
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", headers, io.BytesIO(rejection)
        )

    monkeypatch.setenv("CURSOR_ADMIN_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", reject_urlopen)

    assert agent_spend.main([]) == 1
    assert capsys.readouterr().err == (
        "error: https://api.cursor.com/teams/filtered-usage-events returned HTTP 401: "
        '{"code":"error","message":"Invalid Team API Key"}\n'
    )


def test_report_fails_with_the_api_error_text_when_the_agent_listing_rejects_the_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    usage_apis = FakeApis()
    rejection = b'{"code":"error","message":"Invalid API key"}'

    def reject_listing(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        if request.full_url == agent_spend.USAGE_EVENTS_URL:
            return usage_apis(request, timeout)
        headers = email.message.Message()
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", headers, io.BytesIO(rejection)
        )

    monkeypatch.setenv("CURSOR_ADMIN_API_KEY", "test-key")
    monkeypatch.setenv("CURSOR_API_KEY", "agents-key")
    monkeypatch.setattr(urllib.request, "urlopen", reject_listing)

    assert agent_spend.main([]) == 1
    assert capsys.readouterr().err == (
        "error: https://api.cursor.com/v0/agents returned HTTP 401: "
        '{"code":"error","message":"Invalid API key"}\n'
    )


def test_listing_reads_at_most_the_page_limit_when_a_run_is_not_in_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def endless_listing(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        urls.append(request.full_url)
        return io.BytesIO(b'{"agents": [{"id": "bc-other"}], "nextCursor": "more"}')

    monkeypatch.setattr(agent_spend, "MAX_LISTING_PAGES", 3)
    monkeypatch.setattr(urllib.request, "urlopen", endless_listing)

    labels = agent_spend.fetch_run_labels("agents-key", {"bc-run-missing"})

    assert labels == {"bc-run-missing": agent_spend.UNKNOWN_RUN_LABEL}
    assert len(urls) == 3
