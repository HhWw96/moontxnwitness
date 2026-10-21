"""Opt-in strong connection ownership over the frozen R2 point observer."""
from epoch_sources import EpochError,Installation,References,plain,require,_status


class EpochCapture(plain.PlainJournalCapture):
    def __init__(self,path,*,epoch,registry,coordinator=None,max_live=128,**kwargs):
        require(type(max_live) is int and 1<=max_live<=128,"Live connection bound")
        self._live={};self.epoch=epoch;self.registry=registry;self._coordinator=coordinator
        self._max_live=max_live;self._released=False;self._admissions_stopped=False
        super().__init__(path,**kwargs)

    def wrap(self,raw,*,role=None):
        with self._lock:
            require(self._released and not self._admissions_stopped and not self._closed,"Epoch wrapper admission closed")
            require(self._initialized and self.installation is not None,"Epoch initialization unproved")
            require(len(self._live)<self._max_live,"Live connection registry full")
            require(not any(c._raw is raw for c in self._connections),"Connection already wrapped")
            result=EpochConnection(self,raw);self._live[result._identity]=result;self._connections.add(result)
            try:self.registry.connection(result._identity,self.epoch,"open")
            except Exception:self.gap("connection_registry_failed","Open identity was not durably indexed")
            self._ledger_complete=False;return result

    def activity(self,operation):
        super().activity(operation)
        if self._admissions_stopped and not self._closed:
            self.gap("activity_after_quiescence","Business activity was observed after the explicit stopped-worker barrier")
            if self._coordinator is not None:self._coordinator.invalidate("activity_after_quiescence")
        if self._closed and self._coordinator is not None:self._coordinator.invalidate("late_epoch_activity")

    def admission(self):
        reasons=[]
        if not self._initialized or self.installation is None:reasons.append("initialization")
        if self._closed:reasons.append("already-sealed")
        if self._live:reasons.append("live-connections-without-close-ack")
        if self._pending_results:reasons.append("unread-results")
        if self.gaps:reasons.append("coverage-gaps")
        if not self.registry.closed(self.epoch):reasons.append("unacknowledged-disk-connections")
        return reasons

    def initialize_from_boundary(self,packet):
        require(not self._initialized and not self._seq and self.installation is None,"Boundary initialization once")
        require(self.profile.names==packet.installation.names and self.keys==frozenset(packet.keys),"Boundary scope differs")
        values=packet.validate()
        self.sources.append({"kind":"boundary-initialization","epoch":self.epoch,"boundarySummary":packet.summary,
            "boundaryId":packet.path.name,"boundaryBindings":packet.bindings(),
            "initialRows":[[key,value,version] for key,(value,version) in sorted(values.items())],"coreProofImplemented":False})
        self.installation=Installation(packet.installation.names,packet.installation.nonce,packet.installation.table_oid,{})
        self.publish_snapshot({key:value[1] for key,value in values.items()},consistent=True)


class EpochConnection(plain.PlainConnection):
    def close(self):
        session=self._session
        if self._identity not in session._live:return self._raw.close()  # Pure idempotent cleanup.
        before=_status(self._raw);already_closed=self._raw.closed
        try:result=super().close()
        except BaseException:
            session.gap("close_unacknowledged","Original close failed; strong identity retained");raise
        if already_closed or not self._raw.closed:
            session.gap("close_unobserved","Raw connection was closed elsewhere or did not confirm close")
            return result
        ack={"kind":"connection-close-ack","epoch":session.epoch,"connection":self._identity,
             "statusBefore":before,"closedAfter":True,"idleBefore":before==0}
        try:
            session.sources.append(ack)
            session.registry.connection(self._identity,session.epoch,"closed",ack)
            del session._live[self._identity]
        except Exception:session.gap("close_ack_not_retained","Business close returned but acknowledgement storage failed")
        return result
