# OpenClaw Discord Channel Replies — Bug Investigation & Fix

A two-bug post-mortem on why OpenClaw's Discord plugin silently drops agent replies in guild channels, and the two-config-flip fix.

📄 **[Read the full post-mortem →](./Discord_Chat_Fixes.md)**

## TL;DR

```
messages.groupChat.visibleReplies     = "automatic"     # else dispatcher suppresses ALL channel replies
agents.defaults.silentReply.group     = "disallow"      # else model emits NO_REPLY for cold/ambient channels
```

Restart the OpenClaw gateway after either change.

## What's covered

- Symptoms (DMs work, channel replies silently fail)
- Bug #1: dispatcher-level suppression with source-line proof
- Bug #2: agent-prompt `NO_REPLY` behavior with trajectory evidence
- Verification (no Discord typing required)
- Suggested upstream improvements for OpenClaw maintainers
- Investigation history (5 wrong hypotheses for context)

## Status

Both fixes verified live in production 2026-05-03 / 2026-05-04. ~6.5 hours of debugging compressed into one self-contained writeup.
