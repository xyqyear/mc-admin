set -euo pipefail
umask 077
mode=${1:-run}
runner=./e2e-artifacts/mc-admin-e2e
run_directory="$E2E_DIRECTORY/$E2E_RUN_ID"
config_file=$(mktemp "$RUNNER_TEMP/api-external.XXXXXX")
make_config() {
  case "$E2E_CAPABILITY" in
    huawei) uv run --no-project python scripts/ci/dns_config.py "$config_file" ;;
    dnspod) printf '%s' "$E2E_EXTERNAL_CONFIG" > "$config_file" ;;
  esac
}
recover_owned() {
  recovery_started=$(date +%s%N)
  recovery_status=0
  bash scripts/ci/recover_dns.sh "$runner" "$run_directory" "$config_file" "$E2E_IMAGE" || recovery_status=1
  if [ -d "$run_directory" ]; then
    uv run --no-project python - "$run_directory/recovery.json" "$recovery_started" <<'PY' || recovery_status=1
import json, sys, time
from pathlib import Path
path = Path(sys.argv[1])
previous = json.loads(path.read_text())["seconds"] if path.exists() else 0
path.write_text(json.dumps({"seconds": previous + (time.time_ns() - int(sys.argv[2])) / 1_000_000_000}) + "\n")
PY
  fi
  return "$recovery_status"
}
if [ "$mode" = recover ]; then
  trap 'rm -f "$config_file"' EXIT
  status=0
  make_config || status=1
  recover_owned || status=1
  exit "$status"
fi
recover() {
  status=$?
  trap - EXIT
  set +e
  recover_owned || status=1
  rm -f "$config_file"
  exit "$status"
}
trap recover EXIT
make_config
external_args=()
if [ "$E2E_CAPABILITY" != ordinary ]; then external_args+=(--external-config "$config_file"); fi
"$runner" run --backend-image "$E2E_IMAGE" --output "$E2E_DIRECTORY" --run-id "$E2E_RUN_ID" \
  --execution-plan api-planning/plan.json --profile "$E2E_PROFILE" --revision "$SOURCE_SHA" \
  --shard "$E2E_SHARD" --workers 2 --mc-slots 1 "${external_args[@]}"
