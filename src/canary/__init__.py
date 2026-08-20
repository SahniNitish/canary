"""Canary — a supervision layer that proves a recall scraper is still telling the truth.

The health engine (`canary.signals`) makes zero network calls: it takes run data in and
emits signals out. All network I/O lives behind the `bdata` CLI, wrapped in `canary.runner`.
"""

__version__ = "0.1.0"
