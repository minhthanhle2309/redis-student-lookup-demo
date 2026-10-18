"""Redis-backed server-side sessions used only by the session demonstration."""

import hashlib
import json
import os
import secrets

SESSION_PREFIX = "seminar:session:"
PASSWORD_SALT = b"soa-seminar-demo-v1"
# PBKDF2-HMAC-SHA256 hash of the classroom demo password ``redis123``.
DEFAULT_PASSWORD_HASH = "eb0666d3004137d35dc4b20a505fd5fd181a9d94ff1003e98a1b23c786ac3d85"


class SessionStore:
    def __init__(self, redis_client, ttl=None):
        self.redis = redis_client
        self.ttl = int(ttl if ttl is not None else os.getenv("SESSION_TTL_SECONDS", "45"))
        if self.ttl < 1:
            raise ValueError("SESSION_TTL_SECONDS must be at least 1")

    @staticmethod
    def key(session_id):
        return SESSION_PREFIX + session_id

    def create(self, username):
        session_id = secrets.token_urlsafe(32)
        state = {"username": username}
        self.redis.setex(self.key(session_id), self.ttl, json.dumps(state))
        return session_id

    def get(self, session_id):
        if not session_id:
            return None
        raw = self.redis.get(self.key(session_id))
        return json.loads(raw) if raw else None

    def ttl_remaining(self, session_id):
        return self.redis.ttl(self.key(session_id)) if session_id else -2

    def delete(self, session_id):
        return bool(self.redis.delete(self.key(session_id))) if session_id else False


def verify_demo_credentials(username, password):
    expected_user = os.getenv("SESSION_DEMO_USERNAME", "demo")
    expected_hash = os.getenv("SESSION_PASSWORD_HASH", DEFAULT_PASSWORD_HASH)
    actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), PASSWORD_SALT, 310_000).hex()
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(actual_hash, expected_hash)
