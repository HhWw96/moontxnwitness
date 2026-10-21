"""Opt-in initial ACK barrier over the exact original R2 point initializer.

The delegated initializer remains byte-bound and unchanged. This adds a
pre-publication gate, not general SQL/source proof or automatic crash recovery.
"""
from __future__ import annotations

from epoch_sources import EpochError,require,_status


def bounded_keys(values):
    """Consume at most65 items, including the first overflowing item."""
    iterator=iter(values);items=[]
    for _ in range(65):
        try:item=next(iterator)
        except StopIteration:break
        items.append(item)
    require(1<=len(items)<=64,"Declare1..64 distinct existing text keys")
    # Check type/character count before hashing or UTF-8 allocation. A maximum
    # of512 codepoints also bounds the temporary encoding to2048 bytes.
    require(all(type(k) is str and 0<len(k)<=512 for k in items),"Bounded text key required")
    try:valid=all(len(k.encode("utf8"))<=512 for k in items)
    except UnicodeError:valid=False
    require(valid and len(set(items))==len(items),"Distinct valid UTF-8 keys of at most512 bytes required")
    return tuple(items)


class InitialCommitSetup:
    """Preserve setup results/errors; admit only an exact retained COMMIT ACK."""
    def __init__(self,raw,capture):
        self.raw,self.capture=raw,capture
        self.attempted=False;self.confirmed=False
        self.primary_error=None;self.primary_traceback=None

    def __getattr__(self,name):return getattr(self.raw,name)

    def gap(self,code,message):
        try:self.capture.gap(code,message)
        except BaseException:pass  # Never mask the original driver exception.

    def _retain_error(self,error,before):
        self.primary_error=error;self.primary_traceback=error.__traceback__
        self.gap("initialization_commit_unknown","Original setup COMMIT did not deliver a usable acknowledgement")
        try:
            self.capture.sources.append({"kind":"initialization-commit-error","statusBefore":before,
                "statusAfter":_status(self.raw),"errorClass":type(error).__name__,
                "actualCommitConfirmed":False,"coreProofImplemented":False})
        except BaseException:self.capture.sources.failed=True

    def execute(self,sql,params=None):
        if sql!="COMMIT":return self.raw.execute(sql,params)
        require(not self.attempted,"Initial COMMIT attempted more than once")
        self.attempted=True;before=_status(self.raw)
        try:
            result=self.raw.execute(sql,params)
            tag=result.statusmessage;status=result.pgresult.status
            after=_status(self.raw);description=result.description
        except BaseException as error:
            self._retain_error(error,before);raise
        valid_tag=type(tag) is str and len(tag)<=128
        valid_status=isinstance(status,int) and type(status) is not bool
        status_value=int(status) if valid_status else None
        confirmed=(before==2 and after==0 and valid_tag and tag=="COMMIT"
                   and valid_status and status_value==1 and description is None)
        record={"kind":"initialization-commit-ack","sql":"COMMIT","statusBefore":before,
            "statusAfter":after,"commandTag":tag if valid_tag else None,"pgStatus":status_value,
            "noRows":description is None,"actualCommitConfirmed":confirmed,"coreProofImplemented":False}
        try:self.capture.sources.append(record)
        except BaseException as error:
            self.primary_error=error;self.primary_traceback=error.__traceback__
            self.capture.sources.failed=True
            self.gap("initialization_ack_not_retained","Setup returned but initial ACK evidence could not be retained")
            raise
        if not confirmed:
            self.gap("initialization_ack_invalid","Setup COMMIT tag, result status, transaction status or shape was not confirmation")
            raise EpochError("Initial COMMIT requires COMMIT command tag, COMMAND_OK, no rows and idle connection")
        self.confirmed=True
        return result
