#pragma once
#include "protocol.h"
namespace mesh {
struct Policy {
    uint32_t lastRefill=0, quarantineStart=0, quarantineDuration=0;
    uint32_t violations[3]={0,0,0}; unsigned violationCount=0;
    float tokens=5;
    uint32_t remaining(uint32_t now) const {
        uint32_t elapsed=now-quarantineStart;
        return quarantineDuration && elapsed<quarantineDuration ? quarantineDuration-elapsed : 0;
    }
    void release(uint32_t now) { quarantineDuration=0; violationCount=0; tokens=5; lastRefill=now; }
    void contain(uint32_t now,uint32_t duration) { quarantineStart=now; quarantineDuration=duration; }
    void expire(uint32_t now) { if(quarantineDuration && !remaining(now)) release(now); }
    Reason evaluate(const uint8_t* p,size_t len,uint32_t now) {
        expire(now);
        Reason r=validate(p,len);
        if(r==IS_EMPTY) return r;
        if(remaining(now)) return QUARANTINE;
        if(r==ALLOWED) {
            tokens += float(uint32_t(now-lastRefill))*0.005f;
            if(tokens>5) tokens=5;
            lastRefill=now;
            if(tokens>=1) tokens-=1; else r=RATE_LIMIT;
        }
        if(r!=ALLOWED) {
            unsigned keep=0;
            for(unsigned i=0;i<violationCount;i++) if(uint32_t(now-violations[i])<10000) violations[keep++]=violations[i];
            violationCount=keep; violations[violationCount++]=now;
            if(violationCount==3) { contain(now,15000); violationCount=0; }
        }
        return r;
    }
};
}
