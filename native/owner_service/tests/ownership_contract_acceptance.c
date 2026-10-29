#define _GNU_SOURCE
#include "native_owner.c"
#include <assert.h>
#include <fcntl.h>

static unsigned checks;
#define CHECK(expression) do { if (!(expression)) { fprintf(stderr, "failed line %d: %s\n", __LINE__, #expression); abort(); } ++checks; } while (0)

static no_validated_spec example_spec(void) {
    static const char *argv[] = {"/bin/true", "alpha"};
    static const char *env[] = {"LANG=C"};
    return (no_validated_spec){"/bin/true", "/", argv, env, 2, 1, 1000, 1000, NULL, 0};
}

static no_submit_result prepare_admission(no_runtime *runtime, authenticated_scope_slot *slot,
        unsigned request, no_validated_spec *input, owner_record **record, no_ticket *ticket, no_error *error) {
    *error = (no_error){0};
    scope_reference prepared = {0};
    CHECK(scope_retain((scope_reference){slot}, &prepared));
    immutable_spec_arena *spec = copy_spec(input, error);
    CHECK(spec != NULL);
    pthread_mutex_lock(&runtime->registry);
    no_submit_result result = admit_protected_locked(runtime, &prepared,
        (no_request_key){slot->identity.lease, {0, request}}, &spec, record, ticket, error);
    pthread_mutex_unlock(&runtime->registry);
    scope_release(&prepared); free(spec);
    return result;
}

static void discard_memory_fixture(no_runtime *runtime) {
    for (size_t i = 0; i < runtime->capacity; ++i) {
        CHECK(!runtime->records[i].thread_created);
        scope_release(&runtime->records[i].retained_scope);
        free(runtime->records[i].spec);
        pthread_mutex_destroy(&runtime->records[i].report_lock);
    }
    pthread_mutex_destroy(&runtime->registry);
    free(runtime->records); free(runtime);
}

static void without_thread(owner_record *record) {
    owner_fence_locked(record);
    record->start = THREAD_NO_THREAD;
    record->join = JOIN_ELIGIBLE;
    record->proof = (finished_proof){.kind = PROOF_WITHOUT_SCOPE, .no_child = true,
        .io_settled = true, .wait = {NO_WAIT_NOT_APPLICABLE, 0},
        .detail.without_scope = {NO_WORKER_CREATED}};
    record->report.start = (no_start_outcome){NO_START_FAILED_WITHOUT_CHILD, {NO_ERROR_THREAD_START, EAGAIN, 0}};
    atomic_store_explicit(&record->finished, true, memory_order_release);
}

static void admission_contract(void) {
    no_runtime *runtime = fixture_runtime(4);
    CHECK(runtime != NULL);
    authenticated_scope_slot root = {.identity = {.identity = {7, 1}, .epoch = runtime->epoch,
        .lease = {0, 1}, .parent_is_epoch = true}};
    atomic_init(&root.borrowers, 1); atomic_init(&root.issuance_closed, false);
    no_validated_spec spec = example_spec();
    owner_record *parent = NULL, *child = NULL, *sibling = NULL;
    no_ticket parent_ticket, child_ticket, sibling_ticket, duplicate;
    no_error error;
    CHECK(prepare_admission(runtime, &root, 1, &spec, &parent, &parent_ticket, &error) == NO_ACCEPTED);
    CHECK(atomic_load(&root.borrowers) == 2 && runtime->count == 1);
    CHECK(prepare_admission(runtime, &root, 1, &spec, &child, &duplicate, &error) == NO_EXISTING);
    CHECK(same_id(duplicate.record, parent_ticket.record) && atomic_load(&root.borrowers) == 2);
    spec.gid++;
    CHECK(prepare_admission(runtime, &root, 1, &spec, &child, &duplicate, &error) == NO_REJECTED);
    CHECK(error.kind == NO_ERROR_KEY_CONFLICT && runtime->count == 1);
    spec.gid--;
    authenticated_scope_slot nested = {.identity = {.identity = {7, 2}, .epoch = runtime->epoch,
        .lease = {0, 2}, .permitted_parent = parent_ticket, .parent_is_epoch = false}};
    atomic_init(&nested.borrowers, 1); atomic_init(&nested.issuance_closed, false);
    CHECK(prepare_admission(runtime, &nested, 2, &spec, &child, &child_ticket, &error) == NO_REJECTED);
    CHECK(error.kind == NO_ERROR_UNAVAILABLE && runtime->count == 1 && parent->unsettled_children == 0);
    parent->anchor = (child_anchor){ANCHOR_READY, 123};
    CHECK(prepare_admission(runtime, &nested, 2, &spec, &child, &child_ticket, &error) == NO_ACCEPTED);
    CHECK(parent->unsettled_children == UINT32_C(2) && child->start == THREAD_STARTING);
    CHECK(prepare_admission(runtime, &root, 3, &spec, &sibling, &sibling_ticket, &error) == NO_ACCEPTED);
    CHECK(no_revoke(runtime, parent_ticket));
    CHECK(atomic_load(&parent->revoked) && atomic_load(&child->revoked) && !atomic_load(&sibling->revoked));
    CHECK(!owner_invalidate_anchor_locked(parent));
    CHECK(prepare_admission(runtime, &nested, 2, &spec, &child, &duplicate, &error) == NO_EXISTING);
    CHECK(prepare_admission(runtime, &nested, 4, &spec, &child, &duplicate, &error) == NO_REJECTED);
    CHECK(error.kind == NO_ERROR_ADMISSION_CLOSED && parent->unsettled_children == UINT32_C(2));
    without_thread(child);
    no_runtime_maintain(runtime, (no_deadline){owner_now() + 10000000});
    CHECK(child->report.kind == NO_REPORT_SETTLED_WITHOUT_SCOPE && child->settled);
    CHECK(child->report.start.failure.system_errno == EAGAIN && child->join == JOIN_DONE);
    CHECK(parent->unsettled_children == 0 && atomic_load(&nested.borrowers) == 1);
    CHECK(owner_invalidate_anchor_locked(parent) && parent->anchor.borrowed_directory == -1);
    no_runtime_maintain(runtime, (no_deadline){owner_now() + 10000000});
    CHECK(atomic_load(&nested.borrowers) == 1 && atomic_load(&child->successful_joins) == 0);
    CHECK(prepare_admission(runtime, &nested, 2, &spec, &child, &duplicate, &error) == NO_EXISTING);
    CHECK(atomic_load(&nested.borrowers) == 1);
    CHECK(no_submit(runtime, &(no_authenticated_scope){{&root}}, (no_request_key){{0, 1}, {0, 9}},
        &spec, &duplicate, &error) == NO_REJECTED && error.kind == NO_ERROR_UNAVAILABLE);
    discard_memory_fixture(runtime);
    CHECK(atomic_load(&root.borrowers) == 1 && atomic_load(&nested.borrowers) == 1);
}

static void proof_contract(void) {
    no_runtime *runtime = fixture_runtime(1);
    owner_record *record = &runtime->records[0];
    record_init(record, runtime, (no_request_key){{0, 1}, {0, 1}}, "/bin/true", (fixture_options){0});
    runtime->count = 1; record->profile = PROFILE_PROTECTED;
    without_thread(record); record->join = JOIN_DONE;
    no_report report = record->report;
    CHECK(maintenance_build_final_report(record, &report));
    CHECK(report.kind == NO_REPORT_SETTLED_WITHOUT_SCOPE);
    record->proof.detail.without_scope.execution = (no_scope_execution)77;
    report = record->report;
    CHECK(!maintenance_build_final_report(record, &report));
    publish_joined(record);
    CHECK(record->report.kind == NO_REPORT_STICKY_UNKNOWN && !record->settled);
    CHECK(record->report.detail.unknown.first_error.kind == NO_ERROR_NATIVE_CONTRACT);
    record->proof.kind = PROOF_UNRESOLVED;
    publish_joined(record);
    CHECK(record->report.kind == NO_REPORT_STICKY_UNKNOWN && !record->settled);
    record->proof.kind = PROOF_CONTAINED;
    record->proof.no_child = false; record->proof.child_dead = true;
    record->proof.wait.kind = NO_WAIT_STATUS_UNAVAILABLE;
    record->start = THREAD_STARTED; record->thread_created = true;
    record->report.start.kind = NO_START_CHILD_CREATED;
    record->scope.container.state = DIR_REMOVED; record->scope.payload.state = DIR_REMOVED;
    record->proof.detail.contained = (contained_evidence){.container = CLEAN_EXACT_REMOVAL,
        .payload = CLEAN_EXACT_REMOVAL, .emptiness = EMPTY_POPULATION_OBSERVED,
        .admission_fenced = true, .children_settled = true, .launch_resolved = true, .descriptors_clean = true};
    report = record->report;
    CHECK(maintenance_build_final_report(record, &report));
    record->proof.no_child = true;
    CHECK(!maintenance_build_final_report(record, &report));
    record->proof.no_child = false;
    record->proof.wait.kind = NO_WAIT_PENDING;
    CHECK(!maintenance_build_final_report(record, &report));
    record->proof.wait.kind = NO_WAIT_NOT_APPLICABLE;
    CHECK(!maintenance_build_final_report(record, &report));
    record->proof.wait.kind = NO_WAIT_EXITED;
    report.start.kind = NO_START_NOT_RESOLVED;
    CHECK(!maintenance_build_final_report(record, &report));
    report.start.kind = NO_START_CHILD_CREATED;
    record->proof.detail.contained.emptiness = EMPTY_EXACT_REMOVAL_WITH_FENCED_NO_ENTRY;
    CHECK(!maintenance_build_final_report(record, &report));
    record->proof.detail.contained.emptiness = EMPTY_POPULATION_OBSERVED;
    record->profile = PROFILE_DIRECT_FIXTURE;
    CHECK(!maintenance_build_final_report(record, &report));
    record->profile = PROFILE_PROTECTED; record->start = THREAD_STARTING;
    CHECK(!maintenance_build_final_report(record, &report));
    record->thread_created = false;
    discard_memory_fixture(runtime);
}

static void immutable_and_reference_contract(void) {
    no_error error = {0};
    char argument[] = "alpha";
    const char *argv[] = {"/bin/true", argument};
    no_validated_spec spec = example_spec(); spec.argv = argv;
    immutable_spec_arena *copy = copy_spec(&spec, &error);
    CHECK(copy && strcmp(copy->argv[1], "alpha") == 0);
    argument[0] = 'z';
    CHECK(strcmp(copy->argv[1], "alpha") == 0);
    immutable_spec_arena *changed = copy_spec(&spec, &error);
    CHECK(changed && !same_spec(copy, changed));
    free(copy); free(changed);
    uint32_t bit;
    CHECK(owner_child_bit(31, &bit) && bit == UINT32_C(0x80000000));
    CHECK(!owner_child_bit(32, &bit));
    scope_owner owner = {.count = 1};
    authenticated_scope_slot *slot = &owner.slots[0];
    atomic_init(&slot->borrowers, 1); atomic_init(&slot->issuance_closed, false);
    scope_reference reference = {slot}, retained = {0};
    CHECK(scope_retain(reference, &retained));
    atomic_store(&slot->issuance_closed, true);
    scope_release(&reference); authentication_owner_scan(&owner);
    CHECK(!slot->resources_settled && atomic_load(&slot->borrowers) == 1);
    scope_release(&retained); authentication_owner_scan(&owner);
    CHECK(slot->resources_settled && atomic_load(&slot->borrowers) == 0 && !retained.slot);
    CHECK(!scope_retain((scope_reference){slot}, &retained));
}

static void malformed_child_retention_contract(void) {
    no_runtime *runtime = fixture_runtime(2);
    authenticated_scope_slot root = {.identity = {.identity = {8, 1}, .epoch = runtime->epoch,
        .lease = {0, 1}, .parent_is_epoch = true}};
    atomic_init(&root.borrowers, 1); atomic_init(&root.issuance_closed, false);
    no_validated_spec spec = example_spec();
    owner_record *parent = NULL, *child = NULL;
    no_ticket parent_ticket, child_ticket;
    no_error error;
    CHECK(prepare_admission(runtime, &root, 1, &spec, &parent, &parent_ticket, &error) == NO_ACCEPTED);
    parent->anchor = (child_anchor){ANCHOR_READY, 123};
    authenticated_scope_slot nested = {.identity = {.identity = {8, 2}, .epoch = runtime->epoch,
        .lease = {0, 2}, .permitted_parent = parent_ticket}};
    atomic_init(&nested.borrowers, 1); atomic_init(&nested.issuance_closed, false);
    CHECK(prepare_admission(runtime, &nested, 2, &spec, &child, &child_ticket, &error) == NO_ACCEPTED);
    without_thread(child);
    child->proof.detail.without_scope.execution = (no_scope_execution)77;
    no_runtime_maintain(runtime, (no_deadline){owner_now() + 10000000});
    CHECK(child->report.kind == NO_REPORT_STICKY_UNKNOWN && !child->settled);
    CHECK(parent->unsettled_children == UINT32_C(2) && atomic_load(&nested.borrowers) == 2);
    CHECK(child->retained_scope.slot == &nested && runtime->count == 2);
    CHECK(no_revoke(runtime, parent_ticket) && !owner_invalidate_anchor_locked(parent));
    no_runtime_maintain(runtime, (no_deadline){owner_now() + 10000000});
    CHECK(parent->unsettled_children == UINT32_C(2) && atomic_load(&nested.borrowers) == 2);
    discard_memory_fixture(runtime);
}

static void scope_owner_descriptor_contract(void) {
    scope_owner owner = {.count = 1};
    authenticated_scope_slot *slot = &owner.slots[0];
    int pair[2];
    CHECK(pipe2(pair, O_CLOEXEC) == 0);
    slot->peer = (owned_fd){FD_OWNED, pair[0]};
    slot->epoch_anchor = (owned_fd){FD_OWNED, pair[1]};
    atomic_init(&slot->borrowers, 1); atomic_init(&slot->issuance_closed, true);
    scope_reference reference = {slot};
    authentication_owner_scan(&owner);
    CHECK(fcntl(pair[0], F_GETFD) >= 0 && fcntl(pair[1], F_GETFD) >= 0);
    CHECK(!slot->resources_settled);
    scope_release(&reference);
    CHECK(fcntl(pair[0], F_GETFD) >= 0 && fcntl(pair[1], F_GETFD) >= 0);
    authentication_owner_scan(&owner);
    CHECK(slot->peer.state == FD_CLOSED && slot->epoch_anchor.state == FD_CLOSED && slot->resources_settled);
    CHECK(fcntl(pair[0], F_GETFD) == -1 && errno == EBADF);
    int replacement = open("/dev/null", O_RDONLY | O_CLOEXEC);
    CHECK(replacement >= 0);
    if (replacement != pair[0]) {
        CHECK(dup2(replacement, pair[0]) == pair[0]);
        CHECK(close(replacement) == 0);
    }
    authentication_owner_scan(&owner);
    CHECK(fcntl(pair[0], F_GETFD) >= 0);
    CHECK(close(pair[0]) == 0);
}

bool owner_io_contract_cases(void);

int main(void) {
    CHECK(owner_io_contract_cases());
    admission_contract(); proof_contract(); immutable_and_reference_contract();
    malformed_child_retention_contract(); scope_owner_descriptor_contract();
    printf("{\"suite\":\"memory_and_scope_owner_contracts\",\"checks\":%u,\"result\":\"pass\",\"protected_profile_executed\":false,\"authority_verified\":false}\n", checks);
    return 0;
}
