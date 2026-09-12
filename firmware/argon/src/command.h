#pragma once
#include <stdint.h>
#include <string.h>
#include <ctype.h>
namespace mesh {
struct Command { uint32_t session=0,id=0,node=0,duration=0; char op[16]={0}; };
// Strict, flat JSON subset: five mandatory fields; ASCII strings without escapes.
inline void space(const char*& p) { while(*p && isspace((unsigned char)*p)) ++p; }
inline bool str(const char*& p,char* out,size_t cap) {
    space(p); if(*p++!='"') return false; size_t n=0;
    while(*p && *p!='"') { if((unsigned char)*p<32 || *p=='\\' || n+1>=cap) return false; out[n++]=*p++; }
    if(*p!='"') return false; ++p; out[n]=0; return true;
}
inline bool number(const char*& p,uint32_t& n) {
    space(p); if(!isdigit((unsigned char)*p)) return false; n=0;
    bool zero=*p=='0'; unsigned digits=0;
    while(isdigit((unsigned char)*p)) {
        unsigned d=*p++-'0'; if(n>429496729 || (n==429496729 && d>5)) return false;
        n=n*10+d; ++digits;
    }
    return !zero || digits==1;
}
inline bool parseCommand(const char* p,Command& c) {
    space(p); if(*p++!='{') return false; unsigned fields=0;
    for(unsigned i=0;i<5;i++) {
        char key[20]; if(!str(p,key,sizeof key)) return false;
        space(p); if(*p++!=':') return false;
        unsigned bit=0; uint32_t* dst=nullptr;
        if(!strcmp(key,"session")) {bit=1;dst=&c.session;}
        else if(!strcmp(key,"id")) {bit=2;dst=&c.id;}
        else if(!strcmp(key,"node")) {bit=4;dst=&c.node;}
        else if(!strcmp(key,"duration_ms")) {bit=8;dst=&c.duration;}
        else if(!strcmp(key,"op")) bit=16;
        else return false;
        if(fields&bit) return false; fields|=bit;
        if(dst) { if(!number(p,*dst)) return false; }
        else if(!str(p,c.op,sizeof c.op)) return false;
        space(p); if(i<4) { if(*p++!=',') return false; }
    }
    space(p); if(*p++!='}') return false; space(p); return !*p && fields==31;
}
}
