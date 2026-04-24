"""Generate CLAUDE.md, STATUS.md, NOTES.md for a collaborative project."""

import os


def generate_claude_md(project_dir: str, code_repo: str = "", paper_repo: str = "") -> str:
    """Generate CLAUDE.md content with workflow instructions."""

    repo_section = ""
    if code_repo:
        repo_section += f"\n- Code repository: `{code_repo}`"
    if paper_repo:
        repo_section += f"\n- Paper repository: `{paper_repo}`"

    paper_instructions = ""
    if paper_repo:
        paper_instructions = f"""
## Paper Repository

The paper repo is `{paper_repo}`. Paper updates are triggered automatically when
code merges to main. When updating the paper:
1. Clone or pull the paper repo
2. Make the relevant changes
3. Submit a PR on the paper repo with a clear description of what changed and why
"""

    return f"""# Project Conventions

## Repositories
{repo_section}

## Workflow Rules

### Before Starting Any Task
1. Read `STATUS.md` for current project state, active tasks, and blockers
2. Read `NOTES.md` for related work, discussion notes, and shared resources
3. Check if anyone else is working on related files (check STATUS.md active tasks)

### While Working
- Work only on your assigned task
- Do not modify files that another active task is working on (check STATUS.md)
- Commit frequently with clear messages

### When Finishing a Task
1. Push your branch to the remote: `git push -u origin <branch-name>`
2. Create a PR: `gh pr create --title "<concise title>" --body "<description>"`
3. Update `STATUS.md`: move your task from Active to In Review, add the PR link
4. Never push directly to main — always submit a PR

### Updating STATUS.md
When you update STATUS.md, follow this format:
- Move completed tasks from "Active" to "In Review" or "Done"
- Add PR links next to completed items
- Note any blockers you discovered
- Add relevant decisions to the "Recent Decisions" section

### Adding Notes
If you discover related work, make a design decision, or find a useful resource,
add it to NOTES.md with your name and today's date.
{paper_instructions}
## Code Style
- Follow existing code conventions in the repository
- Write clear commit messages explaining why, not what
- Keep PRs focused — one task per PR
"""


def generate_status_md() -> str:
    return """# Project Status

## Current Goal
<!-- Update this with the current sprint/milestone goal -->

## Active Tasks
<!-- Format: - [person]: task description (branch: branch-name) -->

## In Review
<!-- Format: - PR #N: description (author) — status -->

## Recently Done
<!-- Format: - PR #N: description (merged YYYY-MM-DD) -->

## Blocked
<!-- Format: - description — waiting on X -->

## Recent Decisions
<!-- Format: - YYYY-MM-DD: decision description (participants) -->
"""


def generate_notes_md() -> str:
    return """# Project Notes

## Related Work
<!-- Add relevant papers, projects, and references here -->

## Discussion Notes
<!-- Add key discussion outcomes and decisions here -->

## Resources
<!-- Add useful links, datasets, tools here -->
"""


def scaffold_project(project_dir: str, code_repo: str = "", paper_repo: str = "") -> list[str]:
    """Create CLAUDE.md, STATUS.md, NOTES.md if they don't exist.

    Returns list of files that were created (not overwritten).
    """
    created = []

    files = {
        "CLAUDE.md": generate_claude_md(project_dir, code_repo, paper_repo),
        "STATUS.md": generate_status_md(),
        "NOTES.md": generate_notes_md(),
    }

    for filename, content in files.items():
        filepath = os.path.join(project_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, "w") as f:
                f.write(content)
            created.append(filename)

    return created
