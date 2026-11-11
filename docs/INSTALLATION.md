# Install Delivery Shelf

[README](../README.md) · [Usage](USAGE.md) · [Commands](COMMANDS.md)

## Choose the host

| Host | Install |
| --- | --- |
| Native Hermes Desktop | The Desktop component on the app computer and Agent component on the selected backend/profile. |
| Web Dashboard | The backend package, including its Dashboard bundle. |
| CLI, TUI, or messaging gateway | The backend package for commands and tools; native Telegram panels also need host support and owner policy. |
| Browser-hosted Desktop | Do not assume it loads external native Desktop plugins. Use a compatible native client or the web Dashboard for this UI. |

Use a current Hermes release that supports the plugin's declared contributions. Different hosts expose different controls. Native Desktop's Together, Library, Gallery, adjacent inspector, and plugin-settings page are not claims about identical Dashboard presentation.

## Install in native Desktop

1. Open **Capabilities → Plugins → Install from Git**.
2. Enter `https://github.com/mechkw/hermes-delivery-shelf`.
3. Select the intended backend and profile.
4. Review source, dependency, and permission prompts.
5. Check that both **Agent** and **Desktop** are enabled for their intended scopes.
6. Open **Saved → Deliverables**.

The Desktop component belongs to the app computer. The Agent component and catalog belong to the selected backend profile. If the client connects to a remote backend, both locations matter.

If the backend is already installed but the Desktop half is missing, use the app's supported Git installation flow. Do not create an unmarked manual `plugin.js` copy or assume a server-side Rescan can install client files.

## Install on the backend

On the intended Hermes backend:

```sh
hermes plugins install mechkw/hermes-delivery-shelf --enable
hermes plugins list
```

Review normal dependency and capability consent. If installation is noninteractive and permissions or dependencies are declined, the package can be present without every feature being active. Read the activation result rather than assuming `--enable` grants everything.

For another profile, use Hermes's profile selection with the same commands. Plugin data and enablement are profile-scoped.

Open the authenticated web Dashboard and its **Saved → Deliverables** collection. Follow the host's supported reload or activation path if new routes or commands are not yet loaded. A rescan refreshes discovery; it does not necessarily replace a backend router already imported by a long-running server.

Do not restart a shared gateway or Desktop server in the middle of active work without coordinating that interruption.

## Configure Telegram ownership

Native Shelf panels and file sending require the host's Telegram handler support and a separate operator-owned policy:

```text
plugin-data/delivery-shelf/telegram-owners.json
```

Resolve that path beneath the selected Hermes home. The file contains a JSON array of approved **user ID strings**. Populate it from trusted identity information; do not use a group ID or copy every gateway-allowed user automatically. An absent or invalid policy denies native Shelf actions.

Gateway command access and Shelf owner policy are separate checks. Native buttons can also be unavailable under host isolation or an older plugin lifecycle. Preserve those protections and use the supported fallback; do not extract a bot token or disable isolation.

[Telegram commands and file sending](COMMANDS.md#retrieve-files-in-telegram).

## Configure file access

The default file-root aliases are `workspaces` and `workspace`, beneath the selected Hermes home. For other locations, the operator can provide:

```text
plugin-data/delivery-shelf/allowed-roots.json
```

The file maps root aliases to absolute directories. A custom policy replaces defaults. Approve only the directories needed for deliverables, not a whole home directory or credentials tree. Root policy is not writable through ordinary Shelf tools.

Supported file types, size limits, safe-path checks, and backend filesystem requirements are in [File policy and limits](USAGE.md#file-policy-and-limits).

## Check the installation

Use a fictional test delivery, not private client work:

1. Ask Hermes to create and explicitly deliver a small supported file.
2. Save it with `/shelf add` or manual Add.
3. Read the saved title and file in **Saved → Deliverables**.
4. Download the preserved copy and compare it with the source.
5. If testing cleanup, select only your test delivery and keep the source file separate.

A successful package install is not proof that commands, native buttons, generation, and file downloads all work. Check each surface you plan to use.

## Resolve common installation problems

| Symptom | Check |
| --- | --- |
| Plugin listed, but no Saved tab | Desktop component enabled locally, Agent enabled in the intended backend profile, and status request succeeds. |
| “Unavailable (remote backend)” | Both installation halves; a backend-only install cannot supply local Desktop files. |
| Existing package blocks installation | Inspect its provenance and enabled state. Use supported reinstall controls only if replacement is intended. |
| Generate unavailable | Agent runtime, auxiliary model access, provider capabilities, and source selection. Manual saving remains separate. |
| New backend route missing after rescan | Whether the owning server loaded the new code. Coordinate a supported reload if needed. |
| Telegram list is text-only | Native factory support, owner policy, isolation, and actual host handler lifecycle. |

For continued problems, include Hermes version, plugin version, client type, backend operating system, and a sanitized error in the [issue tracker](https://github.com/mechkw/hermes-delivery-shelf/issues). Never attach a real catalog or transcript to a public report.

## Check a save after an interrupted confirmation

If a save reports an error after a connection or lifecycle interruption, open **Saved → Deliverables** before retrying. Search for the delivery, inspect its files, and download the preserved copy if you need to confirm its contents.

The contest candidate has a [known confirmation defect](https://github.com/mechkw/hermes-delivery-shelf/issues/2). Quick Add can report **“Delivery Shelf not saved”** when the command controller closes after the save has already completed. That message alone does not prove the transaction was rolled back. If the delivery is present, do not repeat the save merely because its confirmation failed.

This issue does not authorize bypassing profile checks or disabling plugin isolation. Manual **Add delivery → Save** remains the supported route where automatic capture is unavailable.

## Update or uninstall

Use Hermes's supported plugin update and uninstall controls. Keep package identity and profile selection intact. Back up `plugin-data/delivery-shelf/` consistently before a migration or manual data removal.

Uninstalling code is not erasing the catalog or preserved files. Removing the plugin's data directory is a separate destructive action. It also removes preserved versions and supporting state; do it only when that loss is intended.

Official references: [Hermes plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins) and [Desktop plugin SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk).
