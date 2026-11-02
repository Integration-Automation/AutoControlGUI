/* Unprivileged check: the purge's SipHash-2-4 gives the reference digests (key bytes
 * 00..0f, message bytes 00, 01, ...; the first eight from the reference implementation's
 * vector table, lengths 0 to 7, and 8, 15 and 63). */
#include "../src/guardian_purge_linux.c"

static const struct { size_t length; uint64_t digest; } vectors[] = {
    {0, 0x726fdb47dd0e0e31ULL}, {1, 0x74f839c593dc67fdULL}, {2, 0x0d6c8009d9a94f5aULL},
    {3, 0x85676696d7fb7e2dULL}, {4, 0xcf2794e0277187b7ULL}, {5, 0x18765564cd99a68dULL},
    {6, 0xcbc9466e58fee3ceULL}, {7, 0xab0200f58b01d137ULL}, {8, 0x93f5f5799a932462ULL},
    {15, 0xa129ca6149be45e5ULL}, {63, 0x958a324ceb064572ULL},
};

int main(void) {
    unsigned char message[64];
    for (size_t i = 0; i < sizeof(message); ++i) message[i] = (unsigned char)i;
    int failures = 0;
    for (size_t i = 0; i < sizeof(vectors) / sizeof(vectors[0]); ++i) {
        uint64_t digest = siphash(0x0706050403020100ULL, 0x0f0e0d0c0b0a0908ULL, message, vectors[i].length);
        if (digest != vectors[i].digest) {
            fprintf(stderr, "length %zu: %016llx\n", vectors[i].length, (unsigned long long)digest);
            ++failures;
        }
    }
    return failures ? 1 : 0;
}
