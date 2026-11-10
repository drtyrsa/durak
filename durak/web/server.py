"""Serve a private, local Durak table using only Python's standard library."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit
import webbrowser

from durak.controller.exceptions import GameControllerError
from durak.engine.wrapper import EngineWrapperException
from durak.web.game import BrowserGame, StalePosition


STATIC = Path(__file__).with_name('static')
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/favicon.svg': ('favicon.svg', 'image/svg+xml')}


class DurakServer(ThreadingHTTPServer):
    def __init__(self, port=8765, engine='nextgen', log_dir=None):
        self.game = BrowserGame(engine, log_dir=log_dir)
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)

    def server_close(self):
        self.game.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _local_request(self):
        port = self.server.server_port
        host = self.headers.get('Host', '')
        return host in ('127.0.0.1:' + str(port), 'localhost:' + str(port))

    def _state(self):
        result = self.server.game.snapshot()
        result['token'] = self.server.token
        return result

    def do_GET(self):
        if not self._local_request():
            self._send(403, {'error': 'Use the local server address.'})
            return
        path = urlsplit(self.path).path
        if path in ASSETS:
            filename, content_type = ASSETS[path]
            self._send(200, (STATIC / filename).read_bytes(), content_type)
        elif path == '/api/state':
            with self.server.lock:
                self._send(200, self._state())
        else:
            self._send(404, {'error': 'Not found.'})

    def do_POST(self):
        host = self.headers.get('Host', '')
        if (not self._local_request() or
                self.headers.get('Origin', 'http://' + host) != 'http://' + host or
                self.headers.get('X-Durak-Token') != self.server.token):
            self._send(403, {'error': 'Refresh the local game page and try again.'})
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Expected JSON.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('Invalid request size.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
        except (ValueError, UnicodeDecodeError) as error:
            self._send(400, {'error': str(error)})
            return
        path = urlsplit(self.path).path
        with self.server.lock:
            game = self.server.game
            try:
                if path == '/api/new':
                    game.check_revision(data.get('revision'))
                    engine = data.get('engine', game.engine_id)
                    if not isinstance(engine, str):
                        raise ValueError('Invalid new-game options.')
                    game.start(engine)
                elif path == '/api/action':
                    game.action(data.get('action'), data.get('cards', []), data.get('revision'))
                elif path == '/api/step':
                    game.step(data.get('revision'))
                else:
                    self._send(404, {'error': 'Not found.'})
                    return
                self._send(200, self._state())
            except StalePosition as error:
                self._send(409, {'error': str(error), 'state': self._state()})
            except (ValueError, GameControllerError) as error:
                if path == '/api/step':
                    game.fail(error)
                self._send(400, {'error': str(error) or 'Choose a card to start the attack.',
                                 'state': self._state()})
            except (OSError, EngineWrapperException) as error:
                game.fail(error)
                self._send(502, {'error': game.error, 'state': self._state()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765, help='local port (default: 8765; 0: choose a free port)')
    parser.add_argument('--engine', default='nextgen', help='nextgen, dummy, or an engine executable name/path')
    parser.add_argument('--no-browser', action='store_true', help='print the URL without opening a browser')
    parser.add_argument('--log-dir', default='logs', help='game/decision log directory (default: logs)')
    parser.add_argument('--no-log', action='store_true', help='disable game and decision logging')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('port must be between 0 and 65535')
    try:
        server = DurakServer(args.port, args.engine, log_dir=None if args.no_log else args.log_dir)
    except OSError as error:
        parser.exit(1, 'Cannot start durak-web: {}\n'.format(error))
    try:
        server.game.start()
        url = 'http://127.0.0.1:{}/'.format(server.server_port)
        print('Durak is at {}\nPress Ctrl+C to close the table.'.format(url), flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nTable closed.')
    except (OSError, EngineWrapperException) as error:
        parser.exit(1, 'Engine error: {}\n'.format(error))
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
