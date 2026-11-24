"""Isolated HTTPS pulse spike receiver. Does not write into the product DB.

Supply BRIDGE_TEST_TOKEN (>=32 characters), a certificate and matching key.
Health values and tokens are never written to access logs; latest values are
held in memory only. Bind a LAN address explicitly for a real iPhone test.
"""
import argparse
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import ssl
import time
import uuid


def validate_sample(value, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(value, dict) or type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1:
        raise ValueError('schema')
    if value.get('source') not in ('apple_watch', 'ble_heart_rate'):
        raise ValueError('source')
    if type(value.get('sequence')) is not int or value['sequence'] < 0:
        raise ValueError('sequence')
    bpm = value.get('bpm')
    if type(bpm) not in (int, float) or not math.isfinite(bpm) or not 20 <= bpm <= 250:
        raise ValueError('bpm')
    uuid.UUID(value['sessionID'])
    stamp = datetime.fromisoformat(value['timestamp'].replace('Z', '+00:00'))
    if stamp.tzinfo is None or not -2 <= (now - stamp).total_seconds() <= 10:
        raise ValueError('stale')
    return value


def make_handler(token):
    sequences = {}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # Neither health values nor Authorization go to an access log.

        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != '/pulse':
                return self.reply(404, {'accepted': False})
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                # Drain a bounded, ordinary request before closing HTTP/1.0.
                # Otherwise TCP may reset while a client is still sending its
                # small JSON body, hiding the intended 401 from that client.
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if 0 < length <= 2048:
                        self.rfile.read(length)
                except (ValueError, OSError):
                    pass
                return self.reply(401, {'accepted': False})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048:
                    raise ValueError('length')
                sample = validate_sample(json.loads(self.rfile.read(length)))
                now = time.monotonic()
                for key, (_, seen) in list(sequences.items()):
                    if now - seen > 60:
                        del sequences[key]
                key = sample['sessionID']
                previous = sequences.get(key, (-1, 0))[0]
                if sample['sequence'] <= previous:
                    return self.reply(409, {'accepted': False, 'reason': 'duplicate_or_out_of_order'})
                if len(sequences) >= 32 and key not in sequences:
                    return self.reply(429, {'accepted': False})
                sequences[key] = (sample['sequence'], now)
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                return self.reply(422, {'accepted': False})
            self.server.latest_sample = sample
            return self.reply(202, {'accepted': True, 'received_at': datetime.now(timezone.utc).isoformat()})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8443)
    parser.add_argument('--cert', required=True)
    parser.add_argument('--key', required=True)
    args = parser.parse_args()
    token = os.environ.get('BRIDGE_TEST_TOKEN', '')
    if len(token) < 32:
        parser.error('BRIDGE_TEST_TOKEN mit mindestens 32 Zeichen setzen')
    server = HTTPServer((args.host, args.port), make_handler(token))
    server.timeout = 5
    server.latest_sample = None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f'Isolierter TLS-Testempfänger auf {args.host}:{args.port}; keine Produktdatenbank, keine Messwertlogs.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
