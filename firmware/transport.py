"""Wi-Fi a odesílání otáček z ESP8266 na Steve Server."""

import json
import network
import socket
import time

import config


_wlan = network.WLAN(network.STA_IF)
_server_ip = None


def _read_name(packet, offset):
    """Přečte DNS jméno včetně komprimovaných ukazatelů."""
    labels = []
    end = None
    for _ in range(20):
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if end is None:
                end = offset + 2
            offset = pointer
        elif length == 0:
            return b".".join(labels).decode(), end or offset + 1
        else:
            offset += 1
            labels.append(packet[offset:offset + length])
            offset += length
    raise ValueError("Neplatná mDNS odpověď")


def _mdns_ip(host):
    name = b"".join(bytes((len(part),)) + part.encode() for part in host.split("."))
    # QU bit žádá odpověď na náš port, ne multicast na 5353.
    query = b"\0\0\0\0\0\1\0\0\0\0\0\0" + name + b"\0\0\1\x80\x01"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(2)
        sock.sendto(query, ("224.0.0.251", 5353))
        for _ in range(3):
            packet, _ = sock.recvfrom(512)
            offset = 12
            questions = (packet[4] << 8) | packet[5]
            answers = (packet[6] << 8) | packet[7]
            for _ in range(questions):
                _, offset = _read_name(packet, offset)
                offset += 4
            for _ in range(answers):
                answer_name, offset = _read_name(packet, offset)
                record_type = (packet[offset] << 8) | packet[offset + 1]
                data_length = (packet[offset + 8] << 8) | packet[offset + 9]
                offset += 10
                if answer_name.lower() == host.lower() and record_type == 1 and data_length == 4:
                    return ".".join(str(x) for x in packet[offset:offset + 4])
                offset += data_length
    finally:
        sock.close()
    raise OSError("macmini.local neodpovídá na mDNS")


def _connect_wifi():
    if _wlan.isconnected():
        return True
    _wlan.active(True)
    _wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    started = time.ticks_ms()
    while not _wlan.isconnected() and time.ticks_diff(time.ticks_ms(), started) < 8000:
        time.sleep_ms(100)
    return _wlan.isconnected()


def post_pulses(body):
    """Vrátí JSON odpověď, nebo None; neúspěšnou dávku je třeba zopakovat."""
    global _server_ip
    try:
        if not _connect_wifi():
            print("Wi-Fi není připojená:", config.WIFI_SSID)
            return None

        address = config.SERVER_URL.split("://", 1)[1].split("/", 1)[0]
        host, port = address.split(":", 1)
        port = int(port)
        if _server_ip is None:
            if host.endswith(".local"):
                _server_ip = _mdns_ip(host)
            else:
                _server_ip = socket.getaddrinfo(host, port)[0][-1][0]

        data = json.dumps(body).encode()
        header = (
            "POST /pulses HTTP/1.0\r\n"
            "Host: {}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(address, len(data)).encode()

        sock = socket.socket()
        try:
            sock.settimeout(10)
            sock.connect((_server_ip, port))
            request = header + data
            while request:
                sent = sock.send(request)
                if sent <= 0:
                    raise OSError("Spojení se serverem bylo přerušeno")
                request = request[sent:]

            response = b""
            while True:
                part = sock.recv(512)
                if not part:
                    break
                response += part
                if len(response) > 4096:
                    raise ValueError("Příliš velká odpověď serveru")
        finally:
            sock.close()

        head, payload = response.split(b"\r\n\r\n", 1)
        if not head.startswith(b"HTTP/1.1 200 ") and not head.startswith(b"HTTP/1.0 200 "):
            raise ValueError("Server odmítl dávku: " + head.split(b"\r\n", 1)[0].decode())
        return json.loads(payload)
    except (OSError, ValueError, IndexError) as exc:
        _server_ip = None
        print("Odeslání selhalo:", exc)
        return None
