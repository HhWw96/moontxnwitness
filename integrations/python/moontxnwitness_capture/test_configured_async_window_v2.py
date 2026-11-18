"""Regression for cancellation during the pre-COMMIT writer probe."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from .configured_async_window_v2 import _AsyncPointConnectionV2
from .configured_effects import WRITER_PROBE_SQL


class AsyncPointWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_cancellation_survives_failed_savepoint_cleanup(self):
        started = asyncio.Event()

        class ProbeCursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def execute(self, sql, *, prepare):
                if sql == WRITER_PROBE_SQL:
                    started.set()
                    await asyncio.Future()
                if sql.startswith('ROLLBACK TO SAVEPOINT '):
                    raise OSError('connection failed during probe cleanup')

        session = SimpleNamespace(_enabled=True, _automatic_writer_checkpoints=True, gap=Mock())
        raw = SimpleNamespace(autocommit=False, _pipeline=None, _tpc=None,
                              info=SimpleNamespace(backend_pid=99, transaction_status=2),
                              cursor=Mock(return_value=ProbeCursor()), commit=AsyncMock())
        connection = _AsyncPointConnectionV2(session, raw)
        connection._tx = 'app-transaction'
        task = asyncio.create_task(connection.commit())
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel('application cancelled commit')
        with self.assertRaisesRegex(asyncio.CancelledError, 'application cancelled commit'):
            await task
        raw.commit.assert_not_awaited()
        self.assertEqual(connection._tx, 'app-transaction')
        self.assertEqual([item.args[0] for item in session.gap.call_args_list[-2:]],
                         ['async_point_checkpoint_cleanup_failed', 'async_point_commit_cancelled'])
