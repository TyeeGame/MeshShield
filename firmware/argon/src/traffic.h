#pragma once
#include "protocol.h"
#include "command.h"
namespace mesh {
inline int hexDigit(char c) {
    if(c>='0' && c<='9') return c-'0';
    if(c>='a' && c<='f') return c-'a'+10;
    if(c>='A' && c<='F') return c-'A'+10;
    return -1;
}
// T,<boot session>,<virtual slot>,<36 packet hex digits>. Host slots are not authentication.
inline bool parseTraffic(const char* p,uint32_t& session,uint32_t& node,uint8_t* packet) {
    if(strncmp(p,"T,",2)) return false;
    p+=2;
    if(!number(p,session) || *p++!=',' || !number(p,node) || *p++!=',') return false;
    if(!session || node<1 || node>2 || strlen(p)!=PACKET_SIZE*2) return false;
    for(size_t i=0;i<PACKET_SIZE;i++) {
        int a=hexDigit(p[i*2]),b=hexDigit(p[i*2+1]);
        if(a<0 || b<0) return false;
        packet[i]=uint8_t((a<<4)|b);
    }
    return true;
}
}
