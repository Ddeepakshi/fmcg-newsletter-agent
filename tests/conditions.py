"""Shared skip-condition helpers for tests that need real network/API access.

Not a test module itself (no test_ prefix) — imported by the individual
per-file test modules to decide whether to skip a real-network/real-API
check versus run it for real.
"""
import socket

import config


def has_network(timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=timeout):
            return True
    except OSError:
        return False


def has_groq_key() -> bool:
    return bool(config.GROQ_API_KEY)
