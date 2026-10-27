"""Bounded owned-child streams. No command is run at import time."""
import os,subprocess,threading,time

def run_bounded(command,*,env,cwd,timeout=150,max_stream_bytes=4*1024*1024):
    if type(timeout) not in (int,float) or not 0<timeout<=150 or type(max_stream_bytes) is not int or not 1<=max_stream_bytes<=4*1024*1024:raise ValueError('Invalid owned-child budget')
    options={'stdin':subprocess.DEVNULL,'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'env':env,'cwd':cwd}
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
    process=subprocess.Popen(command,**options);limit=threading.Event();lock=threading.Lock();buffers={'stdout':bytearray(),'stderr':bytearray()};observed={'stdout':0,'stderr':0};errors=[]
    def drain(name,stream):
        try:
            while True:
                chunk=stream.read(65536)
                if not chunk:break
                with lock:
                    observed[name]+=len(chunk);remaining=max_stream_bytes-len(buffers[name]);buffers[name].extend(chunk[:max(0,remaining)])
                    if observed[name]>max_stream_bytes:limit.set()
        except Exception as error:
            with lock:errors.append(type(error).__name__)
            limit.set()
        finally:stream.close()
    readers=[threading.Thread(target=drain,args=(name,getattr(process,name)),name='owned-'+name,daemon=True) for name in buffers]
    for thread in readers:thread.start()
    deadline=time.monotonic()+timeout;error=None
    try:
        while process.poll() is None:
            if limit.is_set():error='owned-child-stream-budget';break
            if time.monotonic()>=deadline:error='owned-child-process-timeout';break
            time.sleep(min(.02,max(0,deadline-time.monotonic())))
        if error:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        else:process.wait(timeout=5)
    except Exception as failure:
        error='owned-child-cleanup-'+type(failure).__name__
        if process.poll() is None:
            try:process.kill();process.wait(timeout=5)
            except Exception:pass
    finally:
        for thread in readers:thread.join(5)
    stopped=process.poll() is not None;alive=[thread.name for thread in readers if thread.is_alive()]
    if limit.is_set() and error is None:error='owned-child-stream-budget'
    if errors and error is None:error='owned-child-stream-read-failure'
    if (not stopped or alive) and error is None:error='owned-child-streams-not-closed'
    return {'returncode':process.returncode,'stdout':bytes(buffers['stdout']),'stderr':bytes(buffers['stderr']),'stdoutOriginalBytes':observed['stdout'],'stderrOriginalBytes':observed['stderr'],'streamsRetainedWithoutTruncation':error is None and stopped and not alive,'error':error,'childStopped':stopped,'drainThreadsStillAlive':alive}
