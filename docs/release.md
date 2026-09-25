# Candidate qualification and publication

The application is built once as a single-platform `linux/amd64` OCI archive. Static checks, backend tests, API regression shards and browser journeys must succeed for the same source revision before the archive can be promoted. A registry push is a copy of the tested manifest, never another application build.

## Workflow graph

`.github/workflows/docker-image.yml` calls the reusable candidate, static, backend, API and browser workflows. Every checkout receives the caller's exact `github.sha`. The candidate job rejects a dirty checkout and compares its source fingerprint before and after building the application and race-tested Go executable.

The immutable `application-candidate` artifact contains:

- `application.oci.tar`: the one supported platform's image and all blobs.
- `candidate.json`: source revision, dirty flag, source fingerprint, archive checksum, OCI manifest digest, image config digest and Go executable checksum.
- `mc-admin-e2e`: the executable built and tested from that revision.

API and browser jobs validate the archive's blobs and checksums, load that archive into Docker, and address the application by its verified config digest. Each job then compares its actual run manifest and result with the candidate identity and requires owned cleanup to have finished. Browser evidence additionally requires a nonempty Playwright result with no failed, flaky or skipped journeys. API shard and selected-case completeness remain enforced by the runner's coverage audit; the number of observed HTTP routes is diagnostic, not an assertion-coverage threshold.

The qualification job runs even when a dependency fails. It accepts only the exact required set (`candidate`, `static`, `backend`, `api`, `browser`) with every result equal to `success`. Missing, failed, cancelled and skipped jobs cannot produce a qualification receipt. Both the backend collection audit and API coverage audit also explicitly require their execution matrices to succeed.

Only the promotion job has `packages: write`. It requires successful qualification and a semantic version tag. Tag pushes qualify and promote; manual dispatch defaults to qualification only, and its `publish` option is effective only for a semantic version tag ref. Promotion revalidates the candidate and receipt, copies with `skopeo copy --preserve-digests`, and reads back every destination's raw manifest to compare its digest. A registry that requires a manifest rewrite causes failure. Images and build cache are not pushed to GHCR during candidate construction.

The promotion CLI enforces the source boundary itself: formal promotion requires `--revision <full-40-character-SHA>` and a matching clean candidate. The workflow passes its exact `github.sha` to `promote`. Missing, malformed or mismatched revisions and dirty sources are rejected before any registry command. `--insecure-loopback` permits an uncommitted local fixture only for explicit loopback destinations; if a revision is supplied there, the same clean matching-source check still applies.

Release tags use `vMAJOR.MINOR.PATCH`, optionally followed by SemVer prerelease identifiers such as `-beta.1` or `-rc.0`. Numeric identifiers cannot have leading zeroes. Build metadata (`+...`) is excluded from release tags because Docker tags cannot preserve it, and the image version must fit Docker's 128-character tag limit. The workflow accepts both stable and prerelease tag pushes and validates the tag before publication.

The [official metadata-action v6 SemVer rules](https://github.com/docker/metadata-action/tree/v6#type-semver) preserve a prerelease as its complete version and do not automatically generate `latest`. The workflow explicitly disables major/minor aliases and `latest` for prereleases. `v6.0.0-beta.1` therefore publishes only `6.0.0-beta.1` and `sha-<first-seven-commit-characters>`; it cannot update `6.0.0`, `6.0`, `6` or `latest`. Stable `v6.0.0` retains all five tags: `6.0.0`, `6.0`, `6`, `latest` and the SHA tag. Immediately before promotion, `scripts/release/tags.py` checks that the action's complete destination list equals this policy; unexpected, duplicated or missing destinations fail before any registry copy.

## Digest terminology

The OCI manifest digest identifies the registry artifact. The config digest identifies the image configuration and is Docker's local image ID. They are different hashes. The archive checksum additionally identifies the transported tar file; the same OCI image could otherwise be repackaged into a different tar.

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

Run API, browser, workload and deployment checks against the returned `local_image_id`. Keep the OCI manifest digest and source fingerprint alongside those reports. This local dirty-source evidence cannot satisfy the CI `verify --revision <SHA>` requirement, which demands the matching clean checkout.

## Executable gate checks

`backend/tests/ci/test_release_gates.py` injects unsuccessful results for every required gate, checks source/artifact mismatches, and checks the workflow's dependency graph and absence of a publication rebuild. Its subprocess checks run the actual promotion CLI with synthetic archives and a recording external-command adapter: invalid source inputs never reach that adapter, while valid clean or explicitly local inputs do. `scripts/release/verify_local.py` additionally runs a disposable loopback registry, confirms rejected gates create no registry repository, loads a synthetic OCI image, and verifies that a successful copy retains the exact manifest digest. The registry is labeled with a random owner, bound to loopback, and removed only after its identity is checked; its data and temporary local image tag are also removed.

```bash
cd backend
uv run pytest tests/ci tests/testing/test_isolation.py
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
