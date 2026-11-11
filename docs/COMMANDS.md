# Delivery Shelf command reference

[Usage guide](USAGE.md) · [Installation](INSTALLATION.md)

## Browse and search

| Command | Meaning |
| --- | --- |
| `/shelf` | Browse saved deliveries. Native Desktop can open its local browsing UI; configured Telegram connections open an inline panel. Other command hosts return text. |
| `/shelf search <query>` | Search saved title and description metadata. |
| `/shelf <query>` | Search alias, except reserved command forms. |
| `/shelf help` | Show everyday commands without saving. |
| `/shelf help advanced` | Show explicit-file syntax and setup details. |

Use `/shelf search add` to search for the word `add`. A bare `/shelf` is not consent to save.

## Save recent files

```text
/shelf add
/shelf add r1
/shelf add r3
/shelf add Launch report #launch, final --description "Approved report."
```

| Form | Selection |
| --- | --- |
| `add` | Latest recognized delivery set in this conversation. |
| `add r1` | Newest single recognized file. |
| `add rN` | Newest N distinct files, with N from 1 through 8. |

The recent selector reads eligible assistant replies in the active segment, bounded to 40 replies of at most 64 KiB each. It recognizes standalone local `MEDIA:` references outside code fences. It does not search folders, infer filenames, or reconstruct older compressed-away handoffs. Within one reply, the last reference is newest for `rN` counting.

No count selector means the latest delivery set, not automatically one file. An insufficient count or refused file fails without silently selecting a smaller set.

Optional metadata syntax is:

```text
/shelf add [rN] [title] [#tag1, tag2] [--description "text"]
```

Place the count first and the quoted description last. A whitespace-delimited `#` starts the comma-separated tags. The Add command supplies consent to capture the selected set and generate missing details when enabled. It does not authorize later automatic first saves.

Source eligibility and approved-root checks still apply. On hosts without lifecycle support for safe automatic capture, use manual **Add delivery → Save**. Keep plugin isolation unchanged. A successful model call is not a saved confirmation.

## Choose an explicit file

For an exact safe file reference, advanced syntax is:

```text
/shelf add Launch report #launch, final --file workspaces:launch/report.pdf --description "Approved report."
```

The `root` is an operator-approved alias. The path is relative to that root. Quote the entire reference if it contains spaces:

```text
/shelf add Launch report #launch --file "workspaces:launch/Final report.pdf" --description "Approved report."
```

Use `--file` and `--description` at most once each. A root alias is not a filesystem search instruction.

With all metadata supplied, this path saves directly. Missing title, tags, or description use an opt-in current-agent handoff, unlike the structured generation used by recent Add. Gateway-assisted handoffs require:

```sh
hermes config set plugins.entries.delivery-shelf.allow_gateway_injection true
```

Run configuration commands for the intended profile. The plugin does not enable this permission itself. A handoff accepted into the agent queue is not proof that a save completed. Shared-group assisted explicit-file handoffs can be refused when owner identity cannot be preserved; supply all metadata or use the native chooser.

## Retrieve files in Telegram

Native file sending requires the host's Telegram transport and the operator owner policy. It does not call the model.

| Command or action | Meaning |
| --- | --- |
| `/shelf` → delivery → **Send file** | Send a saved attachment in this chat or topic. |
| **Versions** → version → file | Send the selected preserved edition. |
| `/shelf dl 1` | Send item 1 from the last acknowledged numbered result list. |
| `/shelf download 1` | Alias for `dl 1`. |
| `/shelf r1` | Send the primary attachment from the most recently saved delivery. |
| `/shelf r3` | Send the primary attachment from the third most recently saved delivery. |

Saved-delivery ordinals support `r1` through `r5`. They follow registration order, not last-edit order. They select **one delivery**, not a batch of that many deliveries. Metadata-only registrations also occupy an ordinal and cannot send a file; the command does not skip them and substitute another delivery. For a multi-file delivery, the ordinal shortcut sends its primary file. Choose the delivery's file actions to retrieve a companion file or another version.

A multi-file version may offer **Send all files** when its file count is within the native sending limit; larger versions require individual file choices.

Numbered list results expire after ten minutes and are bound to the requesting user, chat or topic, profile, and session. Open a fresh list after an expiry or source change. A plain-text fallback is not proof that numeric selection is available.

If a send reports an unconfirmed delivery, check the chat before retrying. A failed transport response can occur after a file has arrived.

## Save a version in Telegram

Open a delivery, choose **Add version**, select the recent files, and choose **Confirm new version**. Earlier versions remain available. This is a new edition of that saved delivery, not another unrelated first save.

Native menus are optional host capabilities. If buttons are absent, check transport registration, owner policy, plugin activation, and host lifecycle before assuming the command itself is unavailable. Never weaken isolation to make native buttons appear.

## Tools

| Tool | Purpose |
| --- | --- |
| `delivery_shelf_register` | Deliberately register metadata and optional safe attachments. |
| `delivery_shelf_search` | Search explicitly saved metadata. |
| `delivery_shelf_update` | Correct an existing delivery using its current revision. |
| `delivery_shelf_offer_update` | Offer exact new bytes for a known saved delivery. |
| `delivery_shelf_respond_update` | Apply the user's response to that exact offer. |

The assistant must preserve explicit metadata, use exact known references, and read back writes before confirming. It must not discover speculative version candidates by scanning folders or the entire catalog.

For tool schemas and backend routes, see [Technical reference](TECHNICAL.md). For host plugin-command discovery, consult the current [Hermes plugin documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins). A command can be registered even when a host's global help or Telegram command menu does not list it.
