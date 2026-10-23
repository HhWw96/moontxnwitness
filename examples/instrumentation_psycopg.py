"""Optional live SELECT-only diagnostic example. No schema changes or credentials in output."""
import argparse
import asyncio
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations' / 'python'))
from moontxnwitness_capture.instrumentation import instrument_engine, instrument_psycopg


def run_sync(args, dsn):
    import psycopg
    if args.mode == 'engine':
        from sqlalchemy import create_engine
        engine = create_engine('postgresql+psycopg://', creator=lambda: psycopg.connect(dsn))
        observer = instrument_engine(engine, args.output)
        try:
            with engine.begin() as connection:
                assert connection.exec_driver_sql('SELECT 1').scalar_one() == 1
        finally:
            engine.dispose(); observer.close()
    else:
        observer, connect = instrument_psycopg(psycopg.connect, args.output)
        try:
            with connect(dsn) as connection:
                assert connection.execute('SELECT 1').fetchone() == (1,)
        finally: observer.close()
    observer.export_diagnostic(Path(args.output) / 'trace.json')


async def run_async(args, dsn):
    import psycopg
    if args.mode == 'async-engine':
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine('postgresql+psycopg://', async_creator=lambda: psycopg.AsyncConnection.connect(dsn))
        observer = instrument_engine(engine, args.output)
        try:
            async with engine.begin() as connection:
                result = await connection.exec_driver_sql('SELECT 1')
                assert result.scalar_one() == 1
        finally:
            await engine.dispose(); observer.close()
    else:
        observer, connect = instrument_psycopg(psycopg.AsyncConnection.connect, args.output, asynchronous=True)
        try:
            async with await connect(dsn) as connection:
                cursor = await connection.execute('SELECT 1')
                assert await cursor.fetchone() == (1,)
        finally: observer.close()
    observer.export_diagnostic(Path(args.output) / 'trace.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mode', choices=['sync', 'async', 'engine', 'async-engine'], default='sync')
    args = parser.parse_args()
    dsn = os.environ.get('MTW_PG_DSN')
    if not dsn:
        print('not-executed: MTW_PG_DSN is required'); raise SystemExit(3)
    try:
        if args.mode.startswith('async'):
            if sys.platform == 'win32':
                with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                    runner.run(run_async(args, dsn))
            else: asyncio.run(run_async(args, dsn))
        else: run_sync(args, dsn)
    except ImportError:
        print('not-executed: install optional pinned driver/SQLAlchemy dependencies'); raise SystemExit(3)
    print('Diagnostic observations saved; complete transaction-model coverage is not claimed.')
