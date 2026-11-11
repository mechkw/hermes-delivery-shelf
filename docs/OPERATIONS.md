# Operate Delivery Shelf

[README](../README.md) · [Installation](INSTALLATION.md) · [Usage](USAGE.md) · [Technical reference](TECHNICAL.md)

## Install on the intended host

Use the [installation guide](INSTALLATION.md) for native Desktop, web Dashboard, and remote component pairing. Check the connected backend and profile before saving. In native Desktop, open **Saved → Deliverables**. Installing backend Python code alone does not install a remote client's Desktop UI.

Do not expose a separate plugin server or disable Hermes authentication. Browser-hosted Desktop is not the web Dashboard and does not establish native plugin support.

## Save and retrieve a delivery

1. In the conversation that received files, run `/shelf add`.
2. Wait for the saved or already-saved confirmation.
3. Open **Saved → Deliverables**, then inspect the delivery and download a selected file/version.

Bare `/shelf` browses without saving. `/shelf add r1` saves the newest recognized file. `/shelf add r3` saves the newest three recognized files as one delivery. Missing metadata uses configured generation when enabled. No source discovery scans folders. See [command syntax](COMMANDS.md) and [recent-source limits](DETERMINISTIC_ADD.md).

If native automatic Add reports that it cannot propagate caller cancellation in an isolated plugin host, leave isolation unchanged and use manual Add.

For manual native capture, select **Add delivery**, choose the conversation and files, review metadata, then select **Save**. **Generate** only fills a draft. Use **Add version** for a known delivery's next edition; a metadata edit does not refresh same-path file bytes.

A legacy **Original-file link** still needs the original. A preserved version uses managed copies. Test an actual version download before relying on the collection as a record of delivered bytes.

## Approve another root

Only an operator should edit source-root policy. Narrow the scope to a delivery directory on the backend.

1. Resolve the intended profile's Hermes home.
2. Create or edit `plugin-data/delivery-shelf/allowed-roots.json` beneath that home.
3. Map aliases to absolute backend directories, using this fictional shape:

```json
{
  "deliveries": "/srv/example-project/deliveries"
}
```

4. Reload the collection's status and check the reported alias.
5. Save and download a fictional allowed file before using real deliverables.

An explicit policy replaces `workspace` and `workspaces` defaults. `{}` disables source roots. A malformed policy denies access. Do not approve the whole home, a credentials directory, or the filesystem root. Source policy does not scan file contents for secrets.

Files must be ordinary, safely opened files with allowed extensions, at most 10 MiB each. See [file policy](TECHNICAL.md#file-policy). A native Windows client with a supported remote backend is not proof of Windows-backend preservation support.

## Configure Telegram ownership

Use [Telegram setup](TELEGRAM.md) for the separate profile-local owner policy. Permission to receive Telegram traffic is not permission to manage Shelf. Shelf and Bookmarks use different owner-policy files.

Native attachments, numbered lists, and buttons need the host's Telegram lifecycle and transport. Check owner, chat/topic, session, and exact result before retrying an uncertain save or send. Never weaken isolation to make buttons appear.

## Manage version approval

First saves stay deliberate. For an exact offered version of a known saved delivery, **Yes** approves one version. **Always for this delivery** approves that version and later concrete versions of that entry for the approving owner. **Keep current** changes nothing.

To revoke standing consent:

1. Open delivery details or Library's inspector.
2. Check **New versions** and its paused state.
3. Select **Ask before next version**.
4. Confirm the status returns to **Ask first**.

There is no settings switch that grants Always. Updates pause outside Active, but restoring an entry can resume an existing grant. Revoke first if you want another question after restoration.

## Archive or clean up deliveries

Use delivery checkboxes for cleanup. The native toolbar distinguishes **This page** from **All matching deliveries**. File rows belonging to the same delivery do not become separate cleanup targets.

- Archive retains deliveries indefinitely. Restore to Active when needed.
- Trash is recoverable for 30 or 60 days, with 60 as the default.
- Empty Trash affects all Trash, not only a filtered or checked subset. It starts a 60-minute Pending deletion window.

Restore before the recorded deadline. Disabling **Automatic due-item cleanup** does not extend recovery and does not stop purge jobs already queued. **Clean up due items now** explicitly processes due items even with automatic scheduling off.

Changing **Trash retention** applies to existing Trash from its original trash timestamp. Reducing retention can make entries immediately due. Cleanup removes managed Shelf copies and their catalog records, never original working files.

## Back up or erase plugin data

For a restorable file collection, back up the whole `plugin-data/delivery-shelf/` directory beneath the bound Hermes home. The SQLite catalog alone does not contain managed file bytes or all scoped permission state.

1. Stop writers and cleanup for a coordinated snapshot, or use a backup procedure that coordinates SQLite and the managed-file tree.
2. Copy the whole plugin data directory to protected backup storage.
3. Test recovery in a disposable profile before trusting the backup.

Do not copy only a live main SQLite file and assume consistency. Treat original paths, source references, descriptions, policies, and saved file bytes as private data.

Package update or removal does not erase plugin data. For deliberate erasure, stop or disable clients and remove only this plugin's own data directory. Never remove native `state.db`, the broader `plugin-data/` tree, or original working directories as a shortcut.

## Update or disable the package

```sh
hermes plugins update delivery-shelf
hermes plugins disable delivery-shelf
hermes plugins remove delivery-shelf
hermes plugins list
```

Run commands in the intended profile. Check both Agent and Desktop state where relevant. Activate changed backend and frontend code through their normal host lifecycle. Obtain a restart decision before interrupting active work. A successful build or Rescan is not proof that both installed halves changed.

## Diagnose a failed operation

| Symptom | Action |
| --- | --- |
| UI absent or API 404 | Check backend, profile, package enablement, and native Desktop pairing. |
| Profile mismatch | Reconnect to the intended profile. Do not change a URL to select another home. |
| No recent file | Use manual Add or an explicit known file. Do not guess a replacement path. |
| Automatic Add refused | Use manual Add and explicit Save. Leave isolation unchanged. |
| Generation unavailable | Enter metadata manually and check supported Agent runtime/model registration. |
| Already saved | Inspect the existing delivery. Approve Add version for a new edition. |
| Revision conflict | Refresh the exact delivery and review its latest state before retry. |
| Managed-file integrity failure | Preserve the error and inspect storage or a known-good backup. Do not substitute original bytes. |
| Legacy source unavailable | Recover the original or deliberately save a new version from a known source. |
| Send unconfirmed | Inspect the destination chat before another send. |
| Purge still queued | Keep the error and inspect backend storage access; turning scheduling off does not cancel the queue. |

Use fictional data in public reports. Send security reports through [SECURITY.md](../SECURITY.md), with **repobugs@virtuedev.com** as the private fallback.
