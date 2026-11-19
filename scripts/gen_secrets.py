#!/usr/bin/env python3
"""Print fresh JWT_SECRET and MASTER_KEY_HEX values for backend/.env."""
import secrets

print("JWT_SECRET=" + secrets.token_urlsafe(48))
print("MASTER_KEY_HEX=" + secrets.token_hex(32))
