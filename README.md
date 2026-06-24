# Agency Skills

Custom [Claude Code](https://docs.claude.com/en/docs/claude-code) skills for running the agency — client onboarding and GoHighLevel (GHL) delivery. Kept in Git so the same skills are available on every machine.

## Skills

| Skill | Purpose |
|-------|---------|
| `client-onboarding` | Scaffold a new client folder: credentials, brand context, package checklist |
| `ghl-delivery` | Orchestrator — loads a client's context and runs the GHL delivery tasks |
| `ghl-email-templates` | Create / restyle GHL email templates (logo + brand colors) |
| `ghl-calendars` | Create & manage GHL calendars, groups, appointments |
| `ghl-chat-widget` | Read & recolor GHL chat widgets to match brand colors |
| `ghl-cadence` | Convert a cadence doc (Word/PDF) into GHL AI Workflow Builder prompts |
| `resell-sequence` | Build the 12-month monthly resell email series (Full System) |

## Install on a new machine

Claude Code loads personal skills from `~/.claude/skills/` (`%USERPROFILE%\.claude\skills` on Windows).

**If `~/.claude/skills` does not exist yet:**

```bash
git clone <REPO_URL> ~/.claude/skills
```

**If it already exists (has other skills in it):** clone elsewhere and copy the skill folders in, or wire the remote into the existing folder:

```bash
cd ~/.claude/skills
git init
git remote add origin <REPO_URL>
git fetch origin
git checkout -t origin/main
```

Then restart Claude Code so it picks up the skills.

## Notes

- This repo only tracks the 7 custom skills above (see `.gitignore`). Third-party / plugin skills installed in the same folder are ignored.
- **No client credentials live here.** GHL tokens and location IDs are stored per-client under `~/Claude/Clients/<name>/ghl-credentials.md`, outside this repo.
