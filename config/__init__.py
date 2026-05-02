"""Configuration package for the Forward Factor backtester.

Exports `settings` (public) and lazily loads `secrets` (gitignored) on first import.
"""
from . import settings

__all__ = ["settings"]
