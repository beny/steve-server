"""Přenosový protokol ESP bez fyzické desky nebo síťového spojení."""

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


TRANSPORT = Path(__file__).resolve().parents[1] / "firmware" / "transport.py"


def load_transport():
    network = types.ModuleType("network")
    network.STA_IF = 0
    network.WLAN = lambda _: types.SimpleNamespace(isconnected=lambda: True)
    config = types.ModuleType("config")
    config.SERVER_URL = "http://macmini.local:8000"
    with patch.dict(sys.modules, {"network": network, "config": config}):
        spec = importlib.util.spec_from_file_location("test_transport", TRANSPORT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeSocket:
    def __init__(self, reply):
        self.reply = reply
        self.sent = b""
        self.address = None
        self.closed = False

    def settimeout(self, seconds):
        self.timeout = seconds

    def connect(self, address):
        self.address = address

    def send(self, data):
        # Ověřuje i částečný zápis do socketu.
        count = min(len(data), 17)
        self.sent += data[:count]
        return count

    def recv(self, _size):
        data, self.reply = self.reply[:23], self.reply[23:]
        return data

    def close(self):
        self.closed = True


class TransportTests(unittest.TestCase):
    def test_mdns_compressed_answer(self):
        module = load_transport()
        question = b"\x07macmini\x05local\0\0\1\x80\1"
        answer = b"\xc0\x0c\0\1\0\1\0\0\0\x78\0\4\xc0\xa8\x01\x0a"
        packet = b"\0\0\x84\0\0\1\0\1\0\0\0\0" + question + answer

        class MdnsSocket:
            def settimeout(self, value):
                self.timeout = value

            def sendto(self, data, address):
                self.query = data
                self.address = address

            def recvfrom(self, _size):
                return packet, ("192.168.1.10", 5353)

            def close(self):
                pass

        sock = MdnsSocket()
        module.socket = types.SimpleNamespace(
            AF_INET=2, SOCK_DGRAM=2, socket=lambda *_: sock
        )
        self.assertEqual(module._mdns_ip("macmini.local"), "192.168.1.10")
        self.assertEqual(sock.address, ("224.0.0.251", 5353))
        self.assertTrue(sock.query.endswith(question))

    def test_post_sends_contract_and_parses_reply(self):
        module = load_transport()
        body = {"boot_id": "boot1", "sent_at_ticks": 5000, "pulses_ticks": [4500]}
        result = {"received": 1, "stored": 1, "day": "2026-09-27", "latest": None}
        payload = json.dumps(result).encode()
        reply = (
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(payload)).encode()
            + b"\r\n\r\n"
            + payload
        )
        sock = FakeSocket(reply)
        module.socket = types.SimpleNamespace(socket=lambda: sock)
        module._mdns_ip = lambda host: "192.168.1.10"

        self.assertEqual(module.post_pulses(body), result)
        self.assertEqual(sock.address, ("192.168.1.10", 8000))
        self.assertIn(b"POST /pulses HTTP/1.0\r\n", sock.sent)
        self.assertIn(b"Host: macmini.local:8000\r\n", sock.sent)
        self.assertEqual(json.loads(sock.sent.split(b"\r\n\r\n", 1)[1]), body)
        self.assertTrue(sock.closed)

    def test_failed_post_keeps_batch_for_retry(self):
        module = load_transport()
        sock = FakeSocket(b"HTTP/1.1 503 Unavailable\r\n\r\n")
        module.socket = types.SimpleNamespace(socket=lambda: sock)
        module._mdns_ip = lambda host: "192.168.1.10"

        self.assertIsNone(module.post_pulses({"pulses_ticks": [123]}))
        self.assertIsNone(module._server_ip)
        self.assertTrue(sock.closed)


if __name__ == "__main__":
    unittest.main()
