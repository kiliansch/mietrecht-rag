"""FastAPI layer over the Mietrecht agent.

A thin HTTP adapter: every endpoint imports and calls the same UI-agnostic Python the
CLI does (graph, contracts, memory, feedback, eval). No agent/tool/contract/eval logic
is reimplemented here. The React frontend in `frontend/` consumes this API.
"""
