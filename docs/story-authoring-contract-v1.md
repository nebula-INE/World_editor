# Axral Story Authoring Contract v1

> Phase A design contract for Web and Desktop. This document defines the first portable story-data boundary; it does not implement editor behavior.

## 1. Compatibility boundary

- The existing `.axral.json` world-project format (`format: axral-world-project`, `schema_version: 1`) remains unchanged.
- Story authoring data is stored in a separate `*.axral-story.json` file. It must not be silently inserted into, or written over, an existing world-project file.
- Existing world-project save, load, recovery, and export code paths are out of scope for this phase. No refactor of those paths is permitted as a prerequisite for story authoring.
- If a future feature needs a combined container, that requires a separately reviewed migration proposal and compatibility tests before implementation.

## 2. Format identity

A v1 story document uses:

- `format: "axral-story"`
- `schema_version: 1`
- `work_id`: stable string identifier for the work
- `title`: user-visible work title
- `kind`: format-neutral work kind (initial values: `novel`, `screenplay`, `audio_drama`, `game_scenario`, `trpg_scenario`, `storyboard`)
- `chapters`: ordered chapter/act containers

Each chapter has a stable `id`, `title`, integer `order`, and ordered `scenes`. Each scene has a stable `id`, `title`, integer `order`, and ordered `blocks`. Each block has a stable `id`, `type`, integer `order`, and `text`. Block types in v1 are `prose`, `dialogue`, `narration`, `direction`, and `note`. A block may include `character_id` (nullable) and `entity_refs` (an array of stable world-entity IDs).

## 3. Identity and ordering

- IDs are persisted data, not array indices. Reordering must not change IDs.
- `order` is explicit and is interpreted within the parent container. Array order and numeric order must agree when writing a canonical document.
- IDs must remain intact when the same story file moves between Web and Desktop.
- References to world entities use their existing stable IDs. A missing target must be reported as a broken reference; readers must not silently rewrite or discard it.
- Empty title/text values may be allowed by the editor during drafting; structural validation must still require the correct field types.

## 4. Minimal v1 scope

Phase A specifies the data contract and compatibility tests only. It does not yet introduce UI, automatic prose generation, branching routes, conditions/flags, timeline integration, continuity linting, or format-specific exports. Those are later phases in `plan.md`.

## 5. Cross-platform acceptance criteria

Both repositories must carry byte-identical copies of the golden fixture at `tests/fixtures/axral-story-v1.json`.

1. Both implementations can parse the fixture without data loss.
2. Serialization preserves all IDs, text (including Japanese and line breaks), references, and order values.
3. A Web → Desktop → Web round-trip preserves the semantic document.
4. Unknown schema versions fail clearly and do not overwrite the source file.
5. Invalid or missing world-entity references remain visible as validation findings rather than being silently removed.
6. Existing `axral-project-v1.json` persistence contract tests continue to pass unchanged.

## 6. Implementation guardrails

- Define the shared contract before building either UI.
- Keep Web and Desktop work in paired PRs, and use the same fixture and acceptance cases.
- Do not alter existing `.axral.json` v1 codecs or existing save/load/export handlers in order to add story authoring.
- No destructive migration or implicit conversion. Any future migration must be explicit, reversible where possible, and covered by fixtures for both platforms.
