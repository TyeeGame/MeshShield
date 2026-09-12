"""Fixed 18-byte, little-endian packets; CRC is corruption detection only."""
import binascii
import struct
PACKET_SIZE = 18
REASONS = ('malformed', 'checksum', 'version', 'unknown_type', 'rate_limit', 'quarantine')

def packet(kind=1, seq=0, uptime=0, sensor=2200, overflow=0, version=1):
    body = struct.pack('<BBIIhI', version, kind, seq & 0xffffffff, uptime & 0xffffffff, sensor, overflow)
    return body + struct.pack('<H', binascii.crc_hqx(body, 0xffff))

def validate(data):
    if len(data) != PACKET_SIZE:
        return 'malformed'
    if binascii.crc_hqx(data[:16], 0xffff) != int.from_bytes(data[16:], 'little'):
        return 'checksum'
    if data[0] != 1:
        return 'version'
    return {0: 'empty', 1: 'allowed'}.get(data[1], 'unknown_type')
