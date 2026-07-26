# Cloudinary asset storage

The API, not the client, derives every Cloudinary folder from the authenticated
account and database entities. Upload requests accept multipart files and
entity IDs only. Cloudinary dynamic folders are created on first upload; the
application never creates empty folders.

## Folder mapping

| Category | Asset folder | Public ID |
|---|---|---|
| `USER_PROFILE_IMAGE` | `teachalike/{user_id}/Image/Profile` | `{asset_folder}/profile` |
| `CHILD_PROFILE_IMAGE` | `teachalike/{user_id}/Image/Children_profile/{child_id}_{child_name}` | `{asset_folder}/profile` |
| `VOICE_PROFILE` | `teachalike/{user_id}/Audio/Voice_profiles` | `voice_profile_{voice_profile_id}` |
| `GENERATED_BOOK_AUDIO` | `teachalike/{user_id}/Audio/Generated_Books_Audio/{book_id}_{book_name}` | `voice_{voice_profile_id}_{book_id}_{generation_id}` |
| `BOOK_VIDEO` | `teachalike/{user_id}/Video/{admin_id}/{book_id}_{book_name}` | a unique sanitized upload identifier |

Profile public IDs include the trusted asset-folder prefix because Cloudinary
public IDs are account-wide even in dynamic-folder mode. The filename remains
the deterministic `profile`.

Voice samples and generated narration audio use Cloudinary's authenticated
delivery type. Profile images and catalog videos use normal public delivery.

## Endpoints

All endpoints require a JWT. Responses use
`{"success": true, "message": "...", "data": ...}`; errors use the same shape
with `success: false`.

- `POST /api/assets/profile-image` — image in `file` or `profile_image`.
- `POST /api/assets/children/{child_id}/profile-image` — managed child image.
- `POST /api/assets/voice-profiles` — audio in `file` or `audio`; optional `label`.
- `POST /api/assets/books/{book_id}/narrations` — audio plus `voice_profile_id`.
- `POST /api/admin/books/{book_id}/videos` — admin-only video.
- `GET|DELETE /api/assets/{asset_id}` — owner/admin metadata read or exact deletion.
- `GET /api/books/{book_id}/assets` — caller-visible assets for a book.
- `GET /api/users/me/assets` — current account's active assets.

Unsupported media returns 415, size violations 413, authorization failures
403, missing entities 404, and business-rule failures 422.

## Persistence and failure handling

Deterministic replacement history can share both a public ID and Cloudinary's
immutable logical asset ID, so version rows do not apply uniqueness to either
field. `active_slot` is an internal nullable unique key used only for singleton
profile assets; soft-deleted rows set it to NULL. Upload metadata is committed
only after Cloudinary succeeds. A failed initial database commit triggers
exact-asset cleanup. Overwrites request CDN invalidation. Cloudinary deletion
is idempotent (`not found` is success), and the database row is soft-deleted
only after the upstream response resolves. Failed cleanup of an older replaced
profile is retained as `cleanup_failed`, so an exact-ID retry or account
cleanup can safely retry it.

Apply `migrations/20260726_add_assets.sql` to existing MySQL deployments.
Fresh local databases are also supported by the app's existing
`db.create_all()` startup convention.
