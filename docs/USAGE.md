# Use Delivery Shelf

Delivery Shelf saves selected file deliveries, their metadata, and preserved versions. This guide covers native Desktop workflows first. Chat and Telegram have their own [command reference](COMMANDS.md).

## On this page

- [Choose a save workflow](#choose-a-save-workflow)
- [Save the latest handoff](#save-the-latest-handoff)
- [Choose files manually](#choose-files-manually)
- [Generate metadata](#generate-metadata)
- [Browse deliveries and files](#browse-deliveries-and-files)
- [Inspect, preview, and download](#inspect-preview-and-download)
- [Save another version](#save-another-version)
- [Manage version approval](#manage-version-approval)
- [Manage deliveries and recovery](#manage-deliveries-and-recovery)
- [Set preferences](#set-preferences)
- [File policy and limits](#file-policy-and-limits)
- [Storage and privacy](#storage-and-privacy)
- [Troubleshoot a workflow](#troubleshoot-a-workflow)

## Choose a save workflow

| Your goal | Use |
| --- | --- |
| Keep the latest recognized file handoff in this conversation | `/shelf add` |
| Keep only the newest recognized file | `/shelf add r1` |
| Choose files and review metadata before saving | Native Desktop **Add delivery** |
| Save a revised edition of a known delivery | **Add version**, or approve its exact version offer |
| Keep a conversation reference rather than files | Conversation Bookmarks |

A **delivery** is the saved collection. A **file** is an attachment within it. A **version** is a preserved edition of that delivery's files. Cleanup selection acts on whole deliveries, not individual file rows.

## Save the latest handoff

1. In the conversation that received the files, enter `/shelf add`.
2. Wait for the saved or already-saved confirmation.
3. Open **Saved → Deliverables** to find the delivery.

The command saves the newest recognized handoff as one set, up to eight explicit file references. It does not search your folders. Recent-command discovery reads standalone `MEDIA:` references in eligible assistant replies within the active conversation segment. A filename mentioned in prose is not enough, and older compressed-away deliveries may not be found.

To take only the newest file, use `/shelf add r1`. For the newest three files across the bounded recent replies, use `/shelf add r3`. Here `r3` is a **file count**. Within one reply, the last `MEDIA:` reference counts as newest. An insufficient count fails without saving a smaller substitute set.

Supplied metadata takes precedence:

```text
/shelf add Launch handoff #launch, approved --description "Approved report and charts."
```

With metadata generation enabled, missing fields are generated before the save. If generation fails, the command reports failure rather than silently registering a placeholder. When generation is disabled, quick capture uses the filename as a starting title and leaves omitted descriptive fields empty.

If the primary file already has an exact registration, quick capture returns that delivery rather than overwriting its metadata. A different companion set requires an explicit **Add version** decision. A file changed at the same source path is not a request to overwrite its saved edition.

Automatic command capture depends on host lifecycle support. If your host refuses it, use manual **Add delivery** and explicit **Save**. Do not weaken plugin isolation to bypass a refusal.

## Choose files manually

In native Desktop:

1. Open **Saved → Deliverables → Add delivery**, or use **Plus → Delivery Shelf**.
2. Choose a conversation. Use the search beneath the conversation control to narrow recent choices.
3. Select the delivered files you want to keep. Use the file search to narrow the selected conversation's files.
4. Enter the title, description, tags, kind, and project.
5. Select **Save**.

A delivery can contain up to 32 files. Selections remain when you change file pages. **Select all files on this page** affects that page, not all files in the conversation. **Clear selection** removes the file selection without rewriting the metadata.

Thumbnails help identify supported images and document previews. A file-type icon is a normal fallback, not evidence that the file failed to save.

The native chooser retains its draft while dismissed within the same client scope. Changing connection, profile, or source can require a fresh source choice. Do not treat an unsaved draft as durable storage.

The web Dashboard has its own collection and editor. It is not the native Desktop Together, Library, and Gallery interface. Use the controls visible in that host, or use native Desktop for the multi-file workflow described here.

## Generate metadata

Generation is optional. You can write all details yourself.

In the native Add form, choose files, enter any fields you want to preserve, and select **Generate**. Review the result before selecting **Save**. Typed metadata is preserved; generation fills missing fields. For a multi-file manual selection, this draft uses the first selected file and its anchored history, not a combined reading of every companion file.

The context control offers 5, 10, 20, or 50 previous exchanges, with 10 as the default. The native settings page calls this preference **Context messages**. Context ends at the selected delivery response rather than continuing into later conversation.

Generation uses a bounded input, not unrestricted document analysis. Depending on format and provider support, the input can contain text, image content, supported document content, or history-only context. A history-only draft is not a claim that the model read the file. ZIP attachments are not extracted for generation.

A model timeout, invalid response, source change, or profile change can reject generation. Keep your draft, correct the source if necessary, and retry, or enter details manually. Generating is never a save by itself.

## Browse deliveries and files

Open **Saved → Deliverables** in native Desktop.

- **Together** groups each delivery with its current companion files. Collapse a group to shorten the list.
- **Library** shows a compact file list and an adjacent inspector. Choose a row to inspect without leaving the collection.
- **Gallery** shows file cards with thumbnails or type icons and a link to their delivery.

Search titles and descriptions. Narrow by kind or exact project. Tags are also available to the catalog search tools and advanced queries. The native toolbar does not promise a full-text search inside files.

All three views refer to the same saved deliveries. A delivery with several files may appear as several file rows or cards, but it remains one delivery for selection and cleanup.

Checking a row or card selects its **entire delivery**. Choosing its title or preview opens it. The selection toolbar distinguishes **This page** from **All matching deliveries**. The latter applies the current filters across pages; review the scope before a bulk action.

## Inspect, preview, and download

Open delivery details to view metadata, files, and versions. Choose **Open file & history** from Library's inspector to reach the same detail workflow.

For a preserved delivery:

1. Choose the version you want.
2. Choose a file if the version contains more than one.
3. Preview supported content or select **Download** for that file and version.

Text, Markdown, and CSV previews show bounded plain text. Markdown is not executed as HTML. Text previews are limited to 64 KiB; download the file for its full contents.

Image and document thumbnails are raster previews. Unsupported documents or unavailable renderers retain a type icon. Shelf does not embed an editable Office document or execute an attachment.

Source details show the original path and conversation association when available. The originating conversation may be missing even when the preserved file is still available. A legacy **Original-file link** differs: it still requires its source file until a preserved version exists.

Managed downloads validate the saved size and content hash. If validation fails, Shelf reports the failure rather than substituting bytes from the original path.

## Save another version

1. Open an **Active** delivery's details.
2. Choose **Add version**.
3. Select the exact files that make up the new edition.
4. Select **Save new version**.
5. Use the version selector to inspect or download the previous edition.

The manually selected set defines the new version. If the new edition still needs companion files, include them in that set. Earlier versions retain their files.

An agent's approved single-file replacement can preserve the other saved companions without rereading their original working paths. In a multi-file delivery, a new path must identify the exact saved member it replaces. If that association is unknown, clarify it rather than relying on a similar filename.

Restore an archived or trashed delivery to Active before adding a version. Editing only the title, description, tags, kind, or project is a metadata edit, not a new file version.

## Manage version approval

A first save always requires a deliberate save request. Subsequent versions of that **known saved delivery** can use a concrete version offer:

| Response | Effect |
| --- | --- |
| **Yes** | Save the offered version. |
| **Always for this delivery** | Save it and authorize later concrete versions of that delivery for the approving owner. |
| **Keep current** | Leave the saved delivery unchanged. |

An offer is not a save. It refers to exact new file bytes, a saved delivery, and a revision. An expired offer or a changed file needs a fresh offer.

The details view and Library inspector show the delivery's current approval state. Select **Ask before next version** to revoke existing standing approval. There is no global auto-save preference, and the settings page cannot grant **Always**.

Version updates pause while the delivery is outside Active. Restoring it can resume an existing standing permission; revoke that permission if you want the next version to ask again. Unchanged bytes do not need another version offer.

## Manage deliveries and recovery

Use checkboxes to choose deliveries, then choose the cleanup action. File rows belonging to the same delivery refer to the same selection.

| State | What it means | How to return |
| --- | --- | --- |
| **Active** | Normal browsing and version updates. | Already active. |
| **Archive** | Kept indefinitely, outside the active collection. | Select and restore. |
| **Trash** | Recoverable until its 30- or 60-day deadline. | Restore before the deadline. |
| **Pending deletion** | Empty Trash has started a 60-minute recovery window. | Restore before that deadline. |

**Archive selected** is useful for completed projects. The confirmation offers **Undo archive** for the affected deliveries.

**Trash selected** applies to the selected deliveries, including their preserved versions. It does not delete the original working files.

**Empty Trash applies to all deliveries in Trash**, even if your current search shows fewer items or only some are checked. The confirmation states this scope. It moves Trash to Pending deletion; it does not immediately delete the preserved copies.

After the recovery deadline, due-item cleanup can permanently remove the catalog entries and managed copies. Cleanup runs when the backend is active and automatic cleanup is enabled, or when you request cleanup. Do not rely on a stopped backend or a disabled cleanup switch to extend recovery: restoration is rejected once the recorded deadline passes.

Changing Trash retention applies to existing Trash entries, based on their original trash date. Reducing retention can make older items due immediately. It does not change the separate Pending deletion window.

## Set preferences

Open the native plugin settings page for **Delivery Shelf**.

| Preference | Options or scope |
| --- | --- |
| Enabled browsing views | Together, Library, Gallery; at least one remains enabled. |
| Default view | One of the enabled views. |
| Timezone | `auto` for this device, or an IANA name such as `Europe/London`. |
| Date format | Short, medium, long, or `YYYY-MM-DD`. |
| Hour display | Device default, 12-hour, or 24-hour. |
| Generate metadata by default | Applies to missing metadata during quick capture. |
| Context messages | 5, 10, 20, or 50. |
| Trash retention | 30 or 60 days, including existing Trash. |
| Automatic due-item cleanup | Schedules eligible cleanup while the backend is running. |

Select **Save settings** to persist changes. **Clean up due items now** explicitly runs due-item cleanup even when automatic scheduling is off.

Storage usage counts Shelf's preserved files across saved versions and lifecycle states, including queued purges. It excludes original working files, the database, and preview caches. It is not a measurement of total profile disk usage.

## File policy and limits

Attachments must pass the operator's approved-root policy and safe-file checks. Supported extensions are:

```text
.txt .md .csv .pdf .docx .pptx .xlsx
.png .jpg .jpeg .webp .gif .zip
```

Each file is limited to **10 MiB**. Manual deliveries and versions accept up to **32 files**; recent-command selectors accept **1–8**.

Hidden paths, traversal components, symlinks, non-ordinary linked files, and sensitive filenames are refused. An allowed extension is not a guarantee that arbitrary content is safe. ZIP files remain opaque attachments and are never unpacked by Shelf.

The defaults expose only the profile's `workspaces` and `workspace` roots. Operators can set aliases in `plugin-data/delivery-shelf/allowed-roots.json` beneath the selected Hermes home. A custom policy replaces those defaults. Do not approve your entire home directory to work around one refused file.

Safe file access requires backend filesystem primitives such as `dir_fd` and `O_NOFOLLOW`. A native Desktop client on Windows can use a supported remote backend; that is different from claiming equivalent file-preservation support on every Windows backend.

## Storage and privacy

Data lives beneath the active Hermes home:

```text
plugin-data/delivery-shelf/
```

The directory contains `shelf.sqlite3`, managed file versions, policies, and supporting plugin state. Back up the whole directory consistently if you want to preserve the saved collection. Copying only the catalog does not back up the files.

Shelf reads selected source references and bounded conversation context when a save, chooser, or generation operation needs them. It does not sweep folders for future saves. Search operates on saved metadata rather than indexing file contents.

Explicit generation uses Hermes's configured model/provider and its data policy. Advanced agent-assisted commands use the current agent context instead. Neither workflow creates a separate Shelf model account or remote index.

Ordinary updates and package removal do not mean data erasure. Preserve or remove plugin data deliberately. There is no special protection from other software running under the same operating-system account, and Shelf does not encrypt its catalog or managed files.

## Troubleshoot a workflow

| Symptom | Next step |
| --- | --- |
| No recent file found | Use manual Add or ask Hermes to save the exact delivered file. Do not substitute a guessed path. |
| A file is refused | Check its size, extension, ordinary-file status, and approved root. |
| Automatic Add is unsupported | Use manual Add and explicit Save. Keep isolation settings unchanged. |
| Generate fails | Enter metadata manually, or check the Agent runtime, model support, and source availability. |
| Already saved | Inspect the existing delivery. Use Add version for a new edition, not another first save. |
| Delivery changed elsewhere | Refresh before editing or adding a version. |
| Source missing | Download the preserved version if present. Legacy source links still need the original. |
| Saved file failed integrity validation | Preserve the error and check storage or a known-good backup. Do not overwrite the saved file to hide the mismatch. |
| Telegram controls absent | Check native transport, operator owner policy, and the host's plugin lifecycle. |
| Delivery is missing from Active | Check Archive, Trash, and Pending deletion in the same profile. |

For installation and component availability, use [Installation](INSTALLATION.md). For a bug report, include the host, plugin version, workflow, and sanitized error. Keep private paths, titles, and conversation content out of public issues. Send security reports through [SECURITY.md](../SECURITY.md), with **repobugs@virtuedev.com** as the private fallback.
