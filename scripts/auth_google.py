"""CLI script to bootstrap Google OAuth 2.0 `token.json`."""

import argparse
import os
from pathlib import Path

from src.integrations.google_auth import run_oauth_bootstrap


def _resolve_default_paths() -> tuple[Path, Path]:
    """Resolve credential paths from environment variables with local defaults."""
    creds_env = os.getenv("GOOGLE_CREDENTIALS_PATH")
    token_env = os.getenv("GOOGLE_TOKEN_PATH")
    creds_path = Path(creds_env) if creds_env else Path("credentials/credentials.json")
    token_path = Path(token_env) if token_env else Path("credentials/token.json")
    return creds_path, token_path


def main() -> None:
    """Parse CLI arguments and run the interactive Google OAuth 2.0 flow."""
    default_creds, default_token = _resolve_default_paths()

    parser = argparse.ArgumentParser(
        description="Bootstrap Google OAuth 2.0 token.json for Calendar, Sheets, and Drive."
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=default_creds,
        help=(
            "Path to OAuth client secrets JSON "
            "(default: GOOGLE_CREDENTIALS_PATH or credentials/credentials.json)."
        ),
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=default_token,
        help="Output path for token.json (default: GOOGLE_TOKEN_PATH or credentials/token.json).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open a browser window; print the authorization URL instead.",
    )
    args = parser.parse_args()

    run_oauth_bootstrap(
        credentials_path=args.credentials,
        token_path=args.token,
        open_browser=not args.no_browser,
    )
    print(f"Google OAuth token saved successfully to: {args.token}")


if __name__ == "__main__":
    main()
