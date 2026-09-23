import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[1] / 'src/collector.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'codex'
        (self.home / 'sessions').mkdir(parents=True)
        self.file = self.home / 'sessions/a.jsonl'
        self.now = dt.datetime.now().astimezone().replace(hour=12).timestamp()
        self.stamp = dt.datetime.fromtimestamp(self.now, dt.timezone.utc).isoformat()
        self.c = m.Collector(self.home, self.root / 'cache')

    def tearDown(self):
        self.c.db.close()
        self.temp.cleanup()

    def emit(self, kind, payload, path=None, stamp=None):
        with (path or self.file).open('a') as stream:
            stream.write(json.dumps({'timestamp': stamp or self.stamp, 'ordinal': 1, 'type': kind, 'payload': payload}) + '\n')

    def counts(self, n):
        return dict(input_tokens=n, cached_input_tokens=n//2, output_tokens=10, reasoning_output_tokens=2, total_tokens=n+10)

    def snapshot(self, n):
        self.emit('event_msg', {'type': 'token_count', 'info': {'total_token_usage': self.counts(n)}, 'rate_limits': {'primary': {'used_percent': 73, 'window_minutes': 300, 'resets_at': self.now+3600}, 'secondary': {'used_percent': 41, 'window_minutes': 10080, 'resets_at': self.now+86400}}})

    def test_incremental_duplicate_snapshots(self):
        self.emit('session_meta', {'id': 'session'})
        self.snapshot(100)
        self.snapshot(100)
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 110)
        self.c.bytes_read = 0
        self.c.scan()
        self.assertEqual(self.c.bytes_read, 0)
        self.snapshot(200)
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 210)

    def test_partial_malformed_and_private_data(self):
        self.file.write_text('{malformed}\n')
        self.emit('response_item', {'type': 'message', 'content': 'SECRET_MARKER'})
        self.snapshot(100)
        with self.file.open('a') as stream:
            stream.write('{"timestamp":')
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 110)
        self.assertNotIn('SECRET_MARKER', ''.join(self.c.db.iterdump()))
        with self.file.open('a') as stream:
            stream.write('"' + self.stamp + '","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":' + json.dumps(self.counts(200)) + '}}}\n')
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 210)

    def test_records_preferred_and_global_dedup(self):
        self.emit('session_meta', {'id': 'session'})
        self.snapshot(100)
        payload = {'thread_id': 'session', 'response_id': 'response1', 'usage': self.counts(100), 'thread_token_usage': self.counts(100)}
        self.emit('token_usage_record', payload)
        copy = self.home / 'sessions/copy.jsonl'
        self.emit('session_meta', {'id': 'fork'}, copy)
        self.emit('event_msg', {'type': 'token_count', 'info': {'total_token_usage': self.counts(100)}}, copy)
        self.emit('token_usage_record', payload, copy)
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 110)
        self.assertEqual(self.c.result(self.now)['today']['sessions'], 1)

    def test_archive_move_dedup(self):
        self.emit('session_meta', {'id': 'session'})
        self.snapshot(100)
        self.c.scan()
        (self.home / 'archived_sessions').mkdir()
        self.file.rename(self.home / 'archived_sessions/a.jsonl')
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 110)

    def test_missing_and_stale_limits(self):
        self.c.scan()
        self.assertIsNone(self.c.result(self.now)['limits'])
        self.snapshot(100)
        self.c.scan()
        self.assertFalse(self.c.result(self.now)['limits']['primary']['stale'])
        self.assertTrue(self.c.result(self.now+301)['limits']['primary']['stale'])
        self.assertTrue(self.c.result(self.now+3601, stale_seconds=99999)['limits']['primary']['stale'])

    def test_live_limits_allowlists_and_validates_response(self):
        response = {'id': 2, 'result': {'rateLimits': {
            'limitId': 'codex', 'accountId': 'SECRET_ACCOUNT', 'credits': {'balance': 99},
            'primary': {'usedPercent': 12.5, 'windowDurationMins': 300, 'resetsAt': self.now+60, 'secret': 'AUTH_DATA'},
            'secondary': {'usedPercent': 44, 'windowDurationMins': 10080, 'resetsAt': self.now+120},
        }}}
        parsed = m.live_limits(response, self.now)
        self.assertEqual(parsed, {
            'observed_at': self.now,
            'primary': {'used_percent': 12.5, 'resets_at': self.now+60, 'window_minutes': 300},
            'secondary': {'used_percent': 44, 'resets_at': self.now+120, 'window_minutes': 10080},
        })
        self.assertNotIn('SECRET', json.dumps(parsed))
        response['result']['rateLimits']['primary']['usedPercent'] = 101
        response['result']['rateLimits']['secondary']['windowDurationMins'] = 300
        self.assertIsNone(m.live_limits(response, self.now))
        self.assertIsNone(m.live_limits({'id': 2, 'error': {'message': 'private'}}, self.now))

    def test_successful_live_limits_replace_jsonl_observation(self):
        self.snapshot(100)
        self.c.scan()
        live = {'observed_at': self.now+10,
                'primary': {'used_percent': 7, 'resets_at': self.now+1000, 'window_minutes': 300},
                'secondary': {'used_percent': 8, 'resets_at': self.now+2000, 'window_minutes': 10080}}
        self.assertTrue(m.refresh_live_limits(self.c, lambda: live))
        result = self.c.result(self.now+10)
        self.assertEqual(result['limits']['observed_at'], self.now+10)
        self.assertEqual(result['limits']['primary']['used_percent'], 7)
        self.assertEqual(result['today']['total_tokens'], 110)

    def test_schema_change_ignored(self):
        self.emit('event_msg', {'type': 'token_count', 'info': [], 'rate_limits': {'primary': {'used_percent': 'bad'}}})
        self.emit('turn_context', {'model': 'private/path', 'effort': 'high'})
        self.c.scan()
        result = self.c.result(self.now)
        self.assertEqual(result['today']['total_tokens'], 0)
        self.assertIsNone(result['context']['model'])

    def test_mixed_formats_shared_counter(self):
        self.emit('session_meta', {'id': 's'})
        self.snapshot(100)
        self.emit('token_usage_record', {'thread_id': 's', 'response_id': 'r', 'usage': self.counts(100), 'thread_token_usage': self.counts(200)})
        self.snapshot(200)
        self.snapshot(300)
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 310)

    def test_calendar_and_totals(self):
        self.emit('token_usage_record', {'thread_id': 's', 'response_id': 'r', 'usage': self.counts(100)})
        self.c.scan()
        result = self.c.result(self.now)
        self.assertEqual(result['today']['total_tokens'], 110)
        self.assertEqual(result['today']['cache_percent'], 50)
        self.assertEqual(result['week']['total_tokens'], 110)
        self.assertEqual(result['month']['total_tokens'], 110)

    def test_truncate_and_replay(self):
        self.emit('session_meta', {'id': 's'})
        self.snapshot(100)
        self.c.scan()
        saved = self.file.read_text()
        self.file.write_text('')
        self.c.scan()
        self.file.write_text(saved)
        self.c.scan()
        self.assertEqual(self.c.result(self.now)['today']['total_tokens'], 110)

if __name__ == '__main__':
    unittest.main()
