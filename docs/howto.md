# Jetsam Cheatsheet

## Setup
```bash
jetsam init --mcp --agents claude --hooks claude   # full agent setup
jetsam init --aliases                               # shell shortcuts
```

## Daily workflow
```bash
jetsam status                    # where am I?
jetsam start 42                  # branch from issue number
jetsam save -m "fix parser"     # stage + commit
jetsam ship -m "fix parser"     # stage + commit + push + PR
jetsam finish                    # merge PR + cleanup
```

## Sync & push
```bash
jetsam sync                      # fetch + rebase/merge + push
jetsam ship --no-pr              # push without creating a PR
```

## Scoped staging
```bash
jetsam save src/main.py -m "fix"          # specific files only
jetsam ship --include "*.py" -m "update"  # glob pattern
jetsam ship --exclude "*.log" -m "clean"  # exclude pattern
```

## PR & CI
```bash
jetsam pr                        # view PR for current branch
jetsam prs                       # list all PRs
jetsam checks                    # CI status
jetsam release v1.0.0            # tag + push + GitHub release
```

## Plan control
```bash
jetsam ship -m "feat" --execute  # skip confirmation
jetsam ship -m "feat" --dry-run  # preview only
jetsam stash list                # unknown commands → git
```
