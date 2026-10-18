# Task walkthrough (scripted, NOT a usability test)

Run 2026-10-17 20:15 by `tools/ux/task_walkthrough.py`. Scripted walkthrough, NOT a usability test: best-case steps and times, 3 runs per version on fresh servers, one machine, real CalorieNinjas data, 1280x800 desktop. No participants, no SUS.

**What this is.** A script performs the three tasks from [`usability-test.md`](usability-test.md) on the original UI (commit `548d2cd`) and the
current UI, in a real browser, with the real CalorieNinjas API, and checks that the result on screen is correct. Each version was run
3 times on a fresh server; the step counts were identical every time.

**What this is not.** There are no people in it. A script knows where everything is, so the step counts are *best-case minimums* and the times are
*lower bounds*; a real person will hesitate, mis-click and read. It says nothing about how easy or pleasant either version feels, and it
produces no System Usability Scale score. Those need real participants.

| Task | Original UI | Current UI |
|---|---|---|
| T1. Log "2 slices of toast and a banana" | 3/3 completed; 3 clicks, 30 keystrokes; median 3.7 s | 3/3 completed; 2 clicks, 31 keystrokes; median 1.2 s |
| T2. Set a 1,800 kcal daily goal | 3/3 completed; 1 click, 7 keystrokes; median 1.2 s | 3/3 completed; 3 clicks, 4 keystrokes; median 2.8 s |
| T3. Find yesterday's calorie total | 0/3 completed; not countable; median 2.3 s | 3/3 completed; 1 click, 0 keystrokes; median 0.0 s |

## What it shows

- **T1 (log a meal): both can do it, but they log different things.** The original merges the phrase into a single row; the current UI split it:
  2 ingredient rows found, 2 entries logged. The script clicks the search box in both (in the real app the box is already focused on desktop, which would save one click).
- **T2 (set a goal): the current UI is slower here, and that is a real regression.** The original has the goal field at the top of the Today tab
  (1 click). In the current UI the goal lives in Profile (open the tab, click the field, click Save: 3 clicks), because I moved it out of the way to put
  search first. Setting a goal on first run goes through the setup card instead. A quick "set goal" shortcut on Today would remove most of this cost.
- **T3 (find yesterday's total): only the current UI can do it.** History row 'Fri 16 Oct' shows 1203 kcal, expected 1203. In the original the task is impossible from a fresh visit:
  after a page refresh the History tab is empty: nothing from earlier days survives (state lived only in the browser session).

## Limits of this evidence

One machine, 1280x800 desktop only, one phrase, a scripted user, sample data for "yesterday" (made-up values, loaded by the app's own button).
The original's goal field starts at a silent 2,000, which T2 overwrites; the current UI starts with no goal.
