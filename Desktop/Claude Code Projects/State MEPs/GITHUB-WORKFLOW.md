# GitHub Workflow for This Project

## Daily Pattern
1. Start work: Create or switch to a feature branch
2. Work in small chunks: Make changes, test, commit when working
3. End session: Push to GitHub, note branch status in CURRENT.md

## Branch Naming
- Feature work: `feature/description` (e.g., `feature/csv-reader`)
- Bug fixes: `fix/description` (e.g., `fix/data-parsing`)
- Experiments: `experiment/description` (e.g., `experiment/new-scraper`)

## When to Commit
- After getting a feature working (even partially)
- Before trying something risky
- End of work session (even if not done)
- Commit message format: Clear description of what works now

## When to Merge to Main
- Feature is fully working and tested
- Documentation is updated
- No broken functionality

## Safety Rules
- Never commit directly to main - always use a branch
- If unsure, commit to branch and don't merge yet
- Keep main branch always in working state

## Claude Code Instructions
When working with Git/GitHub:
- Create feature branches automatically
- Commit working code with clear messages
- Ask before merging to main
- Push to GitHub at end of session
