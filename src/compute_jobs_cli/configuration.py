"""Checks that the shared SkyPilot API server is configured, before any SkyPilot call."""

import ipaddress
import socket
from collections.abc import Mapping
from urllib.parse import urlparse

from compute_jobs_cli.kinds import CommandFailure, FailureKind

ENDPOINT_VARIABLE = "SKYPILOT_API_SERVER_ENDPOINT"
TOKEN_VARIABLE = "SKYPILOT_SERVICE_ACCOUNT_TOKEN"

# Contract v0's message. SkyPilot's client with no endpoint starts a local API
# server, so each check below must fail before the first SkyPilot call.
_NOT_CONFIGURED_MESSAGE = (
    "{problem}, so no job can be launched or\n"
    "observed. This project is a client of a shared SkyPilot API server: ask the\n"
    f"owner to add {ENDPOINT_VARIABLE} and {TOKEN_VARIABLE}\n"
    "as Cursor secrets. The server is run with the compute-server-admin skill;\n"
    "an agent never starts one. Nothing was started."
)


def check_server_configuration(environment: Mapping[str, str]) -> None:
    """Fail unless the environment names a remote https:// server and a token.

    This makes no network call, not even a DNS lookup, so it never starts a
    SkyPilot API server. The token is never copied into a message.

    Args:
        environment: Variables to read, normally ``os.environ``.

    Raises:
        CommandFailure: With kind ``not_configured`` when the endpoint is
            unset or empty, isn't an ``https://`` URL, or points at this
            machine, or when the token is unset or empty. The endpoint is
            checked first.

    Example:
        >>> check_server_configuration(
        ...     {ENDPOINT_VARIABLE: "https://jobs.example.org", TOKEN_VARIABLE: "t"}
        ... )
        >>> try:
        ...     check_server_configuration({TOKEN_VARIABLE: "t"})
        ... except CommandFailure as failure:
        ...     print(failure.kind)
        not_configured
    """
    problem = _find_configuration_problem(environment)
    if problem is not None:
        raise CommandFailure(
            FailureKind.NOT_CONFIGURED, _NOT_CONFIGURED_MESSAGE.format(problem=problem)
        )


def _find_configuration_problem(environment: Mapping[str, str]) -> str | None:
    endpoint = environment.get(ENDPOINT_VARIABLE, "")
    if not endpoint:
        return f"{ENDPOINT_VARIABLE} is not set"

    parsed_endpoint = urlparse(endpoint)
    if parsed_endpoint.scheme != "https" or not parsed_endpoint.hostname:
        return f"{ENDPOINT_VARIABLE} is {endpoint!r}, which isn't an https:// URL"
    if _is_this_machine(parsed_endpoint.hostname):
        return f"{ENDPOINT_VARIABLE} is {endpoint!r}, which points at this machine"

    if not environment.get(TOKEN_VARIABLE, ""):
        return f"{TOKEN_VARIABLE} is not set"
    return None


def _is_this_machine(hostname: str) -> bool:
    hostname = hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    if hostname == socket.gethostname().lower():
        return True
    address = _parse_address(hostname)
    return address is not None and (address.is_loopback or address.is_unspecified)


def _parse_address(
    hostname: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass
    # The system resolver also reads shortened IPv4 forms such as "127.1".
    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except OSError:
        return None
