# Monaco Editor Integration

Monaco is the code editor for compose YAML, server config files, file-edit dialogs, and the template/server diff viewers. It runs as four web workers (editor, json, ts, css/html) plus a custom YAML worker, all wired in `main.tsx`. SNBT (Minecraft NBT serialized as text) is registered as a custom Monaco language so NBT data files open with proper tokenization.

`MonacoDiffEditor` displays the supplied original/modified labels above its two panes and never logs source text. Configuration conflict comparison uses two explicitly sized diffs for baseline versus remote and remote versus draft, so both comparisons remain readable without overlapping.

## Worker setup

`main.tsx` calls `MonacoEnvironment.getWorker(_, label)` and returns the right worker URL per label. The custom YAML worker is `yaml.worker.js` (loaded via Vite's `?worker` import), which monaco-yaml uses for schema validation.

`ComposeYamlEditor` passes a scoped Monaco facade to monaco-yaml. Its `editor.createWebWorker` delegates to Monaco's top-level `createWebWorker`, which forwards the YAML label and initialization data to the registered worker. The application Monaco module and other language workers retain their original APIs. This adapter is required by the current monaco-worker-manager release; remove it after upgrading to an upstream release that resolves [worker compatibility issue #3](https://github.com/remcohaszing/monaco-worker-manager/issues/3) and verifying the real YAML worker's diagnostics and completions.

```ts
self.MonacoEnvironment = {
  getWorker(_, label) {
    if (label === 'yaml') return new Worker(new URL('./yaml.worker.js', ...));
    if (label === 'json') return new JsonWorker();
    if (['typescript', 'javascript'].includes(label)) return new TsWorker();
    if (['css', 'scss', 'less'].includes(label)) return new CssWorker();
    if (['html', 'handlebars', 'razor'].includes(label)) return new HtmlWorker();
    return new EditorWorker();
  }
};
```

## Compose schema validation

`ComposeYamlEditor` configures monaco-yaml to load `/static/mc-server-compose-schema.json`. This self-contained schema validates the Minecraft Compose structure and adds completions for `itzg/minecraft-server` environment variables (`VERSION`, `EULA`, `MEMORY`, `TYPE`, etc.). Its internal references do not load a separate Compose schema. The configured file matches include Compose filenames and YAML extensions. Updating this schema makes new environment variables discoverable in the editor.

## SNBT language

`shared/editors/snbtLanguage.ts` exports two objects:

- `snbtLanguageDefinition` — Monarch tokenizer rules covering numbers, strings, identifiers, brackets, the `1L` / `1.0f` numeric suffixes
- `snbtLanguageConfiguration` — bracket pairs, comment rules, surrounding-pair config

Registered once in `main.tsx` via `monaco.languages.register({ id: 'snbt' })` + `setMonarchTokensProvider`. `features/files/editingConfig.ts` selects `snbt` for `.snbt` files. `useFileEditor` passes that language and its options to `FileEditDialog`.

## Diff viewer

The compose-diff use cases (template change preview, file conflict resolution, mode conversion) all use Monaco's diff editor (`MonacoDiffEditor` component). Two YAML strings → side-by-side diff with intra-line highlighting. The world-restore preview's "before vs after" is *not* a Monaco diff — that's an image-tile diff via Leaflet.

## Components

- `shared/editors/ComposeYamlEditor.tsx` — the standard YAML editor (used in compose page, template editor)
- `shared/editors/SimpleEditor.tsx` — generic editor for arbitrary file content
- `shared/editors/MonacoDiffEditor.tsx` — diff viewer

## Files

- `src/main.tsx` — worker registration + SNBT language registration
- `src/yaml.worker.js` — custom YAML worker (monaco-yaml)
- `src/shared/editors/snbtLanguage.ts` — SNBT language definition
- `src/features/files/editingConfig.ts` — extension → Monaco language id mapping
- `public/static/mc-server-compose-schema.json` — docker-minecraft-server compose hints
