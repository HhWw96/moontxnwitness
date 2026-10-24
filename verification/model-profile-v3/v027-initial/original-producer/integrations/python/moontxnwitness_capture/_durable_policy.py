"""Internal byte-capacity queue and group-sync policy; no evidence semantics.

Callers own synchronization, record validation, file/index formats and failure
markers. In-flight records remain charged until complete() is called.
"""
import collections


class CapacityQueue:
    def __init__(self, max_bytes):
        self.max_bytes = max_bytes
        self.items = collections.deque()
        self.queued_bytes = self.reserved_bytes = 0

    @property
    def used_bytes(self): return self.queued_bytes + self.reserved_bytes

    def can_reserve(self, size): return self.used_bytes + size <= self.max_bytes

    def reserve(self, size):
        if not self.can_reserve(size): raise ValueError('Queue reservation exceeds byte capacity')
        self.reserved_bytes += size

    def release_reservation(self, size):
        if not 0 <= size <= self.reserved_bytes: raise ValueError('Invalid queue reservation release')
        self.reserved_bytes -= size

    def enqueue(self, item, size):
        self.queued_bytes += size
        self.items.append(item)

    def pop(self): return self.items.popleft() if self.items else None

    def complete(self, size):
        if not 0 <= size <= self.queued_bytes: raise ValueError('Invalid in-flight completion')
        self.queued_bytes -= size

    def clear(self):
        self.items.clear()
        self.queued_bytes = 0


def sync_due(dirty, last_sync, now, interval):
    return dirty and now - last_sync >= interval


def sync_wait(dirty, last_sync, now, interval):
    return max(0.001, interval - (now - last_sync)) if dirty else None


def should_sync(closing, explicit, dirty, pending_bytes, flush_bytes, last_sync, now, interval):
    return closing or explicit or sync_due(dirty, last_sync, now, interval) or pending_bytes >= flush_bytes


def flush_pending(requested_generation, flushed_generation, durable_seq, target_seq):
    # A generation may have been persisted before its target record was written.
    return requested_generation > flushed_generation or durable_seq < target_seq
