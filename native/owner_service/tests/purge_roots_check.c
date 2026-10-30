#define _GNU_SOURCE
/* Acceptance of the manifest's purge-root check. Unprivileged cases always run; as root it
 * also makes the cases only root can make: a link into a user's directory, a user's own
 * directory, and a link loop, each under /run. */
#include "../src/guardian.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static int failures;

/* The service's random source is not needed by these checks. */
bool service_random(void *buffer, size_t size) {
    (void)buffer;
    (void)size;
    return false;
}

static void expect(const char *path, bool valid) {
    const char *roots[] = {path};
    guardian_manifest manifest = {.purge_roots = roots, .purge_root_count = 1};
    if (guardian_purge_roots_valid(&manifest) != valid) {
        fprintf(stderr, "%s: expected %s\n", path, valid ? "valid" : "refused");
        ++failures;
    }
}

static void expect_listener(const char *listener, const char *purge_root, bool valid) {
    const char *roots[] = {purge_root};
    guardian_manifest manifest = {.listener_path = listener, .purge_roots = roots,
                                  .purge_root_count = purge_root ? 1 : 0};
    if (guardian_listener_outside_private_roots(&manifest) != valid) {
        fprintf(stderr, "listener %s: expected %s\n", listener, valid ? "valid" : "refused");
        ++failures;
    }
}

int main(void) {
    expect_listener("/run/je_auto_control/owner.sock", NULL, true);
    expect_listener("/tmpfoo/owner.sock", NULL, true);         /* Shares a prefix, not a root. */
    expect_listener("/tmp/owner.sock", NULL, false);           /* Under an epoch's own /tmp. */
    expect_listener("/run/lock/owner.sock", NULL, false);
    expect_listener("/usr/share/owner.sock", "/usr/share", false);  /* Under a manifest root. */
    expect_listener(NULL, NULL, false);
    expect("/usr/share", true);                          /* A root's directory under root's. */
    expect("/usr/share/autocontrol-absent-root", true);  /* Not there yet: fine. */
    expect("/tmp/app", false);                           /* /tmp: others may create the name. */
    expect("/etc/passwd", false);                        /* Not a directory. */
    expect("relative", false);
    expect("/proc/self/root", false);                    /* Through a link. */
    int root_cases = 0;
    if (geteuid() == 0) {
        unlink("/run/autocontrol-link-root"); /* Left by a run that crashed: started afresh. */
        unlink("/run/autocontrol-loop-root");
        rmdir("/run/autocontrol-user-root");
        rmdir("/run/autocontrol-good-root");
        char user_dir[] = "/tmp/autocontrol-roots-XXXXXX";
        bool made = mkdtemp(user_dir) != NULL;
        if (made && chown(user_dir, 65534, 65534) == 0) {
            /* Each is made, checked and removed before the next. */
            if (symlink(user_dir, "/run/autocontrol-link-root") == 0) {
                expect("/run/autocontrol-link-root", false);    /* Resolves into a user's directory. */
                unlink("/run/autocontrol-link-root");
                ++root_cases;
            }
            if (mkdir("/run/autocontrol-user-root", 0755) == 0 &&
                chown("/run/autocontrol-user-root", 65534, 65534) == 0) {
                expect("/run/autocontrol-user-root", false);    /* A user's own directory. */
                ++root_cases;
            }
            rmdir("/run/autocontrol-user-root");
            if (symlink("/run/autocontrol-loop-root", "/run/autocontrol-loop-root") == 0) {
                expect("/run/autocontrol-loop-root", false);    /* A link loop. */
                unlink("/run/autocontrol-loop-root");
                ++root_cases;
            }
            if (mkdir("/run/autocontrol-good-root", 0755) == 0) {
                expect("/run/autocontrol-good-root", true);     /* Root's, under root's. */
                ++root_cases;
            }
            rmdir("/run/autocontrol-good-root");
        }
        if (made) rmdir(user_dir);
    }
    printf("{\"failures\": %d, \"root_cases\": %d}\n", failures, root_cases);
    return failures ? 1 : 0;
}
