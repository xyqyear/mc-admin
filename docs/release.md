# Candidate qualification and publication

The application ships as a single-platform `linux/amd64` OCI archive. Complete qualification executes static/frontend checks, Go tests, backend tests, API regression and browser journeys with their existing exact-once coverage and cleanup audits. Publication copies a qualified manifest with `skopeo copy --preserve-digests`; it never rebuilds the application.

## Content identities and source provenance

`scripts/release/content.py` hashes sorted committed Git entries, including paths, modes and object identities. Verification identity includes application code, tests, fixtures, locks, Dockerfiles, workflows, release tooling and all unknown inputs. Only regular non-executable Markdown in designated documentation locations and the single release-data file are excluded. Markdown fixtures remain inputs. The policy version and its implementation participate in the identity.

Release identity combines verification identity with `frontend-react/public/static/release.json`. The file must be regular and non-executable. Python qualification and the UI validate its fields, unique complete SemVer versions and dates. A release tag must equal the greatest displayed version. Commit IDs remain provenance, not cache keys. The original full source fingerprint still rejects dirty or changing build sources.

`candidate.json` records target source, archive checksum, OCI manifest/config digests and Go executable checksum. Rebound/derived candidates retain `build_source`, the original application build source. Rebinding documentation-equivalent commits leaves OCI revision labels and image bytes unchanged. Target and build source remain separately visible in receipts and promotion evidence.

## Qualification routes

`.github/workflows/docker-image.yml` is the shared push, PR, manual and tag entry point. It computes identity, serializes equivalent calls to `qualification.yml`, and promotes only semantic version tags. Manual `publish=false` is qualification only; `force_full=true` bypasses history. See [CI validation](ci.md#validation) for delivery and waiting.

The resolver repeats lookup under the content lock:

- `full`: build one candidate and execute the exact set (`candidate`, `static`, `backend`, `api`, `browser`). Missing, failed, cancelled or skipped execution cannot issue a receipt. API qualification includes every current case except DNSPod, which requires explicit selection.
- `reuse`: verify a trusted receipt and candidate with the same release identity, retain the image digest and bind target source without claiming new test execution.
- `metadata`: reuse complete business qualification, derive a bounded data-only image, run version-data/notification tests and real-image browser smoke, and verify owned cleanup.

`application-qualification-<verification identity>` contains versioned `qualification.json`: current identity/producer/target candidate, original complete qualification with source/run/attempt/time and five gates, actual executed gates, and any inherited final-image metadata evidence. Restoration validates the artifact checksum, originating run/attempt/source, successful completion of this repository's coordinator, original run provenance and independently recomputed Git identities. PR/fork, other workflow, failed or incomplete sources cannot authorize reuse. Candidate metadata, archive checksum/blobs and runner bytes must match. Missing/expired evidence causes full validation; corrupt or inconsistent evidence fails closed.

Candidates, receipts and resolutions retain 30 days. Reuse never refreshes the original full qualification timestamp, including after metadata derivation. Legacy receipts are ineligible. This is historical evidence about tested content; external providers and hosted runners can change. Scheduled provider tests and forced qualification remain available.

## Metadata-only image verification

`release.json` uses the application's existing `/static/` mount. Comparison and rendering remain application code and participate in verification identity. The UI requests same-origin JSON without HTTP cache reuse and does not acknowledge unavailable or invalid data. See [version notifications](../frontend-react/docs/version-updates.md).

`scripts/release/metadata.py` appends one deterministic OCI layer containing only `/app/static/static/release.json`. Previous layers and bytes, runtime command/environment/configuration and runner remain unchanged. Config changes only append the rootfs diff ID and history entry; the manifest changes its config descriptor and adds that layer. No dependency installation, application compilation or registry candidate push occurs. Structural verification rejects other changes.

`release-metadata.yml` loads the final image and runs `browser/release.spec.ts` through the owned Go fixture. The browser compares actual served JSON with selected source and checks upgrade notification, version/notes and acknowledgment. Runtime identity and cleanup are verified before accepting smoke evidence. Later reuse preserves this evidence.

## Publication and immutable candidate checks

Only promotion has `packages: write`. It validates the current receipt/content/target revision, copies the final candidate to the exact destination tags and reads back each raw registry manifest to compare its digest. Manifest rewrites fail. Candidate construction never pushes images or build cache to GHCR.

Candidate inspection verifies one supported OCI manifest/config and every blob. Layers are hashed in bounded chunks with descriptor sizes checked; missing, nonregular, unsupported or truncated payloads fail before load/publication. The archive checksum is independent. API/browser audits retain actual candidate identity, successful exact-once outcomes and owned cleanup; cloud cleanup remains independently required.

Tags use `vMAJOR.MINOR.PATCH`, optionally with SemVer prerelease identifiers. Build metadata is excluded from image tags. Prereleases publish only their complete version and SHA tag; stable releases additionally publish major/minor aliases and `latest`. `scripts/release/tags.py` checks the entire destination set before registry writes. Promotion requires the full clean target revision; synthetic local validation is restricted to loopback destinations.

## Digest terminology

The OCI manifest digest identifies the registry artifact. The config digest identifies the image configuration and is Docker's local image ID with the classic image store. They are different hashes. The archive checksum additionally identifies the transported tar file; the same OCI image could otherwise be repackaged into a different tar.

API and browser qualification runners explicitly select the classic `overlay2`
image store before loading any candidate or creating owned environments. The
containerd image store uses a manifest/index digest for the local image ID;
its default on newer hosted runners does not satisfy this config-ID verification
contract. The runner setup checks the selected driver and retains the strict
loaded-config and runtime identity checks. This setting applies only to the
disposable CI runner, not application deployments.

Loading into Docker uses `skopeo copy` to a temporary Docker archive followed by the installed Docker CLI's `docker load`. Docker may require a different transport manifest format; the config digest must remain unchanged. Publication uses the original OCI archive, preserving the original OCI manifest. This avoids older Skopeo versions' `docker-daemon:` API incompatibility with newer Docker engines. Temporary transport archives are removed after loading.

## Local qualification of an uncommitted workspace

A local dirty workspace is not presented as its base commit. Freeze application and fixture changes, then copy a source snapshot outside the working tree. The recorded fingerprint hashes the copied paths, modes and contents. Subsequent documentation edits in the original workspace cannot alter the candidate source snapshot.

```bash
# Run from the repository root. Use new, owned output paths.
uv run --project backend python scripts/release/candidate.py source \
  --allow-dirty --snapshot /tmp/mc-admin-candidate-source \
  --output /tmp/mc-admin-candidate-source.json

# Build only from the copied source. Build its Go executable with go.mod's version.
docker build -t mc-admin:local-candidate /tmp/mc-admin-candidate-source
mkdir -p /tmp/mc-admin-candidate
make -C /tmp/mc-admin-candidate-source/e2e build
cp /tmp/mc-admin-candidate-source/e2e/bin/mc-admin-e2e /tmp/mc-admin-candidate/
docker save --output /tmp/mc-admin-candidate/application.docker.tar mc-admin:local-candidate
skopeo copy docker-archive:/tmp/mc-admin-candidate/application.docker.tar \
  oci-archive:/tmp/mc-admin-candidate/application.oci.tar
rm /tmp/mc-admin-candidate/application.docker.tar
uv run --project backend python scripts/release/candidate.py capture \
  --directory /tmp/mc-admin-candidate --source /tmp/mc-admin-candidate-source.json
uv run --project backend python scripts/release/candidate.py load \
  --directory /tmp/mc-admin-candidate --output /tmp/mc-admin-candidate-loaded.json
```

Run only change-related API, browser, workload or deployment checks against the returned `local_image_id`. Keep the OCI manifest digest and source fingerprint alongside those reports. Delivery requires a current-target GitHub Actions qualification receipt. This local dirty-source evidence cannot satisfy the CI `verify --revision <SHA>` requirement, which demands the matching clean checkout.

## Executable gate checks

`backend/tests/ci/test_release_gates.py` injects unsuccessful results for every required gate, checks source/artifact mismatches, and checks the workflow's dependency graph and absence of a publication rebuild. Its subprocess checks run the actual promotion CLI with synthetic archives and a recording external-command adapter: invalid source inputs never reach that adapter, while valid clean or explicitly local inputs do. `scripts/release/verify_local.py` additionally runs a disposable loopback registry, confirms rejected gates create no registry repository, loads a synthetic OCI image, and verifies that a successful copy retains the exact manifest digest. The registry is labeled with a random owner, bound to loopback, and removed only after its identity is checked; its data and temporary local image tag are also removed.

```bash
cd backend
uv run pytest tests/ci/test_release_gates.py
cd ..
uv run --project backend python -m scripts.release.verify_local \
  --output /tmp/mc-admin-local-promotion.json
```

This synthetic image checks the transfer and gate mechanism. It is not an application regression run or a production publication. Real GHCR credentials, a version tag and approved source selection remain separate from local validation. The workflow is statically validated with pinned actionlint; local execution does not claim that a remote GitHub Actions run has occurred.

After the actual candidate's static, backend, API and browser evidence is complete, the same loopback exercise can consume that candidate and its real qualification receipt:

```bash
uv run --project backend python -m scripts.release.verify_local \
  --candidate /tmp/mc-admin-candidate --receipt /tmp/qualified-local.json \
  --output /tmp/mc-admin-application-promotion.json
```

Both options are required together. The script verifies the candidate archive and receipt before creating a registry, reuses the receipt for the successful copy, records its checksum, and tests each necessary gate's failed/cancelled/skipped/missing variants without registry writes. It does not generate successful qualification for an unverified application.
