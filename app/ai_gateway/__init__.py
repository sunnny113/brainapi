"""BrainAPI AI Gateway

This package implements BrainAPI's multi-provider routing layer.

Key concepts:
- Provider abstraction (`providers.*`)
- Routing + fallback (`router.py`)
- Unified endpoint schema (`types.py`)

The legacy endpoints in app.main keep working and can gradually migrate to this gateway.
"""
