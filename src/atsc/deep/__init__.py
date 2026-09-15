"""Layer 2: paid, RAG-grounded deep report.

Only `atsc.deep.generation` (and the worker that drives it) may import the
Anthropic SDK. Routes that live in the web process (checkout, report viewing)
must not.
"""
