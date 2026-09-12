#pragma once
#include <stdint.h>
#include <stddef.h>
namespace mesh {
constexpr size_t PACKET_SIZE = 18;
constexpr uint8_t VERSION = 1, EMPTY = 0, TELEMETRY = 1;
inline uint16_t crc16(const uint8_t* p, size_t n) {
    uint16_t c = 0xffff;
    while (n--) { c ^= uint16_t(*p++) << 8; for (int i=0;i<8;i++) c = (c & 0x8000) ? (c<<1)^0x1021 : c<<1; }
    return c;
}
inline void put32(uint8_t* p, uint32_t x) { for (int i=0;i<4;i++) p[i]=uint8_t(x>>(i*8)); }
inline uint32_t get32(const uint8_t* p) { uint32_t x=0; for (int i=0;i<4;i++) x |= uint32_t(p[i])<<(i*8); return x; }
inline void encode(uint8_t* p, uint8_t type, uint32_t seq, uint32_t uptime, int16_t sensor, uint32_t overflow) {
    p[0]=VERSION; p[1]=type; put32(p+2,seq); put32(p+6,uptime);
    p[10]=uint8_t(sensor); p[11]=uint8_t(uint16_t(sensor)>>8); put32(p+12,overflow);
    uint16_t c=crc16(p,16); p[16]=uint8_t(c); p[17]=uint8_t(c>>8);
}
enum Reason { ALLOWED, MALFORMED, CHECKSUM, VERSION_BAD, UNKNOWN_TYPE, RATE_LIMIT, QUARANTINE, IS_EMPTY, TRANSPORT, REASON_COUNT };
inline const char* reasonName(Reason r) {
    static const char* names[]={"allowed","malformed","checksum","version","unknown_type","rate_limit","quarantine","empty","transport"}; return names[r];
}
inline Reason validate(const uint8_t* p, size_t n) {
    if(n!=PACKET_SIZE) return MALFORMED;
    if(crc16(p,16)!=(uint16_t(p[16]) | uint16_t(p[17])<<8)) return CHECKSUM;
    if(p[0]!=VERSION) return VERSION_BAD;
    if(p[1]==EMPTY) return IS_EMPTY;
    return p[1]==TELEMETRY ? ALLOWED : UNKNOWN_TYPE;
}
}
