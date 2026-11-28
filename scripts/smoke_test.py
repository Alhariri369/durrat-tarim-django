"""Post-deploy HTTP smoke test for Durrat Tarim endpoints and static assets."""

from __future__ import annotations

import argparse
import sys
import time
from urllib.parse import urljoin

import requests

DEFAULT_BASE_URL = "https://durrat-tarim-dev.vercel.app"
DEFAULT_TIMEOUT = 15.0

SMOKE_ENDPOINTS = (
    "/",
    "/products/",
    "/products/types/",
    "/products/search/",
    "/contact/",
    "/admin/login/",
    "/sitemap.xml",
    "/robots.txt",
    "/static/css/output.css",
    "/static/images/product-placeholder.svg",
)

ERROR_SIGNATURES = (
    "Server Error (500)",
    "Internal Server Error",
    "Traceback (most recent call last):",
    "DisallowedHost",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify live HTTP 200 and non-empty, non-500 responses across key routes."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the deployed site (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    return parser.parse_args(argv)


def check_endpoint(
    session: requests.Session,
    base_url: str,
    path: str,
    timeout: float,
) -> tuple[bool, str]:
    normalized_base = base_url.rstrip("/") + "/"
    url = urljoin(normalized_base, path.lstrip("/"))
    start = time.monotonic()

    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return False, f"FAIL {path} ({elapsed_ms}ms) - request error: {exc}"

    elapsed_ms = int((time.monotonic() - start) * 1000)
    body_bytes = response.content or b""

    if response.status_code != 200:
        return (
            False,
            f"FAIL {path} -> HTTP {response.status_code} ({len(body_bytes)}B, {elapsed_ms}ms)",
        )

    if not body_bytes.strip():
        return (
            False,
            f"FAIL {path} -> HTTP 200 with empty body ({elapsed_ms}ms)",
        )

    content_type = (response.headers.get("Content-Type") or "").lower()
    if any(
        token in content_type
        for token in ("text/", "html", "xml", "json", "javascript", "svg")
    ):
        text = response.text
        for signature in ERROR_SIGNATURES:
            if signature in text:
                return (
                    False,
                    f"FAIL {path} -> HTTP 200 contained error signature {signature!r} ({elapsed_ms}ms)",
                )

    return (
        True,
        f"PASS {path} -> HTTP {response.status_code} ({len(body_bytes)}B, {elapsed_ms}ms)",
    )


def run_smoke_tests(base_url: str, timeout: float) -> int:
    print(f"Running smoke tests against {base_url} (timeout={timeout}s)")
    failures = 0

    with requests.Session() as session:
        session.headers.update({"User-Agent": "durrat-tarim-smoke-test/1.0"})
        for path in SMOKE_ENDPOINTS:
            ok, message = check_endpoint(session, base_url, path, timeout)
            print(message)
            if not ok:
                failures += 1

    total = len(SMOKE_ENDPOINTS)
    if failures:
        print(f"\nSmoke test FAILED: {failures}/{total} endpoint(s) failed.", file=sys.stderr)
        return 1

    print(f"\nSmoke test PASSED: {total}/{total} endpoints healthy.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_smoke_tests(base_url=args.base_url, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
