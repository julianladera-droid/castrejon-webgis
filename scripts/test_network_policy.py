"""Regresiones offline: el contrato válido pasa y sus infracciones fallan."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_webgis as gate


class NetworkPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (gate.ROOT / 'index.html').read_text(encoding='utf-8')

    def check(self, html):
        page = gate.Page()
        page.feed(html)
        page.close()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.check_network_policy(html, page)

    def test_current_page(self):
        self.check(self.html)

    def test_forbidden_literals(self):
        cases = [
            'localhost', 'LOCALHOST', '127.0.0.1', '10.2.3.4',
            '172.16.0.1', '172.31.255.254', '192.168.1.2', '169.254.1.2',
            'printer.local', 'targetAddressSpace: "local"',
            '"targetAddressSpace": "private"',
            'http://sigpac-hubcloud.es/wms', 'https://example.org/map',
            'https://[::1]/map', 'https://[fe80::1]/map',
            'https://sigpac-hubcloud.es.example.org/map',
        ]
        for literal in cases:
            with self.subTest(literal=literal), self.assertRaisesRegex(ValueError, 'Red:'):
                self.check(self.html + '\n<!-- ' + literal + ' -->')

    def test_csp_mutations(self):
        mutations = [
            ('Content-Security-Policy', 'other-policy'),
            ("default-src 'self'", "default-src 'self' *"),
            ("object-src 'none'", "object-src 'none' https:"),
            ("connect-src 'self'", "connect-src 'self' *"),
            ("connect-src 'self'", "connect-src 'self' data:"),
            ("worker-src 'none';", ''),
            ("frame-src 'none';", "frame-src 'none'; frame-src *;"),
        ]
        for before, after in mutations:
            with self.subTest(after=after), self.assertRaisesRegex(ValueError, 'Seguridad:'):
                self.check(self.html.replace(before, after, 1))
        meta = next(line for line in self.html.splitlines() if 'Content-Security-Policy' in line)
        with self.assertRaisesRegex(ValueError, 'única CSP'):
            self.check(self.html.replace(meta, meta + '\n' + meta))

    def test_anonymous_cors(self):
        for value in ["crossOrigin: 'anonymous'", 'crossOrigin : "anonymous"',
                      '"crossOrigin": "anonymous"', "crossorigin = 'anonymous'"]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'WMS:'):
                self.check(self.html + '\n<!-- ' + value + ' -->')

    def test_main_rejects_before_node(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text(self.html.replace("connect-src 'self'", "connect-src *"), encoding='utf-8')
            with patch.object(gate, 'ROOT', root), patch.object(gate, 'check_secrets'), \
                    patch.object(gate.subprocess, 'run') as node:
                with self.assertRaisesRegex(ValueError, 'Seguridad:'):
                    gate.main()
                node.assert_not_called()


if __name__ == '__main__':
    unittest.main()
