# Design

**Design System:** [RuleStorm Design System](https://claude.ai/artifact/LZYe9hhpeto8uWEMimXy6n) (Claude Design System artifact)

Read its `project/README.md` first (the brand book), then `project/tokens.json` for exact values and `project/components/bundle.css` for component styles. Every screen in docs/USER_JOURNEY.md has its components there, with every state. `/ui` reads these from the link; don't copy values by hand.

**Direction (chosen 25 Nov):** two rooms in one system.
- **The bench**: every screen before and after the run (S1–S4, S6–S9). Analytical and flat: lanes with a dashed threshold line, evidence chain, compare tables.
- **The stage**: the run screen (S5). A bright population stage: four zones from the engine's building blocks (getting there, duty, request desk, check), little "figuroid" people who think, talk, file request slips and walk through the check gate, driven by the polled timeline.

Fonts (Google): Bricolage Grotesque (headings), Atkinson Hyperlegible Next (text), Atkinson Hyperlegible Mono (IDs and calculations only). No logo yet: the name in Bricolage Grotesque 700.

Shared stage helper: `project/stage/figuroid.js` (`RSFig.figure({role, initial, name, state, tag})`) draws one person as SVG.
