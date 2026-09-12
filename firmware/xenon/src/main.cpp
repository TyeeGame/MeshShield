#include "Particle.h"
#include "protocol.h"
#include "node_config.h"
SYSTEM_MODE(MANUAL);
static_assert(MESH_NODE==1 || MESH_NODE==2,"Select node 1 or 2");
namespace {
constexpr uint8_t QUEUE_SIZE=8;
uint8_t queueData[QUEUE_SIZE][mesh::PACKET_SIZE], emptyPacket[mesh::PACKET_SIZE];
volatile uint8_t head=0,tail=0,count=0;
uint32_t seq=0,overflow=0,nextSend=0,lastButtonChange=0;
int mode=0,lastRaw=HIGH,stableButton=HIGH;
const char* modes[]={"NORMAL","UNKNOWN_TYPE","FLOOD","ANOMALY"};
// Only copies precomputed bytes; HAL copies them to its own fixed TX buffer.
void requested() {
    if(count) { Wire.write(queueData[tail],mesh::PACKET_SIZE); tail=(tail+1)%QUEUE_SIZE; --count; }
    else Wire.write(emptyPacket,mesh::PACKET_SIZE);
}
void received(int n) { for(int i=0;i<n && i<32;i++) if(Wire.available()) Wire.read(); }
void prepareEmpty(uint32_t now) {
    uint8_t p[mesh::PACKET_SIZE]; mesh::encode(p,mesh::EMPTY,seq,now,0,overflow);
    noInterrupts(); memcpy(emptyPacket,p,sizeof p); interrupts();
}
void announce() {
    if(Serial.isConnected()) Serial.printlnf("node=%d mode=%s queue_overflow=%lu",MESH_NODE,modes[mode],(unsigned long)overflow);
    const uint32_t colors[]={0x00a060,0xe09000,0xe02020,0xa030e0}; RGB.color(colors[mode]);
}
}
void setup() {
    Serial.begin(115200); Serial.blockOnOverrun(false);
    RGB.control(true); RGB.brightness(40); announce();
    pinMode(D4,INPUT_PULLUP); prepareEmpty(millis());
    Wire.onRequest(requested); Wire.onReceive(received); Wire.begin(0x20+MESH_NODE);
    nextSend=millis()+1000;
}
void loop() {
    uint32_t now=millis();
    if(MESH_NODE==2) {
        int raw=digitalRead(D4);
        if(raw!=lastRaw) { lastRaw=raw; lastButtonChange=now; }
        if(raw!=stableButton && uint32_t(now-lastButtonChange)>=35) {
            stableButton=raw;
            if(raw==LOW) { mode=(mode+1)%4; nextSend=now; announce(); }
        }
    }
    if(int32_t(now-nextSend)>=0) {
        uint8_t p[mesh::PACKET_SIZE];
        mesh::encode(p,mode==1?0x7f:mesh::TELEMETRY,++seq,now,2200+int(random(-20,21)),overflow);
        noInterrupts();
        if(count<QUEUE_SIZE) { memcpy(queueData[head],p,sizeof p); head=(head+1)%QUEUE_SIZE; ++count; }
        else ++overflow;
        interrupts();
        nextSend=now+(mode==2?50:mode==3?250:1000+int(random(-40,41)));
    }
    prepareEmpty(now);
    static uint32_t lastDebug=0;
    if(uint32_t(now-lastDebug)>=3000) { lastDebug=now; announce(); }
}
