import re
import time
import uuid
import threading
from contextvars import ContextVar
from typing import Optional, Tuple, Dict, List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# Context variable for request correlation tracing
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

def get_current_request_id() -> str:
    rid = request_id_ctx.get()
    if not rid:
        rid = f"REQ-{uuid.uuid4().hex[:12].upper()}"
        request_id_ctx.set(rid)
    return rid


# =====================================================================
# 1. 21 CFR PART 11 / GAMP 5 PASSWORD COMPLEXITY VALIDATOR
# =====================================================================
COMMON_WEAK_PASSWORDS = {
    "password", "password123", "admin", "admin123", "operator", "operator123",
    "12345678", "123456789", "qwerty123", "pharma123", "letmein123"
}

def validate_password_complexity(password: str) -> Tuple[bool, Optional[str]]:
    """
    Enforces 21 CFR Part 11 / FDA electronic signature password strength standards:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 numeric digit
    - At least 1 special character
    - Not in known weak password dictionary
    """
    if not password:
        return False, "Password cannot be empty."

    if len(password) < 8:
        return False, "Password must be at least 8 characters in length per 21 CFR Part 11."

    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."

    stripped_word = re.sub(r'^[^a-zA-Z]+|[^a-zA-Z]+$', '', password.lower())
    if password.lower() in COMMON_WEAK_PASSWORDS or stripped_word in COMMON_WEAK_PASSWORDS:
        return False, "Password is too common or easily guessable. Please choose a stronger passphrase."

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter (a-z)."

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter (A-Z)."

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one numeric digit (0-9)."

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password):
        return False, "Password must contain at least one special character (!@#$%^&*...)."

    return True, None


# =====================================================================
# 2. IN-MEMORY SLIDING WINDOW RATE LIMITER
# =====================================================================
class SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter designed for plant intranet and cloud deployments.
    Tracks request timestamps per IP and blocks excessive requests with standard 429 Retry-After.
    """
    def __init__(self, cleanup_interval: int = 300):
        self._lock = threading.Lock()
        self._hits: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = cleanup_interval

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        """
        Returns:
            (allowed: bool, remaining_requests: int, retry_after_seconds: int)
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Periodic memory garbage collection
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup(cutoff)
                self._last_cleanup = now

            timestamps = self._hits.get(key, [])
            # Filter hits within current sliding window
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= max_requests:
                # Calculate remaining wait time until earliest request expires
                oldest_hit = valid_timestamps[0]
                retry_after = max(1, int(oldest_hit + window_seconds - now))
                self._hits[key] = valid_timestamps
                return False, 0, retry_after

            valid_timestamps.append(now)
            self._hits[key] = valid_timestamps
            remaining = max(0, max_requests - len(valid_timestamps))
            return True, remaining, 0

    def _cleanup(self, cutoff: float):
        keys_to_delete = []
        for k, timestamps in self._hits.items():
            valid = [t for t in timestamps if t > cutoff]
            if not valid:
                keys_to_delete.append(k)
            else:
                self._hits[k] = valid
        for k in keys_to_delete:
            del self._hits[k]

    def reset(self):
        """Clears rate limiter state (useful in testing)."""
        with self._lock:
            self._hits.clear()


# Global rate limiter instance
global_rate_limiter = SlidingWindowRateLimiter()


# =====================================================================
# 3. REQUEST TRACING & CORRELATION MIDDLEWARE
# =====================================================================
class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Assigns or propagates a unique X-Request-ID to every HTTP transaction,
    enabling end-to-end audit tracing, structured logging, and forensic analysis.
    """
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"

        token = request_id_ctx.set(req_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)


# =====================================================================
# 4. OWASP SECURE HEADERS MIDDLEWARE
# =====================================================================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects enterprise-grade OWASP security headers to prevent XSS, clickjacking,
    MIME-sniffing, and insecure framing across packaging line terminals and browsers.
    """
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Defend against clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Cross-Site Scripting protection filter
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict hardware features not needed by serialization portal
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # Content Security Policy (allows local inline scripts and styles required by single-page portal)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';"
        )

        return response


# =====================================================================
# 5. AUTH RATE LIMITING MIDDLEWARE
# =====================================================================
class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Protects authentication endpoints from automated password-spraying and DDoS.
    Applies stricter limits to login (e.g. 15 attempts / minute per IP).
    """
    def __init__(self, app, login_limit_per_minute: int = 15):
        super().__init__(app)
        self.login_limit = login_limit_per_minute

    async def dispatch(self, request: Request, call_next):
        # Only rate limit the login endpoint
        if request.url.path == "/api/v1/auth/login" and request.method == "POST":
            # Extract client IP (handling reverse proxy X-Forwarded-For if present)
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
            else:
                client_ip = request.client.host if request.client else "unknown_ip"

            allowed, remaining, retry_after = global_rate_limiter.is_allowed(
                key=f"auth_login:{client_ip}",
                max_requests=self.login_limit,
                window_seconds=60
            )

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Too many authentication attempts. Please wait {retry_after} seconds before trying again.",
                        "retry_after": retry_after,
                        "request_id": get_current_request_id()
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-Request-ID": get_current_request_id()
                    }
                )

        return await call_next(request)
