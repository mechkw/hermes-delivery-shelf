# Setup and everyday operation

[← README](../README.md) · [Technical guide](TECHNICAL.md)

## Install and enable

```sh
hermes plugins install mechkw/hermes-delivery-shelf --enable
hermes plugins list
```

This installs from the public Git repository. It is not a claim of inclusion in the
Hermes plugin catalog. Hermes can ask for dependency or capability consent during
installation. The repository name is `hermes-delivery-shelf`; the installed plugin
ID is **`delivery-shelf`**.

If a Dashboard server was already running, restart that server so its Python backend
can mount the new routes, then refresh the page. In Desktop, rescan through
**Capabilities → Plugins** and check both Agent and Desktop enablement. The current
Hermes installer manages the unified package; you do not need to compile JavaScript.

## Remote Desktop setups

A Desktop app and its connected backend can run on different computers. Installing
backend Python code on a server does not automatically put a UI on your laptop.

1. Install and enable the plugin on the backend that owns the catalog and files.
2. Install the same package on the computer running Desktop, so its Desktop half
   is available to the app. Rescan plugins there.
3. Connect Desktop to the intended backend and profile.
4. Open Delivery Shelf and verify that the displayed profile is the one you intended.

The Dashboard runs beside its backend, so its UI and backend package share the same
installation. A responsive Dashboard page is the mobile view; this project does not
install a native Android or iOS application.

Keep your existing Hermes authentication. The plugin does not create a public file
server or require new inbound ports.

## Attach a file

File references contain a **root alias** and a **relative path**, not an arbitrary
absolute path supplied by a browser.

The default aliases are:

- `workspace` → the active Hermes home's `workspace/` directory.
- `workspaces` → the active Hermes home's `workspaces/` directory.

For example, a report saved in `$HERMES_HOME/workspace/launch/report.pdf` can use:

```json
{
  "title": "Spring launch report",
  "kind": "report",
  "project": "Website",
  "tags": ["launch", "final"],
  "file": {"root": "workspace", "path": "launch/report.pdf"}
}
```

The file must already exist. A card without an attachment can omit `file` entirely.
The plugin does not recursively list or discover files in an approved directory.

### Approve another root

An operator can create this file under the **intended profile's** Hermes home:

```text
plugin-data/delivery-shelf/allowed-roots.json
```

Its contents map aliases to absolute paths on the backend machine:

```json
{
  "deliveries": "/srv/my-project/deliveries"
}
```

This example path is illustrative: replace it with your real, narrowly scoped delivery
directory. An explicit policy replaces the defaults. Use `{}` to allow metadata-only
operation with no file roots. Keep this operator-owned file private; it cannot be
edited through the plugin's browser API. A malformed policy fails closed.

Avoid approving a home directory, a credentials directory, or the filesystem root.
The plugin rejects the filesystem root outright. File-name exclusions are an extra
safeguard, not a secret-detection service: operators remain responsible for the contents
of approved roots.

### File limits

Supported attachment extensions: `.txt`, `.md`, `.csv`, `.pdf`, `.png`, `.jpg`,
`.jpeg`, `.webp`, and `.gif`. Only text, Markdown, and CSV have inline plain-text
previews. Binary files are downloads, not active embedded documents. HTML, SVG,
executables, databases, dotfiles, unsafe path segments, and obvious sensitive filenames
are not downloadable.

The maximum download is **10 MiB**. Text preview reads at most **64 KiB** and marks
longer content as truncated. Symlinks—including symlink ancestors of the approved
root—and hard-linked files are rejected. Safe file delivery requires POSIX descriptor
operations; where those primitives are unavailable, the metadata catalog remains
usable but file access refuses rather than weakening the check.

Files are read from their current location on each request. Changing a file's contents
changes what a later download retrieves; registering a file does not freeze or copy it.

## Edit or remove an entry

Use the shelf's edit controls to change metadata. Saving carries the revision you
loaded. If another client changed the entry, refresh before editing again; the plugin
will not silently replace their newer version.

Removal deletes only the catalog entry. It does not remove the attached file, its
folder, or any source conversation. You can edit or remove a card whose attachment
has become unavailable.

## Storage and retention

The catalog is stored on the backend under:

```text
$HERMES_HOME/plugin-data/delivery-shelf/shelf.sqlite3
```

The default profile commonly uses `~/.hermes`; named profiles have their own homes.
The request's host-bound profile selects the catalog. Supplying another profile name
in a URL is not permission to read it.

No automatic expiration is applied. Normal plugin updates or removal leave the catalog
in place. Exporting, copying, or backing up this database can expose titles, notes,
tags, and registered file references; treat it as private data.

For a consistent backup, stop clients that can change the catalog or use SQLite's
backup API. Do not assume copying a live SQLite main file alone captures all activity.
To erase the catalog, first remove entries through the UI or stop/disable the plugin,
then deliberately remove its **own** data directory. Never remove a broader
`plugin-data/` directory, native `state.db`, or source files as a shortcut.

## Update, disable, or remove

```sh
hermes plugins update delivery-shelf
hermes plugins disable delivery-shelf
hermes plugins remove delivery-shelf
```

Verify the desired state in `hermes plugins list` and Desktop's plugin controls.
Restart a running backend after Python changes. Rescan Desktop after package updates;
an already-copied frontend can otherwise remain stale. Removal is not data erasure.

## Troubleshooting

### The page is missing

Check that the package is installed on the correct machine, both relevant plugin
halves are enabled, and the Dashboard backend has restarted since installation.
Rescan Desktop plugins. A server installation and a local Desktop installation are
not interchangeable.

### The page loads, but API requests return 404

The frontend may be present while the backend is absent or disabled. Verify the
connected host, active profile, installed plugin ID, and backend enablement. Do not
work around this by exposing a standalone unauthenticated API.

### A profile mismatch is reported

Reconnect or reload against the intended profile. The plugin refuses an unbound or
mismatching profile hint rather than silently returning the backend's launch profile.

### An attachment is unavailable

Check the current approved root, relative path, extension, file size, and whether any
path segment is a symlink. A moved file does not follow its shelf entry automatically.
Update its reference, or keep the entry as metadata only.

### Saving reports that the delivery changed elsewhere

Another client saved a newer revision. Refresh, review the current values, and apply
your change again. This is an intentional lost-update safeguard.

### I uninstalled it, but my entries returned after reinstalling

Plugin data is retained separately from package code. This protects your collection
during updates and removal. See [storage and retention](#storage-and-retention) for
explicit erasure.

If none of these resolves the issue, [open a bug report](https://github.com/mechkw/hermes-delivery-shelf/issues/new/choose)
with versions and a fictional reproduction. Keep private file paths and contents out
of public reports.
