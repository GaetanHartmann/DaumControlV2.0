import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid
import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest


spec = importlib.util.spec_from_file_location('bridge_receiver', Path(__file__).parents[2] / 'spikes/apple-bridge/receiver.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


def sample(at):
    return dict(schemaVersion=1, sessionID=str(uuid.uuid4()), sequence=1, timestamp=at.isoformat(), source='apple_watch', bpm=97)


def test_receiver_accepts_only_fresh_well_formed_real_source():
    now = datetime.now(timezone.utc)
    assert receiver.validate_sample(sample(now), now)['bpm'] == 97
    for changes in ({'bpm': None}, {'bpm': float('nan')}, {'bpm': True}, {'sequence': -1}, {'source': 'demo'}, {'timestamp': (now - timedelta(seconds=11)).isoformat()}, {'timestamp': (now + timedelta(seconds=3)).isoformat()}, {'timestamp': now.replace(tzinfo=None).isoformat()}):
        with pytest.raises((ValueError, TypeError)):
            receiver.validate_sample({**sample(now), **changes}, now)


def test_receiver_checks_authentication_sequence_and_body_limits():
    token = 'x' * 32
    server = HTTPServer(('127.0.0.1', 0), receiver.make_handler(token))
    server.latest_sample = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    value = sample(datetime.now(timezone.utc))

    def post(payload, secret=token):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=2)
        try:
            connection.request('POST', '/pulse', payload, {'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    try:
        assert post(json.dumps(value), secret='wrong') == 401
        assert server.latest_sample is None
        assert post(json.dumps(value)) == 202
        assert server.latest_sample == value
        assert post(json.dumps(value)) == 409
        assert post('x' * 2049) == 422
        assert post(json.dumps({**value, 'sequence': 2, 'bpm': None})) == 422
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
