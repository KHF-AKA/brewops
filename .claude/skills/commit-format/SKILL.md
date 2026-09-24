---
name: commit-format
description: Applies BrewOps' house style for git commit messages in this repo. Every commit message made in the brewops project must end with a smiley face and a word count of the message body. Use this whenever you are about to run `git commit` in this repository, drafting a commit message, or the user asks you to commit changes here.
---

# BrewOps commit message format

This repo has one extra house rule on top of any standard attribution trailers: every commit message must end with a smiley and a word count.

## Format

1. Write the commit message body as usual (subject line + optional body).
2. Add any required attribution trailer lines (e.g. `Co-Authored-By: ...`) if the session's instructions call for them.
3. As the very last line of the message, add a smiley followed by the word count of the message body (subject + body text, not counting the smiley line itself or trailer lines):

```
<word count> words 🙂
```

## Example

```
fix: correct brew-count aggregation for decaf drinks

Decaf entries were being excluded from the daily total because
the health-aggregate query filtered on drink_type incorrectly.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

22 words 🙂
```

Count words in the subject line and body only — skip trailer lines (Co-Authored-By, Generated with, etc.) and skip the word-count line itself when counting.

## Why

This is a lightweight, repo-local convention for BrewOps commits — it does not apply to other projects. Don't add it to commits outside this repository.
