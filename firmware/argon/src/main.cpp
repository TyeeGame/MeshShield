#include "Particle.h"
#include "rng_hal.h"
#include "protocol.h"
#include "policy.h"
#include "command.h"
#include "traffic.h"
#include "message.h"
#include <stdarg.h>
SYSTEM_MODE(MANUAL);
namespace {
constexpr size_t LINE=1536; constexpr unsigned TX_SLOTS=6;
char tx[TX_SLOTS][LINE]; uint16_t lengths[TX_SLOTS]; unsigned txHead=0,txTail=0,txCount=0,txOffset=0;
uint32_t session=0,eventSeq=0,logDrops=0,lastCommand=0,lastSummary=0;
struct Node {
    mesh::Policy policy;
    uint32_t lastSeen=0,lastMessage=0,overflowDelta=0;
    uint32_t counts[mesh::REASON_COUNT]={0};
    uint32_t received=0,allowed=0,blocked=0,lastSample=0;
    bool seen=false,messageSeen=false,quarantineSeen=false;
} nodes[2];
struct Ack { uint32_t id=0; unsigned node=0; char op[16]={0}; uint32_t duration=0; } cache[16];
unsigned cacheNext=0;
uint8_t messageKey[16]={0}; bool messageConfigured=false;
uint32_t lastMessageId=0;
mesh::Policy messagePolicies[2];
void emit(const char* type,const char* format,...) {
    uint32_t seq=++eventSeq;
    if(txCount==TX_SLOTS || !Serial.isConnected()) { ++logDrops; return; }
    char* out=tx[txHead];
    int prefix=snprintf(out,LINE,"{\"v\":1,\"session\":%lu,\"seq\":%lu,\"type\":\"%s\",",(unsigned long)session,(unsigned long)seq,type);
    va_list args; va_start(args,format); int n=vsnprintf(out+prefix,LINE-prefix,format,args); va_end(args);
    if(n<0 || size_t(prefix+n+3)>=LINE) { ++logDrops; return; }
    size_t len=prefix+n; out[len++]='}';out[len++]='\n'; out[len]=0;
    lengths[txHead]=len; txHead=(txHead+1)%TX_SLOTS; ++txCount;
}
void pumpTx() {
    if(!Serial.isConnected()) { txCount=txHead=txTail=txOffset=0; return; }
    unsigned budget=128;
    while(txCount && budget-- && Serial.availableForWrite()>0) {
        if(Serial.write(uint8_t(tx[txTail][txOffset]))!=1) break;
        if(++txOffset==lengths[txTail]) { txOffset=0;txTail=(txTail+1)%TX_SLOTS;--txCount; }
    }
}
void ack(const mesh::Command& c,const char* status,bool duplicate,uint32_t now) {
    unsigned i=c.node==2?1:0;
    emit("ack","\"id\":%lu,\"node\":%lu,\"status\":\"%s\",\"duplicate\":%s,\"quarantine_ms\":%lu,\"last_command_id\":%lu",
         (unsigned long)c.id,(unsigned long)c.node,status,duplicate?"true":"false",(unsigned long)nodes[i].policy.remaining(now),(unsigned long)lastCommand);
}
void acceptTraffic(unsigned i,const uint8_t* data,size_t read,uint32_t after);
void command(const char* line,uint32_t now) {
    if(!strncmp(line,"K,",2)) {
        uint32_t boot=0,id=0;uint8_t key[16];
        if(mesh::parseMessageKey(line,boot,id,key) && boot==session) {
            memcpy(messageKey,key,sizeof messageKey);messageConfigured=true;
            lastMessageId=0;
            emit("message_ready","\"id\":%lu",(unsigned long)id);
        } else emit("error","\"reason\":\"malformed_command\"");
        return;
    }
    if(!strncmp(line,"M,",2)) {
        uint32_t boot=0,id=0;uint8_t key[16],body[mesh::MESSAGE_MAX];size_t size=0;
        if(!mesh::parseMessage(line,boot,id,key,body,size) || boot!=session || !messageConfigured) {
            emit("error","\"reason\":\"malformed_command\"");return;
        }
        if(id<=lastMessageId) return;
        lastMessageId=id;
        uint8_t difference=0;for(unsigned i=0;i<16;i++) difference|=key[i]^messageKey[i];
        unsigned slot=difference?1:0;
        uint8_t packet[mesh::PACKET_SIZE];mesh::encode(packet,difference?127:1,id,now,0,0);
        mesh::Reason result=messagePolicies[slot].evaluate(packet,sizeof packet,now);
        const char* reason=result==mesh::UNKNOWN_TYPE?"unauthorized":mesh::reasonName(result);
        emit("message_decision","\"id\":%lu,\"slot\":%u,\"reason\":\"%s\",\"quarantine_ms\":%lu",
             (unsigned long)id,slot+1,reason,(unsigned long)messagePolicies[slot].remaining(now));
        return;
    }
    if(!strncmp(line,"T,",2)) {
        uint32_t boot=0,node=0; uint8_t data[mesh::PACKET_SIZE];
        if(mesh::parseTraffic(line,boot,node,data) && boot==session) acceptTraffic(node-1,data,sizeof data,now);
        else emit("error","\"reason\":\"malformed_command\"");
        return;
    }
    mesh::Command c;
    if(!mesh::parseCommand(line,c)) { emit("error","\"reason\":\"malformed_command\"");return; }
    if(c.session!=session) { ack(c,"wrong_session",false,now); return; }
    if(c.node<1 || c.node>2 || !c.id ||
       (strcmp(c.op,"quarantine") && strcmp(c.op,"release") && strcmp(c.op,"state")) ||
       (!strcmp(c.op,"quarantine") ? (c.duration<1 || c.duration>60000) : c.duration!=0)) {
        ack(c,"invalid_command",false,now); return;
    }
    if(c.id<=lastCommand) {
        for(auto& a:cache) if(a.id==c.id) {
            bool same=a.node==c.node && a.duration==c.duration && !strcmp(a.op,c.op);
            ack(c,same?"ok":"id_conflict",same,now); return;
        }
        ack(c,"stale_id",true,now);return;
    }
    Node& n=nodes[c.node-1];
    if(!strcmp(c.op,"quarantine")) { n.policy.contain(now,c.duration);n.quarantineSeen=true; }
    if(!strcmp(c.op,"release")) n.policy.release(now);
    lastCommand=c.id; Ack& a=cache[cacheNext];cacheNext=(cacheNext+1)%16;
    a.id=c.id;a.node=c.node;a.duration=c.duration;strcpy(a.op,c.op);
    ack(c,"ok",false,now); // action precedes acknowledgement
}
void pumpRx(uint32_t now) {
    static char line[416];static size_t used=0;static bool dropping=false;
    unsigned budget=128;
    while(budget-- && Serial.available()) {
        char c=Serial.read();
        if(c=='\n') { if(!dropping) {line[used]=0;command(line,now);} else emit("error","\"reason\":\"command_too_long\"");used=0;dropping=false; }
        else if(used<sizeof(line)-1 && !dropping) line[used++]=c;
        else dropping=true;
    }
}
void acceptTraffic(unsigned i,const uint8_t* data,size_t read,uint32_t after) {
    Node& n=nodes[i];
    n.policy.expire(after);
    n.lastSeen=after;n.seen=true;
    mesh::Reason r=n.policy.evaluate(data,read,after); ++n.counts[r];
    if(r==mesh::IS_EMPTY) return;
    ++n.received;n.lastMessage=after;n.messageSeen=true;
    if(r==mesh::ALLOWED) {
        ++n.allowed;
        if(uint32_t(after-n.lastSample)>=1000) {
            n.lastSample=after;
            emit("telemetry","\"node\":%u,\"packet_seq\":%lu,\"uptime_ms\":%lu,\"sensor\":%d",i+1,(unsigned long)mesh::get32(data+2),(unsigned long)mesh::get32(data+6),int(int16_t(uint16_t(data[10])|uint16_t(data[11])<<8)));
        }
    } else {
        ++n.blocked;
        // At most three incidents per node per interval; summary retains all counts.
        if(n.blocked<=3) emit("incident","\"node\":%u,\"reason\":\"%s\"",i+1,mesh::reasonName(r));
    }
    if(n.policy.remaining(after)) n.quarantineSeen=true;
}
void summary(uint32_t now) {
    char body[1250];size_t pos=0;
    pos+=snprintf(body+pos,sizeof(body)-pos,"\"ingress\":\"usb_virtual\",\"messages\":1,\"duration_ms\":%lu,\"uptime_ms\":%lu,\"log_drops\":%lu,\"last_command_id\":%lu,\"nodes\":[",(unsigned long)uint32_t(now-lastSummary),(unsigned long)now,(unsigned long)logDrops,(unsigned long)lastCommand);
    for(unsigned i=0;i<2;i++) {
        Node& n=nodes[i];n.policy.expire(now);
        pos+=snprintf(body+pos,sizeof(body)-pos,"%s{\"node\":%u,\"received\":%lu,\"allowed\":%lu,\"blocked\":%lu,\"transport\":%lu,\"empty\":%lu,\"queue_overflow\":%lu,\"quarantine_ms\":%lu,\"contaminated\":%s,\"seen_age_ms\":%ld,\"message_age_ms\":%ld,\"reasons\":{",i?",":"",i+1,(unsigned long)n.received,(unsigned long)n.allowed,(unsigned long)n.blocked,(unsigned long)n.counts[mesh::TRANSPORT],(unsigned long)n.counts[mesh::IS_EMPTY],(unsigned long)n.overflowDelta,(unsigned long)n.policy.remaining(now),n.quarantineSeen?"true":"false",n.seen?(long)uint32_t(now-n.lastSeen):-1L,n.messageSeen?(long)uint32_t(now-n.lastMessage):-1L);
        for(int r=mesh::MALFORMED;r<=mesh::QUARANTINE;r++) pos+=snprintf(body+pos,sizeof(body)-pos,"%s\"%s\":%lu",r>mesh::MALFORMED?",":"",mesh::reasonName(mesh::Reason(r)),(unsigned long)n.counts[r]);
        pos+=snprintf(body+pos,sizeof(body)-pos,"}}");
        memset(n.counts,0,sizeof n.counts);n.received=n.allowed=n.blocked=n.overflowDelta=0;n.quarantineSeen=false;
    }
    snprintf(body+pos,sizeof(body)-pos,"]");emit("summary","%s",body);lastSummary=now;
}
}
void setup() {
    Serial.begin(115200);Serial.blockOnOverrun(false);
    RGB.control(true);RGB.brightness(40);RGB.color(0x008080);
    session=HAL_RNG_GetRandomNumber();if(!session) session=1;lastSummary=millis();
    // USB-only gateway: no external wiring or network provisioning.
}
void loop() {
    uint32_t now=millis();pumpRx(now);
    for(auto& n:nodes) {
        if(n.policy.remaining(now)) n.quarantineSeen=true;
        n.policy.expire(now);
    }
    now=millis();if(uint32_t(now-lastSummary)>=1000) summary(now);
    RGB.color(nodes[0].policy.remaining(now)||nodes[1].policy.remaining(now)||
              messagePolicies[0].remaining(now)||messagePolicies[1].remaining(now)?0xd03020:0x008080);
    pumpTx();
}
