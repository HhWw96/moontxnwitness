# Frozen ORM plan regression inputs

These three Python snapshots are the repository's original experimental ORM
policy, cursor and lifecycle implementations. They preserve the previous SQL
templates, result decoding and driver surface for regression comparison with
the standalone package. They are not loaded by production code.

Original source bindings and the first candidate comparison are retained in
the v0.1.3 development evidence. Run `python -B scripts/orm-unit-test.py` with
the optional dependencies from `examples/orm-requirements.txt`.
