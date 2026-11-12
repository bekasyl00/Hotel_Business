---
name: focused-implementation
description: Execute Tynys implementation and debugging tasks with targeted source reads, stage checkpoints and focused verification. Use for tasks from docs/agent-tasks.md.
---

# Focused implementation

1. Read git status, applicable project rules and only the active task section. Read required architecture before structural changes. Use docs/agent-navigation.md for entry points.
2. Write up to three next actions for the current stage. For a large task implement one independently verifiable stage at a time, saving its outcome before continuing.
3. Find symbols with rg -n. Read the enclosing function/component section, its direct caller and one relevant test/pattern. Read complete files when necessary for correctness. For files above 400 lines start with symbol search and relevant ranges instead of sequentially paging through the whole file.
4. After an initial investigation of roughly 5–8 source reads, either implement a justified change, run a diagnostic that distinguishes hypotheses, or state the specific missing fact and expand the search. This is a checkpoint, not a hard limit on essential analysis.
5. Re-read sections when they changed, a failure points there, or earlier context was lost. Preserve a short symbol map in the task report to avoid rediscovering unchanged code.
6. Discover relevant installed skills from their descriptions once per stage. Load one primary skill and, when needed, one additional skill. Use Django/database guidance for server transactions, Vue guidance for UI, native guidance for bridges/signing, and release guidance for publication. Read actual SKILL.md before applying it. If unavailable, use repository instructions and official vendor docs for the specific uncertainty.
7. Select MCP tools by the concrete check needed. Use filesystem/terminal for source and builds, browser tools for UI/network, GitHub for releases, provider tools for configuration. Listing available plugins is not evidence of using them.
8. Run the narrow regression check first, then mandatory repository gates at integration/release. Reuse successful results for the same unchanged revision and environment. Track background jobs until exit and verify their output artifact.
9. After two unsuccessful attempts at the same error, record exact error, hypotheses tried and next diagnostic. Continue independent work. Do not repeat the same command without a reason it can now succeed.
10. Report concise evidence: changed paths, test outcome, stage status, next action or concrete blocker. Summarize tool output instead of pasting full logs. End implementation with READY_FOR_REVIEW and preserve physical-device checks as pending until observed.
