# Review fix 03 — bounded handoff execution

Implemented: at most two durable execution claims; third expired recovery terminalizes without model dispatch. Failed or unavailable execution leaves the execution queue. One persisted terminal notice claim precedes its send attempt; missing owner/endpoint consumes an explicit nondelivery outcome, preventing notice-page starvation. Provider uncertainty cannot authorize a resend. Successful execution remains complete-before-send: transport acceptance is not promised.

Target conversation ensure runs inside the execution failure boundary. Per-row recovery failures do not abort later rows. Owned expired/resolved handoff callbacks remove their stale buttons; foreign handoffs remain untouched.

The carried user input and assistant output are atomic lease-fenced once-per-role transcript writes. Missing or changed recorded messages refuse replay. Current carried input is excluded by ID before transcript DTO projection/history construction; Daily retains its original call path and three-field DTO. Existing persisted model plans and command receipts continue replaying effects; this change does not claim network delivery exactly once.

Files: migration017/assert017; handoffs.py; modes.py and all three Stores; context.py, turns.py, handlers.py; bounded/terminal execution tests. Protected file: migrations/017_mode_conversations.sql.

Red: new integration regressions initially10 failed (two channel variants): repeated failure notices, ensure outside failure boundary, duplicated carried history, stale buttons, recovery row isolation. Green after fix: full1352 passed20.36s; focused90 passed3.87s; Gate A currency + Session DTO + handoff checks132 passed11.23s. Scoped Ruff and git diff --check clean. Scheduler smoke passed. No Gemini/model/provider/production calls.

Author SQL: fresh45-file CI chain passed, local cluster /private/tmp/amigo-handoff-item4-vv03hoa1 stopped. Driver /tmp/amigo-handoff-item4-verify.py. SQL017 SHA25609e0a28583ddac0129657432bd1fc2bb16733194f89f27e3ab458bc7561a3df2. Assertions cover cap2, expired append token, replay content identity, role owner checks, notice single-use and service-only RPC privileges. Independent usage_gate review PASS at the same hash: own fresh45 SQL chain plus owner/token/role/lease/content fences, user+assistant dedup after reclaim, third claim terminal/count2, notice owner/reason/endpoint nondelivery/no-resend. Own42 tests passed2.54s. Driver /tmp/amigo-independent-handoff-item3.py; extra /tmp/amigo-independent-handoff-item3-extra.sql; cluster /tmp/amigo-independent-item3-v7dmpjfy stopped. Final local parity focused42 passed2.51s; Ruff/diff clean.

Remaining limits: a crash after notice claim can lose its notification; uncertain sends deliberately do not replay. A crash after successful execution completion can similarly lose the success reply. At-most-one notice attempt means no delivery guarantee. No new privacy promise.
