# Home room background

Asset: `public/scene-home.png`

Created with the built-in image generation tool. Style reference: `public/scene-work.webp`.

Prompt:

Use case: stylized-concept. Asset type: wide 16:9 visual novel game background for Life Reroll. Input image is a STYLE REFERENCE ONLY, not an edit target. Create a new cozy modest modern Taiwanese apartment bedroom interior that belongs to exactly the same illustrated world as the reference office campus: polished hand-painted anime background, crisp restrained outlines, soft painterly gradients, natural believable perspective, warm ivory surfaces, muted sage green and light wood, bright blue daylight through a window, leafy green trees outside. Eye-level wide room view: neatly made bed, small wooden desk, chair, bookcase, houseplant, curtains, comfortable lived-in room. Warm, restful homecoming mood with sunlit floor. Broad quiet central composition suitable for overlaying small game controls, detailed but uncluttered. No people, no text, no logos, no UI, no dice. Match the reference's linework, saturation, lighting quality, and architectural illustration finish. Render a full-bleed landscape background.

The home scene is shown after the return trip finishes. The workday phase is persisted by the backend: HOME_READY → roll/events/review → WORK_REQUIRED → WORKING → RETURN_HOME → HOME_READY. From home the player can roll again or take a FINANCE outing (FREE_TIME), then return HOME_READY. Work completion is a routine checkpoint; salary and elapsed time continue to be settled by the existing dice simulation, so completing work does not pay salary twice. Initial asset allocation remains available before the first roll.
