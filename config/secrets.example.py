"""
Secrets template — copy this file to `secrets.py` and add your actual keys.

`secrets.py` is gitignored. Do NOT commit your real API keys.

Setup:
    cp config/secrets.example.py config/secrets.py
    # Then edit config/secrets.py with your real keys.
"""

# Polygon.io / Massive API key
# Get from: https://massive.com/dashboard/keys
POLYGON_API_KEY: str = "REPLACE_WITH_YOUR_POLYGON_API_KEY"

# Optional: Tradier API for live signal validation post-backtest
# Get from: https://documentation.tradier.com/
TRADIER_API_KEY: str = ""

# Optional: GitHub PAT for pushing automation outputs
GITHUB_PAT: str = ""
