# Conversation Add and automatic metadata

[Commands](COMMANDS.md) · [Operations](OPERATIONS.md) · [Telegram](TELEGRAM.md)

The historical filename remains for existing links. Ordinary Add can call the configured model. Model-free retrieval, an exact-reference duplicate in quick capture, a fully supplied save, and generation-disabled quick capture are different paths.

## Typed quick capture

| Form | Saved selection |
| --- | --- |
| `/shelf add` | Newest recognized delivery set, up to eight files, as one delivery. |
| `/shelf add r1` | Newest single recognized file. |
| `/shelf add rN` | Newest N distinct recognized files, with N from 1 through 8. |

Count selectors run across the bounded recent eligible replies. Within a reply, the last `MEDIA:` reference is newest for counting. An insufficient count fails without saving a smaller set. The first selected reference is the delivery's primary file.

Quick capture uses supplied title, tags, and description unchanged. When generation is enabled, it fills omitted fields before the managed-copy save. Multi-file capture can generate one draft per selected file, then combine descriptive metadata into one delivery. When generation is disabled, filename-based metadata is used for omitted fields. Generation failure does not silently save a placeholder.

An exact existing primary reference returns its registration without replacing edited metadata or saved versions. A different companion set requires an explicit version decision. This duplicate handling is specific to quick Add; general create requests are not idempotent.

## Manual and panel selection

Native Desktop **Add delivery** provides a searchable conversation/file chooser, up to 32 selected files, optional **Generate**, and separate **Save**. Manual generation uses the first selected file; it does not claim to read every companion.

Telegram's panel **Add** is a separate chooser workflow. One candidate can save directly. Several candidates offer individual files and **Save all**. Its missing-metadata generation is separate from typed quick capture. Do not infer that every panel path shares quick capture's generation-default preference or duplicate inference suppression.

Advanced `--file` commands select one exact approved-root reference. Missing metadata uses the current-agent handoff, not the structured quick-capture collector. Fully supplied advanced saves are direct. See [Commands](COMMANDS.md#choose-an-explicit-file).

## Source boundary

`recent_artifacts.recent()` is a plugin-owned native-schema adapter, not a public host artifact registry. It opens the exact profile's native `state.db` read-only with query-only mode, schema checks, and bounded query work.

Discovery reads at most 40 eligible assistant responses, each at most 64 KiB, in the exact invoking active session segment. It excludes tool-calling, observed, display-only, and compressed-summary rows. A newer oversized response stops lookup rather than selecting an older handoff.

Only standalone absolute local `MEDIA:` markers outside code fences are recognized, including supported native JSON text blocks. Prose paths, Markdown links, URLs, tool outputs, and inferred filenames are not quick-capture candidates. Every selected member must pass approved-root and file policy. An invalid member does not redirect the save to a different delivery.

Discovery does not traverse folders, other sessions, or compression ancestry to recover a delivery. Manual selection or an explicit known reference is needed for old-window, pruned, ancestor-only, or non-marker sources. A marker establishes an assistant file reference, not a Telegram delivery receipt. Reply-to-message discovery is not advertised.

Generation has its own bounded source resolver and anchored-history collector. Finding an eligible marker does not guarantee generation can resolve the required history. The native model service receives bounded file input and eligible context at or before the selected response. Content mode reports history-only input when the file is not read for inference.

## Lifecycle and execution limits

Commands need the host's exact current session, supported profile binding, and lifecycle. Telegram also needs its owner policy and transport. Worker paths recheck profile, session, lifecycle, source identity, and file identity before completion. A commit authorized before cancellation may still finish. A failed confirmation is not rollback; inspect Saved before repeating a request.

The native text-Add preparation path refuses automatic capture when `HERMES_PLUGIN_HOST_PROCESS=1`, before its source discovery or metadata inference. The refusal directs you to manual Add, optional draft generation, and explicit Save. This source-level guard is not proof of deployed cancellation behavior: qualify it against the exact packaged runtime. Keep isolation and permission settings unchanged.

## Verification boundary

Source inspection and parser checks establish syntax and branch intent only. They do not prove typed native dispatch, cancellation, installed persistence, model adherence, or live Telegram delivery. Release verification must exercise the exact package, including old/new saved-byte downloads and an independent check of typed quick capture versus panel selection.
