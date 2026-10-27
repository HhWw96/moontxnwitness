"""Finite execution timing only; never native service facts or completed evidence."""
from __future__ import annotations
import faulthandler,json,os,time
from pathlib import Path

class RunDiagnostics:
    """Owned siblings of server/ so closing them cannot mutate a sealed receipt."""
    def __init__(self,directory,*,stack_after_seconds=90):
        if type(stack_after_seconds) is not int or not 1<=stack_after_seconds<=90:
            raise ValueError('Bounded stack interval required')
        self.directory=Path(directory);self.started=time.monotonic_ns()
        self.log=self.stack=None;self.records=0;self.bytes=0;self.closed=False;self.armed=False
        try:
            self.log=(self.directory/'server-progress.jsonl').open('xb')
            self.stack=(self.directory/'server-stack.log').open('xb')
            self.mark('run-enter',stackAfterSeconds=stack_after_seconds)
            faulthandler.dump_traceback_later(stack_after_seconds,repeat=False,file=self.stack)
            self.armed=True
        except BaseException:
            self.close();raise
    def mark(self,phase,**fields):
        if self.closed or not isinstance(phase,str) or not 1<=len(phase)<=80 or set(fields)-{'stackAfterSeconds','errorClass'}:
            raise ValueError('Diagnostic phase is closed or invalid')
        row={'diagnosticOnly':True,'phase':phase,'elapsedNs':time.monotonic_ns()-self.started,**fields}
        if 'errorClass' in fields and (not isinstance(fields['errorClass'],str) or len(fields['errorClass'])>80):
            raise ValueError('Only bounded exception class names may be recorded')
        raw=(json.dumps(row,separators=(',',':'))+'\n').encode()
        if self.records>=128 or self.bytes+len(raw)>32768:
            raise ValueError('Diagnostic timing budget exceeded')
        self.log.write(raw);self.log.flush();self.records+=1;self.bytes+=len(raw)
    def call(self,phase,callback):
        self.mark(phase+'-start')
        try:result=callback()
        except BaseException as error:
            self.mark(phase+'-error',errorClass=type(error).__name__);raise
        self.mark(phase+'-done');return result
    def close(self):
        if self.closed:return
        try:
            if self.armed:faulthandler.cancel_dump_traceback_later();self.armed=False
            if self.log is not None:self.mark('run-leave')
        finally:
            self.closed=True
            for stream in (self.log,self.stack):
                if stream is not None:
                    try:stream.flush();os.fsync(stream.fileno())
                    finally:stream.close()
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
