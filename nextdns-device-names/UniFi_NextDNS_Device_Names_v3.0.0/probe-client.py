#!/usr/bin/env python3
"""Run on a LAN computer, then inspect /run/nextdns-device-names/proof.json.

Uses Python's standard library. The generated query is forwarded through the
normal LAN DNS listener. It deliberately supplies no EDNS device metadata; the
router must attach the actual requesting computer's identity itself.
"""
import argparse
import hashlib
import secrets
import socket
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--router', default='192.168.1.1')
parser.add_argument('--port', type=int, default=53)
parser.add_argument('--tcp', action='store_true', help='Use DNS over TCP on the LAN hop.')
args = parser.parse_args()
name = 'ndn-check-' + secrets.token_hex(8) + '.example.com'
ident = secrets.token_bytes(2)
question = b''.join(bytes([len(label)]) + label.encode() for label in name.split('.')) + b'\0\x00\x01\x00\x01'
packet = ident + struct.pack('!5H', 0x100, 1, 0, 0, 0) + question
with socket.socket(socket.AF_INET, socket.SOCK_STREAM if args.tcp else socket.SOCK_DGRAM) as sock:
    sock.settimeout(5)
    if args.tcp:
        sock.connect((args.router, args.port))
        sock.sendall(struct.pack('!H', len(packet)) + packet)
        def read_exact(size):
            data = b''
            while len(data) < size:
                part = sock.recv(size - len(data))
                if not part:
                    raise SystemExit('The DNS TCP connection closed early.')
                data += part
            return data
        response = read_exact(struct.unpack('!H', read_exact(2))[0])
    else:
        sock.sendto(packet, (args.router, args.port))
        response, _ = sock.recvfrom(65535)
if len(response) < 12 or response[:2] != ident or response[3] & 15 not in (0, 3):
    raise SystemExit('DNS check failed.')
print('DNS reply received. Match this query_sha256 in the router proof file:')
print(hashlib.sha256(name.encode()).hexdigest())
