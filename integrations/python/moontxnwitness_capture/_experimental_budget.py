"""Finite opt-in storage capacity for controlled cost experiments only.

These ceilings do not extend model/analysis coverage. Disk declarations never
choose a larger budget: the caller must explicitly allow this exact profile.
"""
PROFILE = 'full-capture-cost-capacity/v2'
GIB = 1024 ** 3
LIMITS = {
    'sourceBytes': 2 * GIB, 'sourceRecords': 6_000_000,
    'lifecycleBytes': 6 * GIB, 'lifecycleRecords': 16_000_000,
    'journalBytes': 4 * GIB, 'transactionIndexBytes': GIB,
    'attemptBytes': GIB, 'rawCellBytes': 14 * GIB + 64 * 1024**2,
    'archiveExpandedBytes': 16 * GIB, 'databaseAndWalBytes': 8 * GIB,
    'storageReserveBytes': 4 * GIB,
    'maxAttemptsPerWorker': 1_000_000, 'maxWarmupAttemptsPerWorker': 250_000,
}


def profile(value):
    if value is not None and (type(value) is not str or value != PROFILE):
        raise ValueError('Unknown experimental storage budget; explicit supported profile required')
    return value


def authorize(marker, allowed):
    profile(allowed)
    if marker is not None:
        if marker != PROFILE or allowed != PROFILE:
            raise ValueError('Experimental storage requires the matching explicit reader budget')
    return marker


def sqlite_limit(value, selected):
    if selected is None:
        if value is not None:
            raise ValueError('Transaction page budget requires explicit experimental profile')
        return None
    value = LIMITS['transactionIndexBytes'] if value is None else value
    if type(value) is not int or value < 8192 or value > LIMITS['transactionIndexBytes'] or value % 4096:
        raise ValueError('Experimental transaction budget must be page-aligned 8 KiB..1 GiB')
    return value
