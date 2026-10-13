# Usability test kit

**Status: no sessions have been run. Every results table below is intentionally empty.** Fill them in only with real observations.
Nothing from this file may be quoted as a result until it has data in it.

## Plan

- **Participants:** 5 to 8 adults who do not know the app and have not seen the code. At least half should do the tasks on their own phone.
  Record age band and whether they have used a calorie tracker before; do not collect names.
- **Session length:** about 15 minutes. One facilitator, one note-taker (or screen recording with consent).
- **Version tested:** the rebuilt UI at the commit recorded in the log below. To compare with the old UI, run the same script with the
  original version (`git show 548d2cd:nutrition_tracker.py`) on different participants; do not run both on the same person without
  counterbalancing the order.
- **Setup for every participant:** open the app in a new private window so the link (`?u=`) is new, then press **Load a sample week**
  (Profile or Insights) so that "yesterday" has data. Remove the sample data at the end.

## Facilitator script

Read aloud: *"We're testing the app, not you. Please think out loud. I can't help during the tasks; if you get stuck, tell me what you
expected to happen. You can stop at any time."*

Give one task card at a time. Start the timer when they finish reading; stop it when they say they are done or you see the end state.
Stop a task at 3 minutes and mark it as not completed. Do not hint.

| Task | Card text | Success means |
|---|---|---|
| T1. Log a meal | "You just had two slices of toast and a banana for breakfast. Add it to today's log." | Both foods are in today's log under Breakfast. |
| T2. Set a goal | "You want to eat about 1,800 calories a day. Set that as your daily goal." | Profile (or setup) shows a calorie goal of 1,800 and the Today summary uses it. |
| T3. Find yesterday's total | "How many calories did you eat yesterday?" | They state the History (or Insights, day = yesterday) value correctly. |

Optional probes after T1: "Was the food it picked right?" and "What would you do if it were wrong?" (observe whether they find
**Pick another match**).

## Task sheet (one row per participant per task)

Record `Completed` as Y / N / Y with help. Count errors as taps or entries that were not needed for the task. Quote a short comment
only if the participant said it.

| P | Device | Used a tracker before? | Task | Time (s) | Completed | Errors | Where they hesitated | Comment |
|---|---|---|---|---|---|---|---|---|
| P1 | | | T1 | | | | | |
| P1 | | | T2 | | | | | |
| P1 | | | T3 | | | | | |
| P2 | | | T1 | | | | | |
| P2 | | | T2 | | | | | |
| P2 | | | T3 | | | | | |
| P3 | | | T1 | | | | | |
| P3 | | | T2 | | | | | |
| P3 | | | T3 | | | | | |
| P4 | | | T1 | | | | | |
| P4 | | | T2 | | | | | |
| P4 | | | T3 | | | | | |
| P5 | | | T1 | | | | | |
| P5 | | | T2 | | | | | |
| P5 | | | T3 | | | | | |
| P6 | | | T1 | | | | | |
| P6 | | | T2 | | | | | |
| P6 | | | T3 | | | | | |
| P7 | | | T1 | | | | | |
| P7 | | | T2 | | | | | |
| P7 | | | T3 | | | | | |
| P8 | | | T1 | | | | | |
| P8 | | | T2 | | | | | |
| P8 | | | T3 | | | | | |

### Summary (fill in after all sessions)

| Task | Completed / n | Median time (s) | Fastest | Slowest | Most common problem |
|---|---|---|---|---|---|
| T1 | | | | | |
| T2 | | | | | |
| T3 | | | | | |

With 5 to 8 people, report counts ("6 of 7 completed"), not percentages, and say that the sample is too small for statistical claims.

## System Usability Scale (SUS)

Give this after the tasks. Participants answer each statement from 1 (strongly disagree) to 5 (strongly agree).

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

### Scoring

For odd-numbered items the contribution is (answer - 1); for even-numbered items it is (5 - answer). Add the ten contributions and
multiply by 2.5 to get a score from 0 to 100. Average the participants' scores. Scores are not percentages; a common reference point is an
average of about 68 across many products, but with fewer than ten participants treat the result as indicative only.

### SUS answers

| P | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | SUS score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | | | | |
| P2 | | | | | | | | | | | |
| P3 | | | | | | | | | | | |
| P4 | | | | | | | | | | | |
| P5 | | | | | | | | | | | |
| P6 | | | | | | | | | | | |
| P7 | | | | | | | | | | | |
| P8 | | | | | | | | | | | |
| **Mean** | | | | | | | | | | | |

## Session log

| Date | Commit tested | Facilitator | Notes |
|---|---|---|---|
| | | | |
