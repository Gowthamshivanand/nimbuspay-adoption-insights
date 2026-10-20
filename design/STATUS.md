# NimbusPay FigJam v3 - build status
Updated: 20 Oct 2026, 05:49 IST

- FigJam file: https://www.figma.com/board/vz8IElp1RIfzjVK8Me8xoe
- Sections: Board 1 `3:2` (frames 1A `3:3`, 1B `3:601`), Board 2 `3:890`, Board 3 `3:1441`
- Step: 7 (fix loop) finished after 3 loops. Scores: B1 60/60, B2 59/60, B3 60/60.
- PNGs: board1-user-flow.png, board2-system-design.png, board3-agent-design.png (1x; get_screenshot caps at the node's own size, so 2x export was not available)

## Build results
| Chunk | sectionId | nodesCreated (expected) | groups | groupFailures | steps | fonts |
|---|---|---|---|---|---|---|
| 01 | 3:2 | 394 (363) | 65 | 0 | 43 | Inter / mono: JetBrains Mono |
| 02 | 3:890 | 234 (212) | 40 | 0 | 29 | Inter / mono: JetBrains Mono |
| 03 | 3:1441 | 187 (172) | 33 (32) | 0 | 21 | Inter / mono: JetBrains Mono |
Higher node counts: FigJam made rounded corners > 32 px, so the chunk's own fallback redrew those nodes as rectangle + text.

## Host-compatibility fixes (owner-approved, no design/data change)
1. chunk-01/02/03.js line 92: `n.setPluginData('step', String(NUM))` -> `n.setSharedPluginData('nimbuspay', 'step', String(NUM))`. Reason: setPluginData not supported in this host.
2. chunk-01/02/03.js line 97: `if (n.shapeType === 'ENG_DATABASE')` -> `if (n.type === 'SHAPE_WITH_TEXT' && n.shapeType === 'ENG_DATABASE')`. Reason: host throws on reading shapeType on RECTANGLE nodes.

## Fix loops (in place, use_figma)
- Loop 1 fix: FigJam truncated shape text with "..." (e.g. "Role recognise...", "Picks a governe...", source cylinders on B2). 32 shape labels (diamonds, cylinders, rounded shapes) moved into separate centred text nodes with the same text, font, size and colour, inside the same "Node:" group. Script: out/fix-loop1.js.
- Loop 2 fix attempt: App host boundary (3:909) moved to the back (z-order only) so the "Not schema-validated" label would cover the dash. No visible effect; FigJam draws connector labels without a pad over it.

## Open issues
- B2 S1 [P3]: App host dashed boundary (x ~505 local) runs through the connector label "Not schema-validated" (5 -> 7, y ~1004). FigJam pins the label to the connector midpoint; fixing it means rerouting the connector or moving the boundary (a layout change). Needs owner decision.
- Sharing: owner must set "Anyone with the link can view" and send the link to Mohith.
