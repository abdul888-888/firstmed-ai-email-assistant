#!/usr/bin/env python3
"""Generate password hash for ITU@888888"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

password = "ITU@888888"
hashed = pwd_context.hash(password)
print(f"Password hash for '{password}':")
print(hashed)