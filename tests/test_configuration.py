import socket

import pytest

from compute_jobs_cli.configuration import (
    ENDPOINT_VARIABLE,
    TOKEN_VARIABLE,
    check_server_configuration,
)
from compute_jobs_cli.kinds import CommandFailure, FailureKind


def environment_with(endpoint: str) -> dict[str, str]:
    return {ENDPOINT_VARIABLE: endpoint, TOKEN_VARIABLE: "token-value"}


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://localhost",
        "https://LOCALHOST.:8443",
        "https://skypilot.localhost",
        "https://127.0.0.1",
        "https://127.1",
        "https://127.255.0.3:8443/api",
        "https://0.0.0.0",
        "https://[::1]",
        "https://[::]",
        "https://[::ffff:127.0.0.1]",
        f"https://{socket.gethostname()}",
    ],
)
def test_an_endpoint_that_points_at_this_machine_is_not_configured(
    endpoint: str,
) -> None:
    with pytest.raises(CommandFailure, match="points at this machine") as failure:
        check_server_configuration(environment_with(endpoint))

    assert failure.value.kind is FailureKind.NOT_CONFIGURED


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://jobs.example.org",
        "jobs.example.org",
        "https://",
        "ftp://x",
        "http://{staging}.example.org",
    ],
)
def test_an_endpoint_that_is_not_an_https_url_is_not_configured(endpoint: str) -> None:
    with pytest.raises(CommandFailure, match="isn't an https:// URL"):
        check_server_configuration(environment_with(endpoint))


@pytest.mark.parametrize(
    "endpoint",
    ["https://jobs.example.org", "https://203.0.113.7:8443", "https://[2001:db8::1]"],
)
def test_a_remote_https_endpoint_with_a_token_is_configured(endpoint: str) -> None:
    check_server_configuration(environment_with(endpoint))


def test_a_missing_token_names_the_token_variable() -> None:
    with pytest.raises(CommandFailure, match=f"{TOKEN_VARIABLE} is not set"):
        check_server_configuration({ENDPOINT_VARIABLE: "https://jobs.example.org"})
