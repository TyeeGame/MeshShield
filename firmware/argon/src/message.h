#pragma once
#include "traffic.h"
namespace mesh {
constexpr size_t MESSAGE_MAX = 160;
inline bool readHex(const char*& p, uint8_t* out, size_t count) {
    if(strlen(p)<count*2) return false;
    for(size_t i=0;i<count;i++) {
        int a=hexDigit(*p++), b=hexDigit(*p++);
        if(a<0 || b<0) return false;
        out[i]=uint8_t((a<<4)|b);
    }
    return true;
}
// Provisioning is trusted USB management. Never expose this command on the LAN.
inline bool parseMessageKey(const char* p,uint32_t& boot,uint32_t& id,uint8_t* key) {
    if(strncmp(p,"K,",2)) return false;
    p+=2;
    return number(p,boot) && *p++==',' && number(p,id) && *p++==',' &&
        boot && id && readHex(p,key,16) && !*p;
}
inline bool parseMessage(const char* p,uint32_t& boot,uint32_t& id,uint8_t* key,uint8_t* body,size_t& size) {
    if(strncmp(p,"M,",2)) return false;
    p+=2;
    if(!number(p,boot) || *p++!=',' || !number(p,id) || *p++!=',' || !boot || !id ||
       !readHex(p,key,16) || *p++!=',') return false;
    size_t hexSize=strlen(p);
    if(!hexSize || hexSize%2 || hexSize>MESSAGE_MAX*2) return false;
    size=hexSize/2;
    return readHex(p,body,size) && !*p;
}
}
