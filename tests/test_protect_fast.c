#define _GNU_SOURCE
#include "runtime.h"
#include <assert.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Minimal stubs so test_protect_fast links directly against src/runtime_memory.c. */
int runtime_sotc_neo(void) { return 0; }
uintptr_t runtime_lookup(const RuntimeExport *table, size_t count, const char *nid) {
    (void)table;
    (void)count;
    (void)nid;
    return 0;
}

extern void runtime_memory_gpu_protect(uintptr_t address, uint64_t size, int read, int write);
extern void runtime_memory_lock_stats(uint64_t *writes, double *wait_ms, double *hold_ms, double *worst_ms);
extern void runtime_memory_lock_stats2(double *worst_hold_ms, uint64_t *read_waits, double *read_wait_ms);
extern void runtime_memory_lock_sites(char *readers, char *writers, size_t capacity);

typedef int32_t (ABI *Allocate)(int64_t, int64_t, uint64_t, uint64_t, int, int64_t *);
typedef int32_t (ABI *Map)(void **, uint64_t, int, int, int64_t, uint64_t);
typedef int32_t (ABI *Unmap)(void *, uint64_t);
typedef int32_t (ABI *Release)(uint64_t, uint64_t);

static sigjmp_buf fault_env;
static volatile sig_atomic_t fault_armed;
static volatile sig_atomic_t fault_count;

static void segv_handler(int sig) {
    (void)sig;
    if (fault_armed) {
        fault_armed = 0;
        ++fault_count;
        siglongjmp(fault_env, 1);
    }
    abort();
}

static int try_write_u32(volatile uint32_t *ptr, uint32_t val) {
    if (sigsetjmp(fault_env, 1) == 0) {
        fault_armed = 1;
        *ptr = val;
        fault_armed = 0;
        return 1;
    }
    return 0;
}

static int try_read_u32(volatile uint32_t *ptr, uint32_t *out) {
    if (sigsetjmp(fault_env, 1) == 0) {
        fault_armed = 1;
        *out = *ptr;
        fault_armed = 0;
        return 1;
    }
    return 0;
}

int main(void) {
    setenv("SOTC_PROTECT_FAST", "1", 1);
    setenv("SOTC_PROTECT_SPAN", "1", 1);

    struct sigaction sa = {0};
    sa.sa_handler = segv_handler;
    sigemptyset(&sa.sa_mask);
    assert(sigaction(SIGSEGV, &sa, NULL) == 0);

    Allocate alloc_fn = (Allocate)runtime_memory_resolve("rTXw65xmLIA");
    Map map_fn = (Map)runtime_memory_resolve("L-Q3LEjIbgA");
    Release rel_fn = (Release)runtime_memory_resolve("MBuItvba6z8");
    Unmap unmap_fn = (Unmap)runtime_memory_resolve("cQke9UuBQOk");
    assert(alloc_fn && map_fn && rel_fn && unmap_fn);

    const uint64_t blk = UINT64_C(64) << 10;
    int64_t phys1 = 0, phys2 = 0, phys3 = 0;
    assert(alloc_fn(0, blk * 16, blk, blk, 0, &phys1) == 0);
    assert(alloc_fn(0, blk * 16, blk, blk, 0, &phys2) == 0);
    assert(alloc_fn(0, blk * 16, blk, blk, 0, &phys3) == 0);

    /* Two adjacent mapped regions (same prot: coalesced by Linux protect_fast), a gap, then a third. */
    void *p1 = (void *)(uintptr_t)0x1000000000ULL;
    void *p2 = (void *)(uintptr_t)(0x1000000000ULL + blk);
    void *p3 = (void *)(uintptr_t)(0x1000000000ULL + 3 * blk);
    assert(map_fn(&p1, blk, 0x33, 0x10, phys1, blk) == 0);
    assert(map_fn(&p2, blk, 0x33, 0x10, phys2, blk) == 0);
    assert(map_fn(&p3, blk, 0x33, 0x10, phys3, blk) == 0);

    volatile uint32_t *u1 = (volatile uint32_t *)p1;
    volatile uint32_t *u2 = (volatile uint32_t *)p2;
    volatile uint32_t *u3 = (volatile uint32_t *)p3;
    assert(try_write_u32(u1, 0x11111111u));
    assert(try_write_u32(u2, 0x22222222u));
    assert(try_write_u32(u3, 0x33333333u));

    /* Read-only protection across adjacent regions + gap + third region. */
    runtime_memory_gpu_protect((uintptr_t)p1, 4 * blk, 1, 0);
    uint32_t val = 0;
    assert(try_read_u32(u1, &val) && val == 0x11111111u);
    assert(try_read_u32(u2, &val) && val == 0x22222222u);
    assert(try_read_u32(u3, &val) && val == 0x33333333u);
    assert(!try_write_u32(u1, 0xdead0001u));
    assert(!try_write_u32(u2, 0xdead0002u));
    assert(!try_write_u32(u3, 0xdead0003u));
    assert(fault_count == 3);

    /* PROT_NONE across the same span blocks reads as well. */
    runtime_memory_gpu_protect((uintptr_t)p1, 4 * blk, 0, 0);
    assert(!try_read_u32(u2, &val));
    assert(fault_count == 4);

    /* Restore RW protection via cached protect_fast() hit path. */
    assert(runtime_memory_is_mapped((uintptr_t)p1, 2 * blk) == 1);
    runtime_memory_gpu_protect((uintptr_t)p1, 4 * blk, 1, 1);
    assert(try_write_u32(u1, 0xaaaa0001u));
    assert(try_write_u32(u2, 0xaaaa0002u));
    assert(try_write_u32(u3, 0xaaaa0003u));
    assert(try_read_u32(u2, &val) && val == 0xaaaa0002u);

    uint64_t writes = 0, read_waits = 0;
    double wait_ms = 0, hold_ms = 0, worst_ms = 0, worst_hold_ms = 0, read_wait_ms = 0;
    char readers[256] = {0}, writers[256] = {0};
    runtime_memory_lock_stats(&writes, &wait_ms, &hold_ms, &worst_ms);
    runtime_memory_lock_stats2(&worst_hold_ms, &read_waits, &read_wait_ms);
    runtime_memory_lock_sites(readers, writers, sizeof(writers));
    assert(writes >= 6);
    assert(hold_ms >= 0.0 && worst_hold_ms >= 0.0);

    assert(unmap_fn(p1, blk) == 0);
    assert(unmap_fn(p2, blk) == 0);
    assert(unmap_fn(p3, blk) == 0);
    assert(rel_fn((uint64_t)phys1, blk) == 0);
    assert(rel_fn((uint64_t)phys2, blk) == 0);
    assert(rel_fn((uint64_t)phys3, blk) == 0);

    printf("test_protect_fast: PASS (writes=%llu, sites='%s')\n",
           (unsigned long long)writes, writers);
    return 0;
}
