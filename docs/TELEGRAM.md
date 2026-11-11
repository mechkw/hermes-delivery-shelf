# Use Delivery Shelf in Telegram

[Commands](COMMANDS.md) · [Conversation Add](DETERMINISTIC_ADD.md) · [Security](../SECURITY.md)

## Authorize native panels

Shelf needs Hermes's connected Telegram transport and native plugin handler support. Its owner policy is separate from the gateway's allowed-user configuration and from Bookmarks' policy.

1. Resolve the intended backend profile's Hermes home.
2. Create `plugin-data/delivery-shelf/telegram-owners.json` beneath that home.
3. Store a JSON array of Telegram user IDs as decimal **strings**. This example is fictional:

```json
["123456789"]
```

4. Use `/shelf` from an authorized account in the intended chat or topic.
5. Confirm a native panel arrives before testing callbacks or numbered downloads.

The policy accepts at most 50 IDs. Missing, unreadable, unsafe, or malformed policy denies native access. Remove an ID to revoke its future interactions. The plugin rechecks policy rather than treating an old button as continuing authorization.

Do not expose plugin data, use real identifiers in public reports, disable authentication, or weaken isolation. A host that cannot own native Telegram handlers may lack panels and attachments. A text fallback is not proof of native button or numeric-download support.

## Browse without saving

Use `/shelf` for saved delivery rows and **Browse more** for another page. Use `/shelf search launch` to search saved titles and descriptions. Bare browsing is not save consent.

Select a delivery to view its description, tags, current files, and version actions. This uses the profile's saved catalog, not a private per-user collection inside a shared group. Panel text and sent files are visible to the destination chat's participants.

## Save recent files

Typed `/shelf add` saves the newest recognized file set as one delivery. `/shelf add r1` saves only the newest file. `/shelf add r3` saves the newest three recognized files, not the third saved delivery. Wait for the saved or already-saved response.

The panel's **Add** action is a deliberate chooser instead. One candidate can save directly; several candidates offer individual choices and **Save all**. Selecting a candidate can generate missing metadata before saving. It is not the same path as typed quick capture. See [Conversation Add](DETERMINISTIC_ADD.md) for generation and discovery limits.

An unavailable source, refused file, or uncertain save needs inspection, not a guessed replacement. An existing primary registration does not authorize overwriting its saved bytes or companion set.

## Send a saved file

1. Open `/shelf` and select a delivery.
2. Select **Send file**, or the named file action in a multi-file version.
3. Check the attachment in the same chat or topic.

For an earlier edition, select **Versions**, then a version and its file. **Send all files** is available for versions with two through five files. Larger versions require individual choices. Sending does not call the model.

| Shortcut | Meaning |
| --- | --- |
| `/shelf dl 1` | Send item 1 from the last acknowledged numbered list. |
| `/shelf download 1` | Alias for the same numbered result. |
| `/shelf r1` | Send the primary file of the newest registration. |
| `/shelf r3` | Send the primary file of the third newest registration. |

Saved ordinals support `r1` through `r5` and use creation order, not last-edit order. Metadata-only registrations occupy ordinals. The shortcut does not skip one or send three files for `r3`. It does not apply the Active browse filter, so use the explicit list when you need that filtered scope.

Numbered lists expire after ten minutes. A replaced page or changed revision can invalidate a selection. A plain-text fallback cannot establish an acknowledged numbered mapping. Open a new native list if numbers are unavailable.

Managed versions send preserved bytes. A genuine legacy original-file link still needs its source. A missing or corrupt managed copy is not replaced with bytes read from the original path.

If a send is unconfirmed, check the chat before repeating it. A failed response can occur after the attachment arrives. The plugin does not automatically retry an ambiguous attachment POST or continue the rest of that batch.

## Add a new version

1. Open the known saved delivery.
2. Select **Add version**.
3. Choose the exact recent files for the next edition.
4. Select **Confirm new version**.
5. Reopen **Versions** to inspect the saved edition.

The selected set defines the new version. Include required companions. Earlier versions remain available. An agent's exact single-member replacement can retain other managed companions; do not assume the manual full-set action does that for omitted files.

Conversational version offers use **Yes**, **Always for this delivery**, or **Keep current**. Always applies only to that deliberately saved entry and approving owner, never future first saves. Native delivery details and Library's inspector expose revocation through **Ask before next version**. Approval pauses outside Active.

## Treat buttons as scoped, temporary requests

Panels and numbered results are bound to the issuing owner, chat/topic, session, profile, message, and native application lifecycle. They expire after ten minutes. Reset, deletion, unload, connection replacement, or revoked ownership can invalidate them. Open a fresh panel instead of reusing stale callback bytes.

Buttons are armed only after the matching send or edit acknowledgement. Duplicate and stale callbacks are refused. These guards do not make SQLite and Telegram a distributed transaction. A save may commit before a confirmation fails.

## Qualify the installed transport

Native-loader and captured-transport tests are distinct from real Telegram acceptance. Validate owner denial, topic routing, expiry, reset, readback, and actual saved attachment bytes against the exact installed package. Neither source-inspected behavior nor a browser preview proves live delivery.
