# Antigravity: Tynys implementation protocol

Read AGENTS.md first. It remains the authoritative project safety and domain rulebook.
Then read docs/agent-tasks.md and the referenced task specification.

The project owner discusses requirements with Codex. Codex maintains plans and acceptance criteria; Antigravity implements application code. These agents do not share conversation memory: repository files are the handoff contract.

When the owner writes «Далее», «Следующее задание» or «Работай»:
1. Inspect git status and current branch; preserve existing work. Read the current task and its prerequisites.
2. Execute the earliest READY task, following its stages in order. Continue through implementation, required tests, documentation and report; do not stop after writing another plan.
3. Change READY to IN_PROGRESS before implementation. Record completed stages and evidence as you go. Do not mark DONE from a build alone.
4. Routine technical choices follow existing project conventions. Record assumptions. If a missing business decision or credential prevents safe progress, mark the affected stage BLOCKED with one specific question and continue independent stages.
5. Never invent payment events, guest identities, successful deployment or test results. Never expose .env files, signing keys or real guest data. Do not send money, issue refunds or change provider access merely to test.
6. At completion record changed modules, migrations, commands/results, unresolved risks, deployment status and commit in the task report. Update architecture/contracts/decisions when implementation changes them.
7. Use an implementation branch from the verified current project head; preserve uncommitted changes. Commit scoped work. Deployment or native installation requires an explicit task instruction; readiness is not deployment.

If there is no READY task, report that the queue is empty. Do not invent new features.
