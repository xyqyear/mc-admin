## Qualification evidence

- Complete qualification: [41189275262](https://github.com/xyqyear/mc-admin/actions/runs/41189275262), source `15db6baf2cb93c942894e73655feed4ad6d0251f`, successful forced manual run with publication disabled. Candidate/Go, static/frontend, 13 backend shards, six API shards, three browser shards, all coverage/cleanup audits and final qualification passed. Wall time was 12 minutes 35 seconds.
- Metadata-only qualification: [41190235184](https://github.com/xyqyear/mc-admin/actions/runs/41190235184), diagnostic source `0231e86555b5557581da2bf71c5316fcb34c22cb`. Relative to the implementation source, only JSON whitespace differs. The verification identity is unchanged, the release identity changes, and only the metadata gate executes. The final-image notification checks, diagnostic artifact upload, owned cleanup and qualification passed in 3 minutes 21 seconds. This diagnostic branch is not part of the implementation branch.
- Exact reuse: [41187631113](https://github.com/xyqyear/mc-admin/actions/runs/41187631113) reused [41186599497](https://github.com/xyqyear/mc-admin/actions/runs/41186599497) on the initial implementation SHA `e23061664e6ef40047947fad5784adc22f9d642e`. It completed in 56 seconds, executed no test/build gates, and retained the original manifest digest and full-verification timestamp.

The final implementation verification identity is `13e0946dc26558599bf95445557ae55fd75f4f9873436e863bf2b56b8feae504`.
Its fully tested manifest is `sha256:13a4f070a8b4ea86caa809360e30d66224de3b5d0baa2f5290c1bb8a9ab908f8`.
The diagnostic metadata image is `sha256:f164fb58c2d2fcff38dfeed9bc0ab191fac57b2cb45396efb0c762b5c67e1a6f` and retains complete run `41189275262` and its original timestamp as provenance.

The first metadata diagnostic run rejected qualification when hidden-directory diagnostic uploads were excluded. The final workflow explicitly includes those artifacts; it does not suppress upload failures or weaken the gate.

## Local validation

Related release-gate, content-qualification and API-workflow Python tests passed, including real temporary Git histories, byte-level OCI derivation, artifact transport corruption, source recovery after shallow checkout, unavailable history, failed gates and metadata-to-documentation reuse.

Version precedence, release loading/notification and application session tests passed. Frontend lint, import boundaries, TypeScript, production bundling and generated contracts passed. Backend Ruff/Pyright and release-tool Pyright passed. Pinned actionlint, OpenSpec change/main specifications and version-entry skill validation passed. Complete application suites ran only in GitHub Actions.

All application qualification and diagnostic runs were non-publishing; no registry release tags were changed.
