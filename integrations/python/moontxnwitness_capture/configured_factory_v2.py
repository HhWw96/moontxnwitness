"""Admission and failure cleanup for owned synchronous configured factories.

This gate does not implement asynchronous capture or pool lease ownership. It
never awaits a result, runs an event loop, cancels a task or logs factory args.
"""
from __future__ import annotations

import inspect


FACTORY_GAP_CODE = 'configured_factory_unobserved'
FACTORY_GAP_MESSAGE = (
    'A configured local factory failed or returned an unsupported result; '
    'its operation sequence is not proven.'
)


class UnsupportedConfiguredFactoryV2(ValueError):
    """The synchronous source-bound factory cannot accept this execution mode."""


def _async_callable(value):
    return inspect.iscoroutinefunction(value) or inspect.isasyncgenfunction(value)


def require_sync_factory_v2(factory, *, asynchronous=False):
    """Reject known async factories before invoking any application code."""
    if not callable(factory) or type(asynchronous) is not bool or asynchronous:
        raise UnsupportedConfiguredFactoryV2('An owned synchronous connection factory is required')
    call = inspect.getattr_static(type(factory), '__call__', None)
    if isinstance(call, (staticmethod, classmethod)):
        call = call.__func__
    if _async_callable(factory) or _async_callable(call):
        raise UnsupportedConfiguredFactoryV2('Asynchronous configured connection factories are not supported')
    return factory


def _async_result(value):
    if inspect.isawaitable(value) or inspect.isasyncgen(value):
        return True
    # Check protocol definitions without calling application descriptors/methods.
    for name in ('__aenter__', '__aexit__', 'execute', 'cursor', 'commit', 'rollback', 'close'):
        method = inspect.getattr_static(type(value), name, None)
        if isinstance(method, (staticmethod, classmethod)):
            method = method.__func__
        if name in ('__aenter__', '__aexit__') and method is not None or _async_callable(method):
            return True
    return False


def require_sync_result_v2(value):
    """Reject runtime async results without executing or cleaning up async work.

    An unsupported result remains owned by its caller/factory. In particular, a
    previously scheduled task is not cancelled and a coroutine is not awaited.
    """
    if _async_result(value):
        raise UnsupportedConfiguredFactoryV2('Asynchronous connection results require a separate capture adapter')
    return value


def close_rejected_sync_result_v2(value, *, protected=()):
    """Best-effort cleanup after failed admission; never replaces its exception.

    The calling factory contract owns newly returned sync connections. Explicit
    controller/observer identities and all async protocols are excluded here.
    """
    try:
        if value is None or any(value is item for item in protected) or _async_result(value):
            return False
        close = getattr(value, 'close', None)
        if not callable(close) or _async_callable(close):
            return False
        close()
        return True
    except BaseException:
        return False


def record_factory_gap_v2(observer):
    """One fixed bounded gap; never serialize arguments or an exception message."""
    try:
        observer.gap(FACTORY_GAP_CODE, FACTORY_GAP_MESSAGE)
        return True
    except BaseException:
        return False
