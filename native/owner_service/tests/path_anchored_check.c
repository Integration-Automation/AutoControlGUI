#define _GNU_SOURCE
/* Unprivileged check of guardian_path_anchored: "/" and every directory above a path must be
 * real directories, root's, and writable by no one else, sticky or not. */
#include "../src/guardian.h"
#include <stdio.h>

static const struct { const char *path; bool anchored; } cases[] = {
    {"/usr/bin", true},           /* /usr: root's 0755. */
    {"/tmp/x", false},            /* /tmp: sticky, world-writable. */
    {"/proc/self/x", false},      /* /proc/self: a link. */
    {"relative", false},
    {"/", true},
};

int main(void) {
    int failures = 0;
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i)
        if (guardian_path_anchored(cases[i].path) != cases[i].anchored) {
            fprintf(stderr, "%s: expected %d\n", cases[i].path, cases[i].anchored);
            ++failures;
        }
    return failures ? 1 : 0;
}
