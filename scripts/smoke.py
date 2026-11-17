"""Exercise a running same-origin Compose stack using only the standard library."""

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.request
import uuid

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ""


def call(path, body=None, method=None):
    request = urllib.request.Request(
        base + "/api/v1" + path,
        method=method,
        headers={"Origin": base, "Content-Type": "application/json", "X-CSRF-Token": csrf},
        data=json.dumps(body).encode() if body is not None else None,
    )
    with client.open(request, timeout=10) as response:
        assert response.headers["X-Request-ID"]
        data = response.read()
        return json.loads(data) if data else None


assert call("/health/ready")["status"] == "ready"
assert len(call("/catalog/vocabulary")["entries"]) == 1000
assert len(call("/catalog/listening")["entries"]) == 30
csrf = call("/auth/csrf")["csrf_token"]
email = f"smoke-{uuid.uuid4().hex}@example.com"
credentials = {"email": email, "password": uuid.uuid4().hex}
csrf = call("/auth/register", credentials)["csrf_token"]
payload = {
    "event_id": str(uuid.uuid4()),
    "entry_id": "word-0001",
    "kind": "quiz",
    "answer": "word-0001",
}
assert call("/progress/events", payload)["record"]["attempts"] == 1
assert call("/progress/events", payload)["record"]["attempts"] == 1
call("/auth/logout", method="POST")
csrf = call("/auth/csrf")["csrf_token"]
csrf = call("/auth/login", credentials)["csrf_token"]
assert call("/progress")["records"][0]["attempts"] == 1
call("/auth/logout", method="POST")
for path in ["/", "/listening", "/login", "/progress"]:
    with client.open(base + path, timeout=10) as response:
        html = response.read().decode()
        assert '<div id="root">' in html
        if "X-Content-Type-Options" in response.headers:  # Nginx production profile
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
            with client.open(base + asset, timeout=10) as resource:
                assert "immutable" in resource.headers.get("Cache-Control", "")
print(
    "Passed: same-origin catalog, registration/login/logout, idempotent saving, persisted progress, SPA routes and assets"
)
