#include "../shared/policy.h"
#include "../shared/command.h"
#include <assert.h>
#include <stdio.h>
int main() {
    assert(mesh::crc16((const uint8_t*)"123456789",9)==0x29b1);
    uint8_t p[mesh::PACKET_SIZE];mesh::encode(p,1,1,1000,2200,0);
    const uint8_t expected[]={1,1,1,0,0,0,0xe8,3,0,0,0x98,8,0,0,0,0,0x54,0x1e};
    assert(!memcmp(p,expected,sizeof p));
    for(auto b:p) printf("%02x",b); puts("");
    assert(mesh::validate(p,sizeof p)==mesh::ALLOWED);
    mesh::Policy policy;
    for(int i=0;i<5;i++) assert(policy.evaluate(p,sizeof p,0)==mesh::ALLOWED);
    for(int i=1;i<=3;i++) assert(policy.evaluate(p,sizeof p,i)==mesh::RATE_LIMIT);
    assert(policy.remaining(3)==15000);
    assert(policy.evaluate(p,sizeof p,1000)==mesh::QUARANTINE);
    assert(policy.remaining(1000)==14003);
    assert(policy.evaluate(p,sizeof p,15003)==mesh::ALLOWED);
    mesh::Policy wrap;wrap.release(0xfffffff0);wrap.contain(0xfffffff0,15000);
    assert(wrap.remaining(0x10)==14968);
    assert(wrap.evaluate(p,sizeof p,uint32_t(0xfffffff0+15000U))==mesh::ALLOWED);
    mesh::Policy rolling;
    mesh::encode(p,127,1,0,0,0);
    rolling.evaluate(p,sizeof p,0);rolling.evaluate(p,sizeof p,10000);
    assert(rolling.violationCount==1);
    rolling.evaluate(p,sizeof p,10001);rolling.evaluate(p,sizeof p,10002);
    assert(rolling.remaining(10002)==15000);
    mesh::Command c;
    assert(mesh::parseCommand("{\"session\":1,\"id\":2,\"op\":\"quarantine\",\"node\":2,\"duration_ms\":15000}",c));
    assert(c.id==2 && c.duration==15000);
    const char* bad[]={"", "{", "{}", "{\"id\":4294967296}", "{\"id\":01}", "{\"op\":\"unterminated", "{\"session\":1,\"id\":2,\"op\":\"state\",\"node\":1,\"node\":2}"};
    for(auto s:bad) {mesh::Command invalid;assert(!mesh::parseCommand(s,invalid));}
    puts("Native protocol, policy, wraparound and parser checks passed.");
}
