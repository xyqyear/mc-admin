# Monaco Editor Integration

Monaco is the code editor for compose YAML, server config files, file-edit dialogs, and the template/server diff viewers. It runs as four web workers (editor, json, ts, css/html) plus a custom YAML worker, all wired in `main.tsx`. SNBT (Minecraft NBT serialized as text) is registered as a custom Monaco language so NBT data files open with proper tokenization.

## Worker setup

`main.tsx` calls `MonacoEnvironment.getWorker(_, label)` and returns the right worker URL per label. The custom YAML worker is `yaml.worker.js` (loaded via Vite's `?worker` import), which monaco-yaml uses for schema validation.

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

monaco-yaml is configured with two schemas:

- The Docker Compose JSON Schema for general syntax
- A docker-minecraft-server hint schema (`public/static/mc-server-compose-schema.json`) that adds completions for `itzg/minecraft-server` env vars (`VERSION`, `EULA`, `MEMORY`, `TYPE`, etc.)

Both are loaded as `fileMatch: ['*.yaml', '*.yml']`. The hints schema is project-specific; updating it is how new env vars become discoverable in the editor.

## SNBT language

`config/snbtLanguage.ts` exports two objects:

- `snbtLanguageDefinition` — Monarch tokenizer rules covering numbers, strings, identifiers, brackets, the `1L` / `1.0f` numeric suffixes
- `snbtLanguageConfiguration` — bracket pairs, comment rules, surrounding-pair config

Registered once in `main.tsx` via `monaco.languages.register({ id: 'snbt' })` + `setMonarchTokensProvider`. `utils/fileLanguageDetector.ts` returns `'snbt'` for `.dat` / `.snbt` extensions, which `FileEditModal` passes to Monaco.

## Diff viewer

The compose-diff use cases (template change preview, file conflict resolution, mode conversion) all use Monaco's diff editor (`MonacoDiffEditor` component). Two YAML strings → side-by-side diff with intra-line highlighting. The world-restore preview's "before vs after" is *not* a Monaco diff — that's an image-tile diff via Leaflet.

## Components

- `components/editors/ComposeYamlEditor.tsx` — the standard YAML editor (used in compose page, template editor)
- `components/editors/SimpleEditor.tsx` — generic editor for arbitrary file content
- `components/editors/MonacoDiffEditor.tsx` — diff viewer

## Files

- `src/main.tsx` — worker registration + SNBT language registration
- `src/yaml.worker.js` — custom YAML worker (monaco-yaml)
- `src/config/snbtLanguage.ts` — SNBT language definition
- `src/utils/fileLanguageDetector.ts` — extension → Monaco language id mapping
- `public/static/mc-server-compose-schema.json` — docker-minecraft-server compose hints
