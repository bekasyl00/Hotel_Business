# Task navigation

Use paths as entry points. Verify symbols with rg because line numbers and modules change. Read domain rules from AGENTS.md and the relevant contract sections.

| Task area | Start here |
| --- | --- |
| Native staff push, active T003 | backend/booking/notifications.py, backend/booking/models.py (StaffPushDevice/StaffPushDelivery), backend/commerce/jobs.py and scheduler.py |
| Native registration and startup | src/app/main.js, src/app/App.vue, src/shared/api/mobile-client.js, native/ios, native/android |
| Native platform configuration | package.json, capacitor.config.*, ios-staff/App/App/AppDelegate.swift, android-staff/app/src/main/AndroidManifest.xml; verify paths before reading |
| Staff session/auth | rg --files src/entities and search staff/mobile auth; backend/booking staff-mobile-auth handlers |
| Notification list and navigation | src/pages/workspace/ui/WorkspacePage.vue, search loadNotifications/openNotification/notification; src/widgets/staff-shell |
| Booking places/planner | backend/booking/availability.py and services.py; src/widgets/occupancy-board; src/entities/booking/model/occupancy.js |
| Pricing | backend/booking/pricing.py; src/entities/booking/model/rules.js |
| Release/device commands | docs/ios.md, docs/android.md, package.json and scripts/build-android.mjs |

WorkspacePage.vue currently exceeds 1,500 lines. For push work inspect notification handlers and the route lifecycle that calls them. Expand into unrelated editors only if a caller or failure requires it.

## Restart checkpoint format

Append a short checkpoint to the active task after completing a stage or before context compaction.

- Revision and stage
- Inspected paths and symbols, one-line findings
- Changes and checks completed
- Background task IDs still running
- Next concrete action
- Missing configuration or unresolved question

Keep the latest checkpoint short. Store full historical reports below completed tasks.
