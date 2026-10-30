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

#define EXECUTABLE "/usr/libexec/je_auto_control/owner_service"

static void expect_hidden(const char *listener, const char *executable, const char *purge_root, bool valid) {
    const char *roots[] = {purge_root};
    guardian_manifest manifest = {.listener_path = listener, .service_executable = executable,
                                  .purge_roots = roots, .purge_root_count = purge_root ? 1 : 0};
    if (guardian_private_roots_hide_nothing(&manifest, true) != valid) {
        fprintf(stderr, "listener %s, executable %s, root %s: expected %s\n", listener ? listener : "-",
                executable ? executable : "-", purge_root ? purge_root : "-", valid ? "valid" : "refused");
        ++failures;
    }
}

/* A policy's executable and working directory, under the default roots only. */
static void expect_policy(const char *executable, const char *cwd, bool valid) {
    service_launch_policy policy = {.executable = executable, .cwd = cwd};
    service_policy service = {.policies = &policy, .policy_count = 1};
    guardian_manifest manifest = {.listener_path = "/run/je_auto_control/owner.sock",
                                  .service_executable = EXECUTABLE, .service = &service};
    bool policies = guardian_private_roots_hide_nothing(&manifest, true);
    bool start = guardian_private_roots_hide_nothing(&manifest, false);  /* Each epoch start: not policies. */
    if (policies != valid || !start) {
        fprintf(stderr, "policy %s in %s: expected %s\n", executable ? executable : "-", cwd ? cwd : "-",
                valid ? "valid" : "refused");
        ++failures;
    }
}

/* A policy's working directory against one manifest purge root as well as the defaults. */
static void expect_cwd_under(const char *cwd, const char *purge_root, bool valid) {
    const char *roots[] = {purge_root};
    service_launch_policy policy = {.executable = "/usr/bin/python3", .cwd = cwd};
    service_policy service = {.policies = &policy, .policy_count = 1};
    guardian_manifest manifest = {.listener_path = "/run/je_auto_control/owner.sock",
                                  .service_executable = EXECUTABLE, .service = &service,
                                  .purge_roots = roots, .purge_root_count = 1};
    if (guardian_private_roots_hide_nothing(&manifest, true) != valid) {
        fprintf(stderr, "cwd %s, root %s: expected %s\n", cwd, purge_root, valid ? "valid" : "refused");
        ++failures;
    }
}

/* A policy whose fixed arguments or environment name paths. */
static void expect_named_in(const char *cwd, const char *argument, const char *environment, bool valid) {
    const char *argv[] = {"/usr/bin/python3", "-I", argument};
    const char *env[] = {environment};
    service_launch_policy policy = {.executable = "/usr/bin/python3", .cwd = cwd, .fixed_argv = argv,
                                    .fixed_argc = 3, .env = env, .envc = environment ? 1 : 0};
    service_policy service = {.policies = &policy, .policy_count = 1};
    guardian_manifest manifest = {.listener_path = "/run/je_auto_control/owner.sock",
                                  .service_executable = EXECUTABLE, .service = &service};
    if (guardian_private_roots_hide_nothing(&manifest, true) != valid) {
        fprintf(stderr, "in %s, argument %s, environment %s: expected %s\n", cwd, argument,
                environment ? environment : "-", valid ? "valid" : "refused");
        ++failures;
    }
}

static void expect_named(const char *argument, const char *environment, bool valid) {
    expect_named_in("/", argument, environment, valid);
}

/* The epoch's tmpfs takes noexec, nosymfollow and read-only from the host's mount, never more. */
static void expect_flags(unsigned long host, unsigned long wanted) {
    if (guardian_private_mount_flags(host) != (MS_NOSUID | MS_NODEV | wanted)) {
        fprintf(stderr, "mount flags for host %#lx: got %#lx\n", host, guardian_private_mount_flags(host));
        ++failures;
    }
}

static void expect_listener(const char *listener, const char *purge_root, bool valid) {
    expect_hidden(listener, EXECUTABLE, purge_root, valid);
}

int main(void) {
    expect_listener("/run/je_auto_control/owner.sock", NULL, true);
    expect_listener("/tmpfoo/owner.sock", NULL, true);         /* Shares a prefix, not a root. */
    expect_listener("/tmp/owner.sock", NULL, false);           /* Under an epoch's own /tmp. */
    expect_listener("/run/lock/owner.sock", NULL, false);
    expect_listener("/usr/share/owner.sock", "/usr/share", false);  /* Under a manifest root. */
    expect_listener(NULL, NULL, false);
    expect_listener("/usr/share/owner.sock", "/usr/share/", false);    /* A root written with a slash. */
    /* Not there, so not resolved: only dropping the trailing slash finds it. */
    expect_listener("/usr/share/autocontrol-absent/owner.sock", "/usr/share/autocontrol-absent/", false);
    expect_listener("relative/owner.sock", NULL, false);
    expect_policy("/usr/bin/python3", "/", true);
    expect_policy("/usr/bin/python3", "/tmp", true);           /* A root itself: the epoch's empty tmpfs. */
    expect_policy("/usr/bin/python3", "/tmp/", true);          /* The same, written with a slash. */
    expect_policy("/usr/bin/../bin/python3", "/./tmp", true);  /* "." and ".." resolve as the kernel does. */
    expect_policy("/usr/bin/python3", "/usr/../tmp/work", false);   /* Only resolving ".." finds /tmp. */
    expect_policy("/usr/bin/python3", "/usr/autocontrol-absent/../../tmp/work", false);  /* ".." past a gap. */
    /* A root not made yet, and a directory below it spelled with "." or "//": only tidying finds it. */
    expect_cwd_under("/usr/share/autocontrol-absent/./cache/w", "/usr/share/autocontrol-absent/cache", false);
    expect_cwd_under("/usr/share/autocontrol-absent/sub//cache/w", "/usr/share/autocontrol-absent/sub/cache", false);
    expect_cwd_under("/usr/share/autocontrol-absent/cache/w", "/usr/share/./autocontrol-absent//cache", false);
    expect_cwd_under("/usr/share/autocontrol-absent/other", "/usr/share/autocontrol-absent/cache", true);
    expect_cwd_under("/usr/share/autocontrol-absent/other", "/usr/share/autocontrol-absent/../x", false);
    /* A root validation accepts (anchored, not made yet) spelled with "//": only tidying finds it. */
    expect("/usr//share/autocontrol-absent", true);
    expect_cwd_under("/usr/share/autocontrol-absent/w", "/usr//share/autocontrol-absent", false);
    expect_named("/opt/app/main.py", NULL, true);
    expect_named("-m", "PATH=/usr/bin:/bin", true);
    expect_named("/var/tmp/app/main.py", NULL, false);                  /* A script in a root. */
    expect_named("--cache=/tmp/cache", NULL, false);                    /* After '='. */
    expect_named("-m", "PYTHONPATH=/opt/lib:/tmp/lib", false);          /* One part of a list. */
    expect_named("/tmp", "TMPDIR=/tmp", true);                          /* A root itself: the epoch's own. */
    expect_named("tmp/app/main.py", NULL, false);                       /* Relative to "/": /tmp/app. */
    expect_named("-m", "PYTHONPATH=var/tmp/lib", false);
    expect_named("-m", "PATH=:/usr/bin:", true);                        /* Empty parts: "/", not a root. */
    expect_named("-m", "EMPTY=", true);
    expect_named("-m", "NOEQUALS", true);
    expect_named_in("/tmp", "-m", "PATH=/usr/bin:", false);             /* "Here" is a root: shared. */
    expect_named_in("/tmp", "-m", "PATH=.:/usr/bin", false);
    expect_named_in("/tmp", "-m", "PATH=/usr/bin:/bin", true);
    expect_named_in("/tmp", "sub/main.py", NULL, false);                /* Joined: /tmp/sub/main.py. */
    expect_named_in("/tmp", "-m", NULL, true);                          /* A bare word is not judged. */
    /* Search lists (names ending in PATH or LIB): a root itself is shared, so refused there. */
    expect_named("-m", "PATH=/tmp:/usr/bin", false);
    expect_named("-m", "PYTHONPATH=lib", true);                          /* /lib, from "/". */
    expect_named_in("/tmp", "-m", "PYTHONPATH=lib", false);              /* /tmp/lib. */
    expect_named_in("/tmp", "-m", "PATH=:/usr/bin", false);              /* A leading empty part. */
    /* Other variables: an empty or "." part means nothing; a root itself is the epoch's own. */
    expect_named_in("/tmp", "-m", "LANG=", true);
    expect_named_in("/tmp", "-m", "DISPLAY=:0", true);
    expect_named("-m", "PATH=/usr/bin", true);                           /* The value alone is judged. */
    /* Program text is not a path, whatever slashes it holds. */
    expect_named("import os; os.path.join(here, '/../lib')", NULL, true);
    expect_named("print(open('x' * 300 + '/y').read())", NULL, true);
    expect_policy("/usr/bin/python3", "/tmp/work", false);     /* Below a root: hidden. */
    expect_policy("/tmp/helper", "/", false);
    expect_policy("relative/helper", "/", false);
    expect_policy("/usr/bin/python3", NULL, false);
    expect_flags(0, 0);
    expect_flags(ST_NOEXEC, MS_NOEXEC);
    expect_flags(ST_RDONLY | ST_NOSYMFOLLOW, MS_RDONLY | MS_NOSYMFOLLOW);
    expect_flags(ST_NOSUID | ST_NODEV, 0);
    expect_listener("/run/je_auto_control/owner.sock", "/", false);    /* "/" covers everything. */
    expect_hidden("/run/je_auto_control/owner.sock", EXECUTABLE, "/usr/libexec", false);  /* Hides the service. */
    expect_hidden("/run/je_auto_control/owner.sock", NULL, NULL, false);
    expect("/usr/share", true);                          /* A root's directory under root's. */
    expect("/usr/share/autocontrol-absent-root", true);  /* Not there yet: fine. */
    expect("/tmp/app", false);                           /* /tmp: others may create the name. */
    expect("/etc/passwd", false);                        /* Not a directory. */
    expect("relative", false);
    expect("/proc/self/root", false);                    /* Through a link. */
    int root_cases = 0;
    if (geteuid() == 0) {
        unlink("/run/autocontrol-link-root"); /* Left by a run that crashed: started afresh. */
        unlink("/run/autocontrol-hide-link");
        unlink("/run/autocontrol-lock-link");
        unlink("/run/autocontrol-dangling-link");
        unlink("/run/autocontrol-chain");
        unlink("/run/autocontrol-exe-link");
        unlink("/run/autocontrol-exe-dir/helper");
        rmdir("/run/autocontrol-exe-dir");
        /* A root that is a link: only its resolved form covers the executable's directory. */
        if (symlink("/usr/libexec", "/run/autocontrol-hide-link") == 0) {
            expect_hidden("/run/je_auto_control/owner.sock", EXECUTABLE, "/run/autocontrol-hide-link", false);
            unlink("/run/autocontrol-hide-link");
            ++root_cases;
        }
        /* A working directory not made yet, one or two levels below a link to a root (as
         * /var/lock is to /run/lock on many hosts): only a resolved prefix shows it lies below
         * the root. And a link to a place in the root not made yet: there but not resolving. */
        char lock[4096];
        bool lock_root = realpath("/run/lock", lock) != NULL;
        if (lock_root && symlink("/run/lock", "/run/autocontrol-lock-link") == 0) {
            expect_policy("/usr/bin/python3", "/run/autocontrol-lock-link/autocontrol-absent-leaf", false);
            expect_policy("/usr/bin/python3", "/run/autocontrol-lock-link/autocontrol-absent-leaf/work", false);
            ++root_cases;
        }
        unlink("/run/autocontrol-lock-link");
        if (lock_root && symlink("/run/lock/autocontrol-absent-leaf", "/run/autocontrol-dangling-link") == 0) {
            expect_policy("/usr/bin/python3", "/run/autocontrol-dangling-link", false);
            ++root_cases;
        }
        unlink("/run/autocontrol-dangling-link");
        /* A chain through a root and back out: it ends in /usr, but it passes through /run/lock,
         * which each epoch covers with its own tmpfs, so the epoch would not reach /usr. */
        char hop[64];  /* /run/lock is anyone's: a name of this run's own, never another user's. */
        snprintf(hop, sizeof(hop), "/run/lock/autocontrol-hop-%ld", (long)getpid());
        bool hop_made = lock_root && symlink("/usr", hop) == 0;  /* Only what this run made is removed. */
        if (hop_made && symlink(hop, "/run/autocontrol-chain") == 0) {
            expect_policy("/usr/bin/python3", "/run/autocontrol-chain", false);
            expect_policy("/run/autocontrol-chain/bin/sh", "/", false);
            ++root_cases;
        }
        unlink("/run/autocontrol-chain");
        if (hop_made) unlink(hop);
        /* An executable that is a link into a root: followed, it is hidden. The target is made
         * here, so the case does not depend on how the host packages its tools. */
        FILE *helper = mkdir("/run/autocontrol-exe-dir", 0755) == 0 ? fopen("/run/autocontrol-exe-dir/helper", "w")
                                                                    : NULL;
        if (helper && fclose(helper) == 0 &&
            symlink("/run/autocontrol-exe-dir/helper", "/run/autocontrol-exe-link") == 0) {
            expect_hidden("/run/je_auto_control/owner.sock", "/run/autocontrol-exe-link", "/run/autocontrol-exe-dir",
                          false);
            expect_hidden("/run/je_auto_control/owner.sock", "/run/autocontrol-exe-link", "/usr/share", true);
            ++root_cases;
        }
        unlink("/run/autocontrol-exe-link");
        unlink("/run/autocontrol-exe-dir/helper");
        rmdir("/run/autocontrol-exe-dir");
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
