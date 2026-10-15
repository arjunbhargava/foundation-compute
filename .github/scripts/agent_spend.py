"""Report tokens and cost per Cursor cloud agent run, from the Cursor Admin API.

Run it with ``mise run spend``; arguments after ``--`` go to this script, for
example ``mise run spend -- --since 2026-09-26``. It reads a team Admin API
key from the environment variable ``CURSOR_ADMIN_API_KEY``, fetches every
usage event in the window from the Admin API's usage-events endpoint, and
prints two Markdown tables: one row per cloud agent run, most expensive first,
then totals for all runs, for each repository, for usage outside the runs
(people's editors and Bugbot, for example), and for all usage. The last total
is the one to compare with the dashboard's usage total for the same window.

The usage events say nothing about what a run was for, so each run's task
(the agent's name), repository, and branch come from the Cloud Agents API's
agent listing, which takes a different key from the Admin API: the environment
variable ``CURSOR_API_KEY``. A run missing from the listing is labelled
``unknown``. Without ``CURSOR_API_KEY`` the report has no labels or repository
totals, and says so.

Cost is each event's ``chargedCents``: the model cost plus the Cursor Token
Rate, whether paid on demand or from the plan's included usage. The Admin API
documents it as the field that matches the dashboard's totals.
"""

<<<<<<< before updating
# Annotations name Usage before its definition, which Python 3.13 rejects
# unless annotations are deferred.
=======
# Annotations name Usage before its definition. Python 3.14 defers evaluating
# them, but 3.13 raises NameError unless this import defers them too.
>>>>>>> after updating
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Self

ADMIN_KEY_VARIABLE = "CURSOR_ADMIN_API_KEY"
AGENTS_KEY_VARIABLE = "CURSOR_API_KEY"
USAGE_EVENTS_URL = "https://api.cursor.com/teams/filtered-usage-events"
AGENTS_URL = "https://api.cursor.com/v0/agents"
EVENTS_PER_PAGE = 1000  # The endpoint's maximum.
AGENTS_PER_PAGE = 100  # The endpoint's maximum.
# The Cloud Agents API allows 20 requests a minute. Ten pages, the 1,000 newest
# agents, stay under that; a run older than that is labelled unknown.
MAX_LISTING_PAGES = 10
UNKNOWN_LABEL = "unknown"
REQUEST_TIMEOUT_S = 60
DEFAULT_WINDOW = timedelta(days=7)
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
COUNT_COLUMNS = "Events | Input tokens | Output tokens | Cache write tokens | Cache read tokens | Cost ($)"
COUNT_ALIGNMENT = "--:|--:|--:|--:|--:|--:"

type UsageEvent = dict[str, Any]


@dataclass(frozen=True)
class RunLabel:
    """What a cloud agent run was for, from the Cloud Agents API's agent listing.

    Attributes:
        task: the agent's ``name``.
        repository: the agent's ``source.repository``, such as
            ``github.com/owner/repo``.
        branch_name: the agent's ``target.branchName``.

    Each attribute is ``"unknown"`` if the listing lacks the run or the field.
    """

    task: str
    repository: str
    branch_name: str


UNKNOWN_RUN_LABEL = RunLabel(UNKNOWN_LABEL, UNKNOWN_LABEL, UNKNOWN_LABEL)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the spend report for the window the command-line arguments give.

    Args:
        argv: command-line arguments without the program name; ``None`` reads
            ``sys.argv``.

    Returns:
        0 after printing the report to stdout; 1 if ``CURSOR_ADMIN_API_KEY``
        is not set or either API returns an HTTP error, with the reason on
        stderr. A missing ``CURSOR_API_KEY`` is not an error: the report is
        printed without labels.
    """
    since, until = _parse_window(argv)
    api_key = os.environ.get(ADMIN_KEY_VARIABLE)
    if not api_key:
        print(
            f"error: {ADMIN_KEY_VARIABLE} is not set. Set it to a Cursor team Admin API key: "
            "for cloud agents, as a secret under Cloud Agents > Secrets in the Cursor dashboard.",
            file=sys.stderr,
        )
        return 1

    events_by_run: dict[str, list[UsageEvent]] = {}
    events_outside_runs: list[UsageEvent] = []
    labels: dict[str, RunLabel] | None = None
    url = USAGE_EVENTS_URL
    try:
        events = fetch_usage_events(api_key, since, until)
        events_by_run, events_outside_runs = split_by_run(events)
        agents_api_key = os.environ.get(AGENTS_KEY_VARIABLE)
        if agents_api_key:
            url = AGENTS_URL
            labels = fetch_run_labels(agents_api_key, set(events_by_run))
    except urllib.error.HTTPError as error:
        with error:
            response_text = error.read().decode(errors="replace")
        print(
            f"error: {url} returned HTTP {error.code}: {response_text}",
            file=sys.stderr,
        )
        return 1

    print(format_report(since, until, events_by_run, events_outside_runs, labels))
    return 0


def _parse_window(argv: Sequence[str] | None) -> tuple[datetime, datetime]:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--since",
        type=_parse_utc_time,
        help="start of the window, an ISO 8601 date or time, UTC unless it gives an offset; "
        "default: 7 days before --until",
    )
    parser.add_argument(
        "--until",
        type=_parse_utc_time,
        help="end of the window, excluded; default: now",
    )
    arguments = parser.parse_args(argv)

    until: datetime = arguments.until or datetime.now(UTC)
    since: datetime = arguments.since or until - DEFAULT_WINDOW
    if since >= until:
        parser.error(
            f"--since ({since:%Y-%m-%d %H:%M} UTC) must be before --until ({until:%Y-%m-%d %H:%M} UTC)"
        )
    return since, until


def _parse_utc_time(text: str) -> datetime:
    try:
        time = datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not an ISO 8601 date or time, such as 2026-09-26 or 2026-09-26T13:00Z"
        ) from None
    return time.replace(tzinfo=UTC) if time.tzinfo is None else time.astimezone(UTC)


def fetch_usage_events(
    api_key: str, since: datetime, until: datetime
) -> list[UsageEvent]:
    """Fetch every team usage event from ``since`` up to, but excluding, ``until``.

    Args:
        api_key: a Cursor team Admin API key.
        since: start of the window, included; timezone-aware.
        until: end of the window, excluded; timezone-aware.

    Returns:
        The events as the Admin API returns them, newest first.

    Raises:
        urllib.error.HTTPError: the Admin API rejected a request, for example
            with 401 for an invalid key or 429 above 60 requests a minute.
        urllib.error.URLError: the Admin API could not be reached.
    """
    credentials = base64.b64encode(f"{api_key}:".encode()).decode()
    window = {
        "startDate": _epoch_ms(since),
        # endDate is inclusive, so a window that ends where the next starts
        # stops a millisecond short to count no event twice.
        "endDate": _epoch_ms(until) - 1,
    }
    events: list[UsageEvent] = []
    page = 1
    while True:
        request = urllib.request.Request(
            USAGE_EVENTS_URL,
            data=json.dumps(
                {**window, "page": page, "pageSize": EVENTS_PER_PAGE}
            ).encode(),
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
            response_body = json.load(response)
        events += response_body["usageEvents"]
        if not response_body["pagination"]["hasNextPage"]:
            return events
        page += 1


def _epoch_ms(time: datetime) -> int:
    return (time - UNIX_EPOCH) // timedelta(milliseconds=1)


def fetch_run_labels(api_key: str, run_ids: set[str]) -> dict[str, RunLabel]:
    """Label cloud agent runs with their task, repository, and branch.

    Reads the Cloud Agents API's agent listing, newest first, and stops at the
    page where the last of ``run_ids`` is found, or after ``MAX_LISTING_PAGES``
    pages, so a missing run does not read every agent the team ever started.

    Args:
        api_key: a Cursor user or service account API key; a team Admin API key
            is rejected.
        run_ids: the IDs (``bc-...``) of the runs to label.

    Returns:
        A label for each ID in ``run_ids``; ``UNKNOWN_RUN_LABEL`` for an ID
        not in the newest ``MAX_LISTING_PAGES`` pages of the listing.

    Raises:
        urllib.error.HTTPError: the Cloud Agents API rejected a request.
        urllib.error.URLError: the Cloud Agents API could not be reached.
    """
    credentials = base64.b64encode(f"{api_key}:".encode()).decode()
    labels: dict[str, RunLabel] = {}
    cursor: str | None = None
    for _ in range(MAX_LISTING_PAGES):
        if len(labels) == len(run_ids):
            break
        query = {"limit": AGENTS_PER_PAGE, **({"cursor": cursor} if cursor else {})}
        request = urllib.request.Request(
            f"{AGENTS_URL}?{urllib.parse.urlencode(query)}",
            headers={"Authorization": f"Basic {credentials}"},
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
            response_body = json.load(response)
        for agent in response_body["agents"]:
            if agent["id"] in run_ids:
                labels[agent["id"]] = RunLabel(
                    task=agent.get("name") or UNKNOWN_LABEL,
                    repository=agent.get("source", {}).get("repository")
                    or UNKNOWN_LABEL,
                    branch_name=agent.get("target", {}).get("branchName")
                    or UNKNOWN_LABEL,
                )
        cursor = response_body.get("nextCursor")
        if not cursor:
            break
    return {run_id: labels.get(run_id, UNKNOWN_RUN_LABEL) for run_id in run_ids}


def split_by_run(
    events: list[UsageEvent],
) -> tuple[dict[str, list[UsageEvent]], list[UsageEvent]]:
    """Group usage events by the cloud agent run they came from.

    Args:
        events: usage events as the Admin API returns them.

    Returns:
        A map from each cloud agent run's ID (``bc-...``) to its events, and
        the events that came from no cloud agent run.
    """
    events_by_run: dict[str, list[UsageEvent]] = {}
    events_outside_runs: list[UsageEvent] = []
    for event in events:
        run_id = event.get("cloudAgentId")
        if run_id:
            events_by_run.setdefault(run_id, []).append(event)
        else:
            events_outside_runs.append(event)
    return events_by_run, events_outside_runs


def format_report(
    since: datetime,
    until: datetime,
    events_by_run: dict[str, list[UsageEvent]],
    events_outside_runs: list[UsageEvent],
    labels: dict[str, RunLabel] | None = None,
) -> str:
    """Format usage as a Markdown table of cloud agent runs and a table of totals.

    Args:
        since: start of the window, in UTC.
        until: end of the window, excluded, in UTC.
        events_by_run: each cloud agent run's events, by run ID.
        events_outside_runs: the events that came from no cloud agent run.
        labels: each run's label, by run ID, which must have every run in
            ``events_by_run``; ``None`` if the labels are unavailable.

    Returns:
        The report: a title line, one row per run in descending order of cost,
        then totals for all runs, for each repository in descending order of
        cost, for usage outside the runs, and for all usage. With ``labels``
        ``None``, the runs have no task, repository, or branch columns, there
        are no repository totals, and a line after the title says why.
    """
    usage_by_run = {
        run_id: Usage.total(events) for run_id, events in events_by_run.items()
    }
    runs_by_cost = sorted(
        usage_by_run.items(), key=lambda run: run[1].charged_cents, reverse=True
    )
    run_events = [event for events in events_by_run.values() for event in events]
    totals = {
        f"All {len(usage_by_run)} cloud agent runs": Usage.total(run_events),
        **(_repository_totals(events_by_run, labels) if labels is not None else {}),
        "Usage outside cloud agent runs": Usage.total(events_outside_runs),
        "All usage": Usage.total(run_events + events_outside_runs),
    }

    label_columns = "Task | Repository | Branch | " if labels is not None else ""
    label_alignment = "---|---|---|" if labels is not None else ""
    run_rows = [
        f"| {run_id} | {_format_labels(labels[run_id]) if labels is not None else ''}"
        f"{usage.first_event_time:%Y-%m-%d %H:%M} | {', '.join(usage.models)} | {_format_counts(usage)} |"
        for run_id, usage in runs_by_cost
    ]
    total_rows = [
        f"| {label} | {_format_counts(usage)} |" for label, usage in totals.items()
    ]
    return "\n".join(
        [
            f"Cursor usage from {since:%Y-%m-%d %H:%M} UTC up to {until:%Y-%m-%d %H:%M} UTC.",
            *(
                []
                if labels is not None
                else [
                    f"Task and repository labels need {AGENTS_KEY_VARIABLE}, which is not set."
                ]
            ),
            "",
            f"| Cloud agent run | {label_columns}First event (UTC) | Models | {COUNT_COLUMNS} |",
            f"|---|{label_alignment}---|---|{COUNT_ALIGNMENT}|",
            *run_rows,
            "",
            f"| Total | {COUNT_COLUMNS} |",
            f"|---|{COUNT_ALIGNMENT}|",
            *total_rows,
        ]
    )


def _repository_totals(
    events_by_run: dict[str, list[UsageEvent]], labels: dict[str, RunLabel]
) -> dict[str, Usage]:
    run_ids_by_repository: dict[str, list[str]] = {}
    for run_id in events_by_run:
        run_ids_by_repository.setdefault(labels[run_id].repository, []).append(run_id)

    usage_by_repository = {
        repository: Usage.total(
            [event for run_id in run_ids for event in events_by_run[run_id]]
        )
        for repository, run_ids in run_ids_by_repository.items()
    }
    repositories_by_cost = sorted(
        usage_by_repository,
        key=lambda repository: usage_by_repository[repository].charged_cents,
        reverse=True,
    )
    return {
        f"Repository {repository}, {_count_runs(len(run_ids_by_repository[repository]))}": usage_by_repository[
            repository
        ]
        for repository in repositories_by_cost
    }


def _count_runs(run_count: int) -> str:
    return f"{run_count} run" if run_count == 1 else f"{run_count} runs"


def _format_labels(label: RunLabel) -> str:
    cells = [label.task, label.repository, label.branch_name]
    escaped_cells = [cell.replace("|", "\\|") for cell in cells]
    return "".join(f"{cell} | " for cell in escaped_cells)


def _format_counts(usage: Usage) -> str:
    counts = [
        usage.event_count,
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_write_tokens,
        usage.cache_read_tokens,
    ]
    return " | ".join(
        [*(f"{count:,}" for count in counts), f"{usage.charged_cents / 100:,.2f}"]
    )


@dataclass(frozen=True)
class Usage:
    """Token and cost totals of a set of usage events.

    Attributes:
        event_count: number of usage events. The Admin API aggregates a
            conversation's requests into events, so this is not a request
            count.
        input_tokens: prompt tokens not read from or written to the cache.
        output_tokens: tokens the model generated.
        cache_write_tokens: prompt tokens written to the cache.
        cache_read_tokens: prompt tokens read from the cache.
        charged_cents: sum of the events' ``chargedCents``, in US cents.
        models: the models the events used, sorted by name.
        first_event_time: time of the earliest event, in UTC; ``None`` if
            there are no events.
    """

    event_count: int
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    charged_cents: float
    models: list[str]
    first_event_time: datetime | None

    @classmethod
    def total(cls, events: list[UsageEvent]) -> Self:
        """Total usage events as the Admin API returns them.

        Args:
            events: usage events; each has ``timestamp`` (epoch milliseconds,
                as a string), ``model``, and ``chargedCents``, and has
                ``tokenUsage`` only if it was billed by tokens.

        Returns:
            The events' totals.
        """
        token_counts = [
            event["tokenUsage"] for event in events if "tokenUsage" in event
        ]
        return cls(
            event_count=len(events),
            input_tokens=sum(tokens["inputTokens"] for tokens in token_counts),
            output_tokens=sum(tokens["outputTokens"] for tokens in token_counts),
            cache_write_tokens=sum(
                tokens["cacheWriteTokens"] for tokens in token_counts
            ),
            cache_read_tokens=sum(tokens["cacheReadTokens"] for tokens in token_counts),
            charged_cents=sum(event["chargedCents"] for event in events),
            models=sorted({event["model"] for event in events}),
            first_event_time=min(
                (
                    UNIX_EPOCH + timedelta(milliseconds=int(event["timestamp"]))
                    for event in events
                ),
                default=None,
            ),
        )


if __name__ == "__main__":
    sys.exit(main())
