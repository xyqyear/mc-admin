set -u
runner=$1
run_directory=$2
config=$3
image=$4
status=0
if [ -f "$run_directory/manifest.json" ]; then
  "$runner" cleanup --run-dir "$run_directory" || status=1
fi
for manifest in "$run_directory"/cloud/*.json; do
  [ -f "$manifest" ] || continue
  "$runner" cleanup-dns --manifest "$manifest" --external-config "$config" --backend-image "$image" || status=1
done
exit "$status"
