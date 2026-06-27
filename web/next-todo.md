# Amigo demo UI — next_to_do.md

Generated: 2026-06-17

---

## What the current state looks like

The mode chips are now correctly placed as a horizontal row between the
Horizon card and the dashboard grid. The Recommender chip is clickable and
shows an active orange state. The layout structure is correct.

---

## Immediate fixes (do these first — visual polish)

### 1. Horizon card: still no glass effect
The card has a flat dark fill. The glass treatment is the signature visual
moment of the whole UI and it is still missing.

```css
.horizon-card {
  background: rgba(29, 24, 40, 0.55);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(183, 178, 201, 0.1);
}
```

Also set the page background to `#14121A` (warm violet near-black) so the
blur has something to bleed into. On a flat solid background, backdrop-filter
has no visual effect.

### 2. "Good afternoon" heading: still sans-serif
The spec calls for system serif here. Add to the greeting element:

```css
font-family: ui-serif, Georgia, "Iowan Old Style", "Times New Roman", serif;
font-weight: 400;
```

### 3. Sidebar active state: still solid orange fill
The "Dashboard" item has a solid `#FF8A5B` background, which reads as a
button, not a nav selection. Change to a left-border accent:

```css
/* remove */
background: var(--ember);
border-radius: 8px;

/* add */
background: rgba(255, 138, 91, 0.1);
border-left: 2px solid var(--ember);
border-radius: 0 8px 8px 0;
color: var(--ember);
```

### 4. Mode chip active state: Recommender should not be selectable yet
The Recommender chip appears as orange/active even though it is a "coming
soon" item. The `disabled` prop and `available: false` flag should prevent
this. Check that the `onClick` guard is working:

```js
onClick={() => available && onModeChange(id)}
```

If Recommender is showing as active, `available` may have been accidentally
set to `true` in `MODES`. Fix it back to `false`.

### 5. Horizon subtext is mode-aware but shows a confusing message
"Discover mode is coming soon. For now, keep steering the day from Daily."
This message implies the user successfully switched to Discover mode, which
contradicts the disabled state. The subtext should only change when the user
is actually in an active mode. For now, since only Daily is available, the
subtext should always show the Daily copy:

```
"Keeping the momentum going."
```

Remove the fallback/coming-soon subtext entirely until the modes are real.

### 6. Page background color
Body background appears to be `#0a0a0a` or similar flat black. Change to:

```css
body { background-color: #14121A; }
```

### 7. Primary text color
Body text appears pure white. Change to warm off-white:

```css
color: #F7F3EC;
```

---

## Short-term improvements (next 1–2 sessions)

### 8. Add gold accent color usage
`--gold: #F3C26A` is defined but not used anywhere visible. Apply it to:
- The clock icons in Active Reminders (currently orange — clock should be gold)
- Focus rings on inputs (`:focus-visible` outline)
- The progress stat circle icon in the Horizon card

### 9. Task input field needs a visible focus state
When the user clicks "Add a new task..." the field should show a gold focus
ring, not the default browser outline:

```css
.task-input:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(243, 194, 106, 0.4);
}
```

### 10. "Snooze 15m" buttons look like primary actions
They are styled with a prominent border, making them look more important than
they are. Reduce their visual weight:

```css
.snooze-btn {
  background: transparent;
  border: 1px solid rgba(183, 178, 201, 0.15);
  color: var(--mist);
  font-size: 12px;
  padding: 6px 12px;
}
.snooze-btn:hover {
  border-color: rgba(183, 178, 201, 0.3);
  color: var(--paper);
}
```

### 11. Card background separation
Tasks and Reminders cards look very similar in tone to the page background.
Cards should be `#1D1828` (--dusk) so they lift off the `#14121A` page:

```css
.card { background: #1D1828; }
```

### 12. "Focused" and "Casual" mood tags in Recent Sessions need color
They are currently plain orange text. Assign distinct subtle colors:
- Focused → teal/green tint: `rgba(29, 158, 117, 0.15)` bg, `#1D9E75` text
- Casual → muted amber: `rgba(243, 194, 106, 0.12)` bg, `#F3C26A` text

---

## Medium-term: feature work (next week+)

### 13. Build the Recommender mode view
When Recommender is unlocked, clicking it should swap the dashboard content
area to show:
- A mood/vibe prompt ("What are you in the mood for?")
- 3 cards: one film rec, one music rec, one activity rec
- Each card has a title, genre/type tag, and a one-line reason

Start with static mock data, same pattern as the existing `mockData.js`.

### 14. Build the Coach mode view
When Coach is unlocked, show:
- Habit streak cards (reading, workouts, sleep) — mock data
- A single nudge message from Amigo based on the weakest streak
- A simple week-view bar for each habit (7 small squares, filled or empty)

### 15. Implement real reminder scheduling
Current reminders are mock data. Wire up:
- `reminder.fire_at` stored as UTC in Supabase
- ARQ background worker polling every 60s for `fire_at <= NOW()`
- Telegram bot sending the reminder message with inline buttons
- Callback handler for Done / Snooze 15m / Dismiss

See the task/reminder architecture doc for the full schema.

### 16. Natural language task/reminder creation
Add a chat-style input (could be the existing task input, extended) that:
- Detects "remind me to X at Y" patterns
- Calls the LLM with a structured extraction prompt
- Returns `{ task: {...} | null, reminder: {...} | null }` JSON
- Writes to Supabase and confirms back to the user

### 17. Mobile layout — bottom tab bar
On screens < 768px, the sidebar should collapse and a bottom tab bar should
appear with: Dashboard, Connect Apps, and (later) mode switcher. The current
layout likely breaks on mobile. Add a responsive breakpoint:

```css
@media (max-width: 768px) {
  .sidebar { display: none; }
  .bottom-nav { display: flex; }
}
```

---

## Architecture decisions to make before scaling

### 18. Ability router in the agent
Before adding more modes, define how the Telegram bot decides which mode
logic to invoke. Options:
- Explicit: user sets mode via `/mode coach` command
- Implicit: LLM classifier on every message returns `{ mode, confidence }`
- Hybrid (recommended): implicit classifier with explicit override

Design this now so each new mode is just a registered handler, not an
if/else branch in the main prompt.

### 19. Memory scope per mode
- Daily: short-term session memory only
- Coach: needs persistent habit history (weekly cadence)
- Recommender: needs taste profile (persists across sessions)
- Reflect: needs mood history but with a forgetting policy

Decide which of these live in Supabase vs the agent's context window before
building mode 2.

### 20. Crisis safeguard (required before Reflect/Wellbeing ships)
Before the Reflect or any wellbeing mode goes live, implement:
- Keyword detection for distress signals in the agent prompt
- Hard exit from bot flow when triggered
- Redirect to a helpline message (iCall Nepal: 9840021600 for KTM users)
- This is non-negotiable — do not ship Reflect without it

---

## Priority order

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | Glass effect on Horizon card | 10 min | High |
| 2 | Serif greeting font | 5 min | High |
| 3 | Fix sidebar active state | 10 min | Medium |
| 4 | Fix chip disabled state | 5 min | Medium |
| 5 | Fix subtext copy | 5 min | Low |
| 6–7 | BG + text color | 5 min | Medium |
| 8–12 | Polish (gold, snooze, cards) | 1 hr | Medium |
| 13–14 | Recommender + Coach views | 2–3 days | High |
| 15–16 | Real reminders + NLP input | 3–5 days | High |
| 17 | Mobile layout | 1 day | Medium |
| 18–20 | Architecture + safety | Before scale | Critical |