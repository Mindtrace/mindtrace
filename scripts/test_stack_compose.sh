# Shared Compose invocation for the integration test stack.
# Sourced by scripts/docker_up.sh and scripts/run_tests.sh.
# Requires DOCKER_COMPOSE_CMD to be set by the caller.

_TEST_STACK_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_TEST_STACK_REPO_ROOT="$(cd "$_TEST_STACK_SCRIPTS_DIR/.." && pwd)"

MINDTRACE_TEST_COMPOSE_FILE="$_TEST_STACK_REPO_ROOT/tests/docker-compose.yml"
MINDTRACE_MINIO_ENV="$_TEST_STACK_REPO_ROOT/mindtrace/core/mindtrace/core/testing/minio.env"

if [ ! -f "$MINDTRACE_MINIO_ENV" ]; then
    echo "error: missing MinIO env file: $MINDTRACE_MINIO_ENV" >&2
    return 1 2>/dev/null || exit 1
fi

mindtrace_test_compose() {
    $DOCKER_COMPOSE_CMD --env-file "$MINDTRACE_MINIO_ENV" -f "$MINDTRACE_TEST_COMPOSE_FILE" "$@"
}
