"""web_backend package.

This package groups the Flask web-layer modules so the entrypoint stays small.

Variables and functionality summary:
- The package exposes no runtime globals directly.
- Import concrete modules (`environment`, `routes`, `services`, `job_state`, `parsing`)
  to access shared paths, DB objects, request parsing helpers, and route wiring.
"""
