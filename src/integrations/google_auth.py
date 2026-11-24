"""Google OAuth 2.0 credential loading, refresh, and bootstrap helpers."""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

GOOGLE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
)


def load_google_credentials(
    credentials_path: Path,
    token_path: Path,
) -> Credentials:
    """Load OAuth 2.0 credentials from `token_path`, refreshing automatically if expired."""
    if not token_path.exists():
        raise FileNotFoundError(
            f"Google OAuth token not found at '{token_path}'. "
            "Run 'python -m scripts.auth_google' to authorize."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), list(GOOGLE_SCOPES))
    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials file not found at '{credentials_path}'."
        )

    raise RuntimeError(
        "Google OAuth token is invalid or missing a refresh token. "
        "Re-run 'python -m scripts.auth_google' to re-authorize."
    )


def run_oauth_bootstrap(
    credentials_path: Path,
    token_path: Path,
    *,
    open_browser: bool = True,
) -> Credentials:
    """Run interactive OAuth 2.0 flow and persist `token.json` with refresh token."""
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google OAuth client secrets not found at '{credentials_path}'."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path),
        list(GOOGLE_SCOPES),
    )
    creds = flow.run_local_server(port=0, open_browser=open_browser)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
