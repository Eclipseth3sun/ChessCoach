# Screenshot shot list

Capture these from the running app and save them here with the exact filenames
below (the README links to them). Recommended: maximize the window (~1440×920),
pick the theme you like best, and use a game that's fully coached.

| Filename | What to show |
| --- | --- |
| `game-view.png` | **Hero shot.** A coached game open: board + eval graph on the left, the coach's report panel on the right. Step to a move that has a grade badge (★/!/?!) visible on the board. |
| `game-list.png` | The game list / dashboard: the stats strip (games · W·L·D · analyzed · coached) and a few rows with result chips and analysis pills. |
| `coaching.png` | A close-up of the coach panel — opening summary + a couple of key-moment cards (one positive ✓, one mistake) with the strategic explanations. |
| `variation.png` | A variation step-through at the decision point of a mistake, showing the **red (played)** vs **green (best)** arrows on the board and the banner. |

Optional extras (not linked yet, but nice for the repo / a future post):

- `onboarding.png` — the first-run checklist (visit `/?welcome=1` to force it).
- `themes.png` — the topbar theme picker, or the same screen in two different palettes side by side.

Once added, delete this file or leave it — it's harmless. Then commit:

```
git add docs/screenshots/*.png
git commit -m "Add README screenshots"
```
