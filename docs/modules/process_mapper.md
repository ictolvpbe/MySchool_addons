# process_mapper

BPMN-like business process mapping met prompt-generation. Visualiseert school-processen als flow-diagrammen + genereert AI-prompts om processen te analyseren of te verbeteren.

## Status

| Onderdeel | Stand |
|---|---|
| Status | stable, in productie |
| Dependencies | `base`, `web`, `myschool_core` |
| Wordt gebruikt door | `myschool_devhub` (process-flow per project) |

## Doel

Tweeledig:

1. **Process-visualisatie**: BPMN-achtige diagrammen voor school-processen (aanvragen, goedkeuringen, workflows)
2. **AI-prompt-generation**: vanuit een gemapped proces wordt een prompt-template gegenereerd die je in Claude/ChatGPT kunt plakken voor proces-analyse of verbetering

## Architectuur

(Op basis van naam + dependency op `web`)

- Front-end visual canvas (SVG of canvas-based, web-laag)
- Back-end records voor processen, steps, gateways, swimlanes
- Export-functionaliteit naar prompt-format

## Relatie tot top-level docs

In repo-root staan twee bestanden die hierop betrekking hebben (zie [`../guides/`](../guides/) en [`../prompts/`](../prompts/) voor verplaatsing):

- `PROCESS_MAPPER_MANUAL.md` (top-level) → `docs/guides/process-mapper.md` na verplaatsing
- `BPMN_IMPROVEMENT_PROMPTS.md` (top-level) → `docs/prompts/bpmn-improvement-prompts.md` na verplaatsing

## In-module docs

Geen aparte README in de module-dir (maar wel deze top-level manual — TODO verplaatsen + crosslink).

## Gerelateerde modules

- [`myschool_devhub`](myschool_devhub.md) — depends op deze (project-flow-mapping)
- [`knowledge_builder`](knowledge_builder.md) — verwante visuele-builder-functionaliteit
- [`myschool_processcomposer`](myschool_processcomposer.md) — WIP, mogelijk overlap
