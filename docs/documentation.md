# Documentation ownership and maintenance

Use this guide when writing, reorganizing or reviewing repository documentation.
The [documentation index](README.md) routes readers to current topics.

## Choose the owner

| Content | Detailed owner |
| --- | --- |
| Instructions that govern agent work | Root or component `AGENTS.md`, at the narrowest useful scope |
| Project introduction and first successful start | Root/component `README.md`; shared setup in [development](development.md) |
| Cross-component operation, CI or deployment | Root `docs/` |
| Component architecture, workflows and failure boundaries | The owning component's `docs/<topic>.md` |
| Observable behavior and acceptance requirements | `openspec/specs/<capability>/spec.md` |
| Proposed work, implementation checklist and historical evidence | `openspec/changes/`, with completed changes under `archive/` |
| Exact API, configuration and executable inventory | Owning source/schema, linked from explanatory docs |
| Deployed API scenario coverage | [E2E coverage index](../e2e/docs/coverage.md) and its domain pages |

Keep one detailed explanation per responsibility. A cross-component overview may
summarize it and link to the owner. Self-contained docs explain their own terms
and boundaries; they need not copy every dependency's implementation.

## Instruction files

AGENTS.md contains commands, development constraints, significant traps and
conditional reading routes. Component files inherit root policy and add their
specific execution requirements. Keep high-impact constraints visible: test
scope, delivery gates, generated-source protection and resource ownership.

Update AGENTS.md when those instructions or reading routes change. Function
signatures, hook/store shapes, schema revisions, individual test cases and
implementation counts belong to the owning topic or source, not automatically
to an instruction file. Do not append a feature summary after unrelated headings.

Use a task condition with each important link, such as “before changing task
cancellation, read background-tasks.md and operations.md”. A complete document
catalog belongs in `docs/README.md`; do not require every task to read it all.

Review size in bytes as well as lines. Repository working targets are 4–6 KiB
for root instructions and about 5–8 KiB per component, with room for justified
constraints. These are review prompts, not reasons to discard required rules.

## Topic documents

Start with the document's purpose, owned module/workflow and links to related
contracts. Organize explanation around responsibilities, normal execution,
invariants, failure/recovery behavior and relevant implementation/verification
entry points. Task guides give prerequisites and ordered commands; reference
pages collect details that readers look up rather than follow sequentially.

Use descriptive headings and short paragraphs. Split a document when it serves
independent tasks or audiences, such as migration operations versus schema
reference, or test authoring versus scheduling. Around 16 KiB is a useful review
point, not a hard limit. A cohesive contract can remain longer. Merge overlapping
sections into their owner instead of making several near-identical documents.

Describe current behavior. Keep historical compatibility only when it explains
a supported upgrade, interpretation or recovery constraint. Implementation
diaries, completed task lists and dated observations belong to change archives
or release evidence. Remove hand-maintained counts and exhaustive symbol lists
when source discovery supplies the answer more reliably.

## Change and review workflow

1. Identify the current topic, behavior specification and affected readers.
2. Reconcile the text with code, tests and workflows. Preserve failure and
   ownership boundaries when shortening; distinguish an overview from a contract.
3. Move unique content before deleting its old copy. Retain a topic when it has
   a distinct purpose; delete or merge only superseded or duplicate explanations.
4. Update links and the owning `docs/README.md` when adding, splitting or moving
   a topic. Root README links to the root index; component indexes own their catalogs.
5. Check relative links, heading anchors, command working directories, source
   paths, scenario references and the diff. Check new topics are reachable from
   the indexes. Follow the root delivery rules; documentation-only edits need no
   local application tests.

OpenSpec archives retain historical evidence. Current documentation must be
understandable without treating an archived plan as today's implementation.
When a current topic disagrees with a specification or code, investigate the
contract rather than silently changing documented product behavior.
