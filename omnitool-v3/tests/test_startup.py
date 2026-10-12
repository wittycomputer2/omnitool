"""Regression checks for launching alongside an older OmniTool process."""

import errno
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class StartupTest(unittest.TestCase):
    def listener(self, port, bind_errors=None):
        listener = MagicMock()
        listener.__enter__.return_value = listener
        listener.getsockname.return_value = ('127.0.0.1', port)
        listener.fileno.return_value = 42
        listener.bind.side_effect = bind_errors
        return listener

    def test_uses_default_port_when_available(self):
        listener = self.listener(5000)
        with patch.object(app.socket, 'socket', return_value=listener), patch.object(app, 'make_server') as create:
            server = app._create_server()
        listener.bind.assert_called_once_with(('127.0.0.1', 5000))
        create.assert_called_once_with('127.0.0.1', 5000, app.app, threaded=True, fd=42)
        self.assertIs(server, create.return_value)

    def test_older_server_uses_separate_port_without_stopping_it(self):
        listener = self.listener(43210, [OSError(errno.EADDRINUSE, 'Address already in use'), None])
        with patch.object(app.socket, 'socket', return_value=listener), patch.object(app, 'make_server') as create:
            app._create_server()
        self.assertEqual(listener.bind.call_args_list, [call(('127.0.0.1', 5000)), call(('127.0.0.1', 0))])
        listener.listen.assert_called_once()
        create.assert_called_once_with('127.0.0.1', 43210, app.app, threaded=True, fd=42)

    def test_permission_failure_is_not_misreported_as_port_conflict(self):
        listener = self.listener(5000, OSError(errno.EACCES, 'Permission denied'))
        with patch.object(app.socket, 'socket', return_value=listener), patch.object(app, 'make_server') as create:
            with self.assertRaises(PermissionError):
                app._create_server()
        listener.bind.assert_called_once()
        create.assert_not_called()

    def test_ui_identifies_current_version_and_actual_port(self):
        response = app.app.test_client().get('/', base_url='http://127.0.0.1:43210')
        html = response.get_data(as_text=True)
        self.assertIn('v3.2.0', html)
        self.assertIn('Ready • 127.0.0.1:43210', html)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
