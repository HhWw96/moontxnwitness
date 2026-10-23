"""Opt-in cost-run capacity arithmetic and small shared byte reservation guard.

No execution on import. Estimates do not promise that a full 36-cell run fits.
"""
from pathlib import Path
import shutil
import sys
import threading
import tempfile
import os
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture._experimental_budget import PROFILE,LIMITS,profile

METADATA_BYTES=64*1024**2

def raw_envelope():
    return sum(LIMITS[x] for x in ('sourceBytes','lifecycleBytes','journalBytes','transactionIndexBytes','attemptBytes'))+METADATA_BYTES

def required_free():
    return 2*raw_envelope()+LIMITS['transactionIndexBytes']+LIMITS['databaseAndWalBytes']+LIMITS['storageReserveBytes']

def preparation(path, *, free_bytes=None):
    observed=shutil.disk_usage(path)
    free=observed.free if free_bytes is None else free_bytes
    if type(free) is not int or free<0:raise ValueError('Invalid observed free bytes')
    archives=Path(path)/'archives'
    retained=sum(p.stat().st_size for p in archives.glob('*.zip')) if archives.is_dir() else 0
    # Existing archives and DB already reduce actual free. Reserve the full DB
    # budget as additional conservative headroom; never add archives twice.
    required=required_free()
    return {'experimentalBudget':PROFILE,'observedFreeBytes':free,'observedVolumeBytes':observed.total,'alreadyRetainedArchiveBytes':retained,'rawCellEnvelopeBytes':raw_envelope(),'rawPlusWorstCaseZipBytes':2*raw_envelope(),'sqliteRebuildReserveBytes':LIMITS['transactionIndexBytes'],'databaseAndWalReserveBytes':LIMITS['databaseAndWalBytes'],'minimumFreeRequiredBeforeCell':required,'eligibleToStart':free>=required,'reason':None if free>=required else 'insufficient_capacity_before_cell','noCompressionRatioAssumed':True,'fullThirtySixCellCompletionGuaranteed':False}

def scratch_preparation(path):
    scratch=Path(os.environ.get('MTW_JOURNAL_SCRATCH',tempfile.gettempdir()))
    if not scratch.is_dir():
        return {'eligibleToStart':False,'reason':'verification_scratch_missing'}
    free=shutil.disk_usage(scratch).free
    required=LIMITS['transactionIndexBytes']+512*1024**2
    return {'eligibleToStart':free>=required,'reason':None if free>=required else 'insufficient_verification_scratch',
            'sameVolumeAsOutput':os.stat(scratch).st_dev==os.stat(path).st_dev,
            'observedScratchFreeBytes':free,'scratchRequiredBytes':required}

def live_reserve():
    # Preserve room for one complete worst-case archive plus reconstruction and
    # safety reserve while this newly owned raw cell is growing.
    return raw_envelope()+LIMITS['transactionIndexBytes']+LIMITS['storageReserveBytes']

class AttemptByteBudget:
    def __init__(self,limit):
        if type(limit) is not int or limit<1:raise ValueError('Positive byte budget required')
        self.limit=limit;self.written=0;self.reserved=0;self.lock=threading.Lock()
    def reserve(self,size):
        if type(size) is not int or size<1:raise ValueError('Positive reservation required')
        with self.lock:
            if self.written+self.reserved+size>self.limit:return False
            self.reserved+=size;return True
    def complete(self,reservation,actual):
        if type(reservation) is not int or reservation<1 or type(actual) is not int or not 0<=actual<=reservation:raise ValueError('Record exceeded reservation')
        with self.lock:
            if self.reserved<reservation:raise ValueError('Unknown reservation')
            self.reserved-=reservation;self.written+=actual
    def release(self,reservation):self.complete(reservation,0)
