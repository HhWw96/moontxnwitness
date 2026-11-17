"""Exact current V2 window runtime closure, independent of the frozen V1 slots."""
from hashlib import sha256
from pathlib import Path


CONFIGURED_WINDOW_V2_WRAPPERS = (
    'configured-window-v2.mjs', 'configured-window-v2-host.mjs',
    'configured-window-v2-standalone.mjs',
)
CONFIGURED_WINDOW_V2_RUNTIME = ('sql-projection-v2-core.mjs', *CONFIGURED_WINDOW_V2_WRAPPERS)
STRUCTURED_WINDOW_WRAPPERS = ('configured-window-v2-structured.mjs',)
STRUCTURED_WINDOW_RUNTIME = ('structured-window-verification-core.mjs', *STRUCTURED_WINDOW_WRAPPERS)


def configured_window_v2_available(root):
    return (Path(root) / 'cmd/configured-window-v2.mjs').is_file()


def structured_window_available(root):
    """The explicit profile is separate from default SDK capability availability."""
    return (Path(root) / 'cmd/configured-window-v2-structured.mjs').is_file()


def verify_configured_window_v2_runtime(root, manifest):
    """Reject missing/stale/extra slots and wrappers changed after compilation."""
    root = Path(root)
    slots = manifest.get('configuredWindowRuntimeSha256')
    if not isinstance(slots, dict) or set(slots) != set(CONFIGURED_WINDOW_V2_RUNTIME):
        raise ValueError('Configured window V2 runtime inventory differs; rebuild current source')
    for name, digest in slots.items():
        path = root / 'dist' / name
        if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Configured window V2 runtime digest differs: ' + name)
        if name in CONFIGURED_WINDOW_V2_WRAPPERS:
            source = root / 'cmd' / name
            if not source.is_file() or source.is_symlink() or source.read_bytes() != path.read_bytes():
                raise ValueError('Configured window V2 wrapper changed after build: ' + name)
    return dict(slots)


def verify_structured_window_runtime(root, manifest):
    """Bind the opt-in module without adding it to either default inventory.

    Its shared host dependency is independently covered by the existing four
    window slots. Missing payloads or stale wrappers must prevent packaging.
    """
    root = Path(root)
    verify_configured_window_v2_runtime(root, manifest)
    slots = manifest.get('structuredWindowRuntimeSha256')
    if not isinstance(slots, dict) or set(slots) != set(STRUCTURED_WINDOW_RUNTIME):
        raise ValueError('Structured window runtime inventory differs; rebuild current source')
    for name, digest in slots.items():
        path = root / 'dist' / name
        if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Structured window runtime digest differs: ' + name)
        if name in STRUCTURED_WINDOW_WRAPPERS:
            source = root / 'cmd' / name
            if not source.is_file() or source.is_symlink() or source.read_bytes() != path.read_bytes():
                raise ValueError('Structured window wrapper changed after build: ' + name)
    return dict(slots)
