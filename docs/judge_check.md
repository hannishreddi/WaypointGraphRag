# Judge spot-check (3.3d)
Reviewer: Claude (an AI assistant), not the author. Rows are the 6 per system that the runner wrote to judge_review.csv (random.Random(42) over each system's judge-scored ids, so the two systems' samples differ). Judge: gemini-3.5-flash-lite (judge-v1).
Runs: S5 eval_runs/20261016-032128_s5_test; S1 eval_runs/20261016-134333_s1_test.

| system | id | judge verdict | reviewer verdict | agree | note |
|---|---|---|---|---|---|
| S5 | Q103 | correct | correct | yes | sponsor and lead both right |
| S5 | Q117 | correct | correct | yes | sponsor and lead both right |
| S5 | Q187 | correct | correct | yes | No, 3.4 y of 5 required |
| S5 | Q189 | correct | correct | yes | Yes, eligible; omits the 8.3 years; extra details not verified |
| S5 | Q224 | correct | correct | yes | 3 months, extendable by 3 months |
| S5 | Q231 | correct | correct | yes | all required items present; extras not verified |
| S1 | Q105 | correct | correct | yes | sponsor and lead both right |
| S1 | Q174 | correct | correct | yes | full WFO, serving notice, ZEN-POL-002 |
| S1 | Q188 | incorrect | incorrect | yes | "cannot find" where gold is No with reason |
| S1 | Q190 | incorrect | incorrect | yes | same |
| S1 | Q225 | partial | partial | yes | says Yes; misses shift window, GPS, escort |
| S1 | Q233 | correct | correct | yes | CEO and CFO |

Agreement 12/12 (exact 95% lower bound about 0.74). Limits: 6 rows per system; AI reviewer, not the author; extras beyond the gold answer were not verified against the policy text; the S5 sample contains no policy question, so it says nothing about S5's low policy score.
