# OpenClaw Discord Channel Replies â€” Root Cause & Fix

> **TL;DR:** OpenClaw's Discord plugin silently drops agent replies in guild channels (DMs work fine). The root cause is **two stacked behaviors**, both fixable with two config keys â€” no source change required.
>
> ```
> messages.groupChat.visibleReplies     = "automatic"     # else dispatcher suppresses ALL channel replies
> agents.defaults.silentReply.group     = "disallow"      # else model emits NO_REPLY for cold/ambient channels
> ```
>
> Restart the gateway after either change. Both knobs are tagged `advanced` in the schema, so the default UI may not surface them.

---

## Symptoms

- Discord **DMs** to the bot work end-to-end (`Wendi is typingâ€¦` â†’ reply appears).
- Discord **guild channels** show `Wendi is typingâ€¦` then **silence**. No error in logs at info level.
- `openclaw message send --channel discord --target "channel:..."` from CLI **works fine** (different code path â€” bypasses the dispatcher).
- A process restart **temporarily** unblocks some channels but doesn't actually fix the bug; the suppression returns on the next inbound that matches the failing conditions.

---

## Bug #1: Dispatcher suppresses all group/channel replies by default

**File:** `/usr/lib/node_modules/openclaw/dist/source-reply-delivery-mode-DahE29Wm.js:6`

```js
if (chatType === "group" || chatType === "channel")
  return params.cfg.messages?.groupChat?.visibleReplies === "automatic"
    ? "automatic"
    : "message_tool_only";
return "automatic";
```

For Discord guild channels, `ChatType` is set to `"channel"` in
`/usr/lib/node_modules/openclaw/dist/extensions/discord/message-handler.process-Bo5-Suyq.js:485`:

```js
ChatType: isDirectMessage ? "direct" : "channel"
```

So unless `messages.groupChat.visibleReplies === "automatic"`, the dispatcher resolves the delivery mode to `"message_tool_only"`, which triggers the suppression path in `dispatch-Bd9Vyd-o.js:636`:

```js
const { ..., suppressDelivery, deliverySuppressionReason, ... } = sourceReplyPolicy;

if (suppressDelivery)
  logVerbose(`Delivery suppressed by ${deliverySuppressionReason} for session ...`);

deliver: async (payload, info) => {
  // ...
  if (suppressDelivery) return;   // <-- agent reply dies here
  // never reaches deliverDiscordReply
}
```

DMs (`ChatType: "direct"`) fall through to `"automatic"`, which is why DMs work and channels don't.

**Why other hypotheses don't fit:**
- *"Mention required" gate* would have killed the inbound in `message-handler.preflight-DR1wtLd6.js:627-641` â€” but a session with assistant text exists, so preflight let it through.
- *Thread-binding mismatch* would only affect routing inside `deliverDiscordReply` â€” but logs show `deliverDiscordReply` is never called for channel finals.
- *Slash/interaction pipeline* â€” only used for slash commands & components, not raw channel messages.

### Fix #1: Config flip

```bash
openclaw config set messages.groupChat.visibleReplies automatic
```

Or via gateway tool:
```json
[
  { "op": "add", "path": "/messages/groupChat/visibleReplies", "value": "automatic" }
]
```

**Restart the gateway after this change.** `cfg` is captured once at `monitorDiscordProvider` boot (`provider-Dy4gmGhl.js:7028`) and reused as a snapshot per inbound â€” it is not re-read live for this key.

---

## Bug #2: Even with #1 fixed, ambient/cold channels still go silent

After applying Fix #1, `#general` works but `#ventures`, `#clients`, `#wendi` (or any cold channel) still appear to drop replies.

**This is not a runtime gate.** The agent is intentionally returning `NO_REPLY`, which is then correctly stripped by the standard silent-reply normalizer.

### Where the drop happens

`/usr/lib/node_modules/openclaw/dist/normalize-reply-VyVCke1Q.js:21-26`:

```js
const silentToken = opts.silentToken ?? "NO_REPLY";
let text = payload.text ?? void 0;
if (text && isSilentReplyPayloadText(text, silentToken)) {
  if (!hasContent("")) {
    opts.onSkip?.("silent");
    return null;          // <-- NO_REPLY â†’ null â†’ enqueue returns false â†’ no delivery
  }
  text = "";
}
```

### Why the agent emits `NO_REPLY`

`/usr/lib/node_modules/openclaw/dist/get-reply-CfL1pJQm.js:605-616` builds the group-chat system prompt unconditionally including:

```
Be a good group participant: mostly lurk and follow the conversation;
reply only when directly addressed or you can add clear value.
```

When `silentReplyPolicy === "allow"` (the default for `group` per `silent-reply-CuB457HX.js:3-7`), it appends:

```
If no response is needed, reply with exactly "NO_REPLY" (and nothing else)
so OpenClaw stays silent.
Be extremely selective: reply only when directly addressed or clearly helpful.
... whole final answer must be only "NO_REPLY".
```

For a channel with rich prior conversational context, the model interprets new messages as part of the conversation and replies normally. For a **cold** channel where the bot is dropped in and someone sends a bare `"Test"`, the prompt's "mostly lurk" + `NO_REPLY` escape hatch wins â€” the model dutifully emits `NO_REPLY`.

**Verified live in trajectory logs:**
- `#ventures` session `c988037f-...`: user `"Test"` â†’ assistant `"NO_REPLY"`
- `#clients` session `441cfd28-...`: user `"Test"` â†’ assistant `"NO_REPLY"`
- `#wendi` session `0cb516c0-...`: user `"Test"` â†’ assistant `"NO_REPLY"`
- `#general` session (with 100+ prior context messages): user `"Test"` â†’ real reply âœ…

### Fix #2: Remove the NO_REPLY escape hatch from the prompt

```bash
openclaw config set agents.defaults.silentReply.group disallow
```

This sets `agents.defaults.silentReply.group = "disallow"`, consumed by `silent-reply-CuB457HX.js:resolveSilentReplySettings`. With `policy = "disallow"`:

- `get-reply-CfL1pJQm.js:607` `canUseSilentReply` becomes `false`.
- The `If no response is needed, reply NO_REPLY ...` block (lines 610-616) and the `Be extremely selective` line (612) are **omitted from the channel system prompt**.
- The agent has no token to silently emit. Empirically the model strongly prefers a real reply when no `NO_REPLY` escape hatch is offered.

**Note:** the hardcoded `"Be a good group participant: mostly lurk"` line at `get-reply-CfL1pJQm.js:605` remains â€” there is no config knob for it. The agent still uses judgment, but without the `NO_REPLY` escape it leans toward responding. This is the closest config-only fit for a private/single-user server.

**Restart required** â€” same `cfg`-snapshot reason as Fix #1.

### Why I did NOT also flip `silentReplyRewrite.group = true`

The Discord plugin doesn't pass `silentReplyContext` to the dispatcher (`message-handler.process-Bo5-Suyq.js:690`):

```js
const { dispatcher, ... } = createReplyDispatcherWithTyping({
  ...replyPipeline,                              // no silentReplyContext
  humanDelay: resolveHumanDelayConfig(cfg, route.agentId),
  deliver: async (payload, info) => { ... },
});
```

So `resolveSilentFinalPayload` (`dispatch-Bd9Vyd-o.js:960`) returns `undefined` and the rewrite path (which would replace `NO_REPLY` with a fallback like "Nothing to add right now.") is never reached for Discord channel finals. Setting only `rewrite=true` would make the agent emit `NO_REPLY` more confidently, then the runtime would still drop it via `normalizeReplyPayload`. Net result: worse, not better.

---

## Verification (no Discord typing required)

After restart, confirm both fixes are live with these one-liners:

```bash
# Fix #1 â€” visibleReplies
openclaw config get messages.groupChat.visibleReplies
# expect: automatic

# Fix #2 â€” silentReply.group
openclaw config get agents.defaults.silentReply.group
# expect: disallow
```

Verify the resolved silent-reply settings for a channel session directly:

```bash
node --input-type=module -e '
import("/usr/lib/node_modules/openclaw/dist/silent-reply-CuB457HX.js").then(({ n: resolveSilentReplySettings }) => {
  const cfg = JSON.parse(require("node:fs").readFileSync("/home/ubuntu/.openclaw/openclaw.json", "utf8"));
  const r = resolveSilentReplySettings({ cfg, sessionKey: "agent:main:discord:channel:<channel-id>", surface: "discord" });
  console.log("group policy:", r.policy, "rewrite:", r.rewrite, "(want: disallow / false)");
});
'
```

Expected:
```
group policy: disallow rewrite: false (want: disallow / false)
```

---

## Restart caveat

**Never `kill` the openclaw process from inside a Discord/WhatsApp/cron session.** You ARE that process. The kill aborts the in-flight reply, the typing indicator hangs, and the user sees "typingâ€¦" then silence. Do the restart from the main webchat/CLI session, or use the gateway tool's `restart` action.

In containers without systemd, `openclaw gateway restart` may be a no-op. Check supervisord (e.g. `/tmp/supervisord-openclaw.conf`) and use `kill <pid>` from a session **other than** the one being restarted; supervisord respawns it.

---

## Suggested upstream improvements

For OpenClaw maintainers, three changes would have prevented this from being a 6+ hour debug session:

### 1. Default `visibleReplies` to `"automatic"` for small servers

The current `"message_tool_only"` default is a footgun for single-user / small-team Discord setups where the bot is meant to behave like a conversational participant. Two options:

- Flip the default per-channel-type in `source-reply-delivery-mode-DahE29Wm.js:6` (e.g., only `"message_tool_only"` for Slack/Telegram large groups, `"automatic"` for Discord guilds under N members).
- Read it from the channel config (`channels.discord.visibleReplies`) so per-server tuning is possible.

### 2. Make the "mostly lurk" / `NO_REPLY` prompt block opt-in

Today there's no clean knob to remove the hardcoded `"Be a good group participant: mostly lurk"` line at `get-reply-CfL1pJQm.js:605`. `silentReply.group=disallow` only removes the `NO_REPLY` token instruction, not the lurk-bias. A `messages.groupChat.lurk` flag (default `true` for backward-compat) checked before adding line 605 would make this fully configurable.

### 3. Surface dispatcher-level reply suppression at `info` level

Today silenced replies are logged at `logVerbose` only:

```js
if (suppressDelivery)
  logVerbose(`Delivery suppressed by ${deliverySuppressionReason} for session ...`);
```

Change to `info` level (at least once per session) with a one-line hint pointing at the relevant config key. The fact that this is silent at info level is what made it take source-reading to find. **Loud diagnostics on intentional drops > silent drops.**

---

## Files referenced (all read-only inspection)

- `/usr/lib/node_modules/openclaw/dist/source-reply-delivery-mode-DahE29Wm.js:6`
- `/usr/lib/node_modules/openclaw/dist/dispatch-Bd9Vyd-o.js:619, 636, 960, 1020, 1131`
- `/usr/lib/node_modules/openclaw/dist/silent-reply-CuB457HX.js:3-7, 52-58`
- `/usr/lib/node_modules/openclaw/dist/get-reply-CfL1pJQm.js:605-616, 1986-2052`
- `/usr/lib/node_modules/openclaw/dist/normalize-reply-VyVCke1Q.js:21-26`
- `/usr/lib/node_modules/openclaw/dist/extensions/discord/message-handler.process-Bo5-Suyq.js:235, 485, 690`
- `/usr/lib/node_modules/openclaw/dist/extensions/discord/provider-Dy4gmGhl.js:7028`
- `/usr/lib/node_modules/openclaw/dist/extensions/discord/reply-delivery-CzRSSCl3.js:66`
- `/usr/lib/node_modules/openclaw/dist/deliver-83pBIoxY.js:486`
- `/usr/lib/node_modules/openclaw/dist/runtime-schema-CjQQFitv.js:25418` (schema/help text)

---

## Investigation history

This bug took ~6.5 hours of debugging across two sessions on 2026-05-02 â†’ 2026-05-03 before both root causes were isolated. Initial symptoms looked like:

1. A network/intent issue (Discord Developer Portal Message Content Intent) â€” **wrong**; that intent is hardcoded ON in `provider-Dy4gmGhl.js`.
2. Anthropic API credit exhaustion â€” **wrong**; verified live with a test call.
3. A channel-allowlist or mention-required gate â€” **wrong**; preflight let messages through.
4. The dispatcher's `suppressDelivery` flag (Bug #1) â€” **partially right**; fixed `#general` but not cold channels.
5. A second runtime gate filtering cold channels â€” **wrong**; no such gate exists. The agent is choosing to emit `NO_REPLY` (Bug #2).

The two-config-flip fix is reproducible and minimal. Both knobs exist today in OpenClaw's schema â€” they're just hidden behind the `advanced` tag and the wrong defaults for small servers.

---

*Written 2026-05-04 after both fixes were verified live in production. OpenClaw runtime version captured at `/usr/lib/node_modules/openclaw/package.json`.*
