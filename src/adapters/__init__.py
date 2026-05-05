"""Data-source adapters.

Each adapter exposes a small, uniform API for loading historical option chains
from a specific vendor (Polygon, ORATS, ...). Discovery / simulation code stays
vendor-agnostic by depending on the adapter API rather than the vendor's
native client.
"""
