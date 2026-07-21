import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from urllib.parse import urlsplit

from fastapi import Request
from itsdangerous import BadSignature, URLSafeSerializer

from backend.app.config import Settings
from backend.app.errors import ApiError

SESSION_COOKIE = "prefine_session"
SESSION_SALT = "prefine-session-v1"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURE_LIMIT = 5


@dataclass(frozen=True)
class SessionPrincipal:
    username: str


class AuthService:
    """Authenticates the environment-defined administrator and signs sessions."""

    def __init__(
        self,
        settings: Settings,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self._now = now or (lambda: datetime.now(UTC))
        self._serializer = URLSafeSerializer(
            settings.session_secret.get_secret_value(),
            salt=SESSION_SALT,
        )
        self._failures: dict[str, deque[datetime]] = defaultdict(deque)
        self._failure_lock = Lock()

    def authenticate(self, client_ip: str, username: str, password: str) -> str:
        now = self._now()
        with self._failure_lock:
            attempts = self._active_failures(client_ip, now)
            if len(attempts) >= LOGIN_FAILURE_LIMIT:
                raise ApiError(
                    status_code=429,
                    code="login_rate_limited",
                    message="登录失败次数过多，请稍后再试",
                )

        username_matches = secrets.compare_digest(username, self.settings.admin_username)
        password_matches = secrets.compare_digest(
            password,
            self.settings.admin_password.get_secret_value(),
        )
        if not (username_matches and password_matches):
            with self._failure_lock:
                self._active_failures(client_ip, now).append(now)
            raise ApiError(
                status_code=401,
                code="invalid_credentials",
                message="用户名或密码错误",
            )

        with self._failure_lock:
            self._failures.pop(client_ip, None)
        expires_at = now + timedelta(seconds=SESSION_MAX_AGE_SECONDS)
        return self._serializer.dumps(
            {
                "username": self.settings.admin_username,
                "expires_at": int(expires_at.timestamp()),
            }
        )

    def verify_session(self, token: str | None) -> SessionPrincipal:
        if not token:
            raise _authentication_required()
        try:
            payload = self._serializer.loads(token)
            username = payload["username"]
            expires_at = int(payload["expires_at"])
        except (BadSignature, KeyError, TypeError, ValueError) as error:
            raise _authentication_required() from error

        if not isinstance(username, str) or not secrets.compare_digest(
            username, self.settings.admin_username
        ):
            raise _authentication_required()
        if int(self._now().timestamp()) > expires_at:
            raise _authentication_required()
        return SessionPrincipal(username=username)

    def _active_failures(self, client_ip: str, now: datetime) -> deque[datetime]:
        attempts = self._failures[client_ip]
        cutoff = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def require_session(request: Request) -> SessionPrincipal:
    service = get_auth_service(request)
    return service.verify_session(request.cookies.get(SESSION_COOKIE))


def require_same_origin(request: Request) -> None:
    """Reject a supplied Origin that does not match the request Host."""

    source = request.headers.get("origin") or request.headers.get("referer")
    request_host = request.headers.get("host", "").lower()
    if source is None:
        fetch_site = request.headers.get("sec-fetch-site")
        if fetch_site is None:
            return  # Non-browser API clients do not always send browser source headers.
        if fetch_site == "same-origin":
            return
        raise _origin_not_allowed()

    parsed = urlsplit(source)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request_host:
        raise _origin_not_allowed()


def client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _authentication_required() -> ApiError:
    return ApiError(
        status_code=401,
        code="authentication_required",
        message="请先登录",
    )


def _origin_not_allowed() -> ApiError:
    return ApiError(
        status_code=403,
        code="origin_not_allowed",
        message="请求来源不受信任",
    )
