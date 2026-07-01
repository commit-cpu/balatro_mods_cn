# Production Admin Security and Queue Design

## Goal

Prepare the Balatro CN web app for production use by protecting the admin workflow, improving mod management, adding controllable translation queueing, and making public status/link behavior accurate after fork publishing.

## Scope

This design covers the recommended production-ready version:

- Admin access through a configurable hidden suffix and secret key.
- Cookie-based authorization for admin pages and mutating workflow APIs.
- Admin views that make translated, truly translatable, review, queue, and fork-published mods easy to manage individually.
- A SQLite-backed translation queue with manual ordering.
- A lightweight in-process scheduler that can start one queued translation every configured interval, such as every 5 hours.
- Public mod list status/link corrections, including fork branch links.

This design does not add upstream PR creation, multi-worker distributed locking, user accounts, role-based permissions, or concurrent queue workers.

## Security Model

Two environment variables control admin access:

- `ADMIN_PATH_SUFFIX`: the private path suffix. If set to `cnops`, the admin page lives at `/cnops`.
- `ADMIN_SECRET_KEY`: the secret key accepted through the admin verification form.

When the secret key is correct, the server redirects back to the admin path and sets an HttpOnly cookie. Later admin navigation and protected API calls use that cookie. The secret key does not need to remain in the URL.

The public SPA routes stay available:

- `/`
- `/mods`
- `/about`
- `/static/*`

Public read-only APIs stay available:

- `/api/health`
- `/api/dashboard`
- `/api/mod-index`

Protected APIs require the admin cookie:

- `POST /api/github/probe`
- `POST /api/github/forks`
- `POST /api/github/localization-source`
- `POST /api/mods/{mod_id}/translate`
- `POST /api/mods/{mod_id}/apply-approved`
- `POST /api/mods/{mod_id}/publish-fork`
- Review mutation APIs.
- Queue and settings APIs.
- Job/event APIs, because payloads may reveal local paths or operational details.

If `ADMIN_SECRET_KEY` is unset, the app runs in development-open mode for local iteration. Production deployment should set both admin variables.

## Admin Routing

The existing `/admin` route should no longer expose the admin page in production. Behavior:

- If admin auth is disabled, `/admin` continues to work for development.
- If admin auth is enabled, `/admin` returns 404.
- `/{ADMIN_PATH_SUFFIX}` is the only production admin route.
- Before authorization, `/{ADMIN_PATH_SUFFIX}` shows a small `sk` form instead of the SPA.
- Client-side routing should detect custom admin paths as the admin page after the server has authorized it.

## Data Model

Add `app_settings` for server-editable operational settings:

- `key text primary key`
- `value_json text not null`
- `updated_at text not null default current_timestamp`

Initial settings:

- `auto_translate_enabled`: `false`
- `auto_translate_interval_hours`: `5`
- `last_auto_translate_at`: `null`

Add `translation_queue`:

- `id integer primary key`
- `mod_id text not null`
- `source_name text`
- `repo_url text`
- `priority integer not null default 1000`
- `status text not null default 'queued'`
- `locked_job_id integer`
- `last_error text`
- `created_at text not null default current_timestamp`
- `updated_at text not null default current_timestamp`
- `started_at text`
- `finished_at text`

Queue status values:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Only one active queue row per `mod_id` should be allowed for `queued` or `running`.

## Queue Behavior

Manual controls in admin:

- Add selected mod to queue.
- Start selected mod immediately.
- Move queued item up.
- Move queued item down.
- Remove queued item.
- Retry failed item.

When a queue item starts:

1. If the mod has no local source but has a GitHub repo URL, materialize localization source first.
2. Create a normal `translate_entry_loop` job.
3. Store `locked_job_id` on the queue row.
4. Poll the job until it leaves `pending/running`.
5. Mark the queue row `succeeded` or `failed`.

The scheduler is intentionally conservative:

- It runs inside the FastAPI process.
- It checks settings periodically.
- It starts at most one queued item per configured interval.
- It does not start a new item if any translation job or queue item is already running.
- It uses the same protected workflow functions as manual translation.

This keeps production behavior understandable and prevents accidental full-list translation bursts.

## Admin UI

The admin page should show a compact management surface with tabs or segmented filters:

- `待翻译`: no local complete AI translation and a usable GitHub/local source.
- `队列`: queued/running/failed items, ordered by priority.
- `翻译中`: active translation jobs.
- `待审核`: mods with pending or needs_changes review items.
- `已应用`: reviewed translation has been written to `zh_CN.lua` but not committed to fork.
- `已提交 Fork`: fork commit exists.
- `已合并`: upstream merge state, if known.

Each mod row should show:

- Display name.
- Local `mod_id` when available.
- Upstream localization status.
- AI workflow status.
- Review counts.
- Queue status.
- Fork slug.
- Latest fork branch/commit when available.
- Direct action buttons appropriate to the current state.

The existing review group UI can remain below this management surface. The workflow dropdown should still exist, but the new filtered views should become the primary way to manage individual mods.

## Status Semantics

Public list columns should avoid mixing upstream and fork state:

- `当前汉化状态`: upstream/original repository localization coverage from probe results.
- `AI 翻译状态`: this system's translation lifecycle, including review and fork commit.
- `流程`: next operational action in this system.

After `publish-fork` succeeds:

- `pull_requests.state` remains `fork_committed`.
- `mod_workflows.workflow_status` becomes `committed`.
- `mod_workflows.next_action` becomes `pr`.
- Public AI status should read as completed by this system.
- The workflow label should make clear that it is submitted to the fork and waiting for a PR/upstream merge, not already merged upstream.

## Fork Branch Links

The AI repository button should link to the most useful known destination:

1. Latest fork branch from `pull_requests` for that mod, using `https://github.com/{repo_slug}/tree/{branch}`.
2. Fork repository homepage if a verified fork exists but no branch is known.
3. Disabled "未创建" state if no verified fork exists.

The publish response already returns `repo_slug`, `branch`, and `commit_sha`; the index API should expose the branch URL so the frontend does not need to infer it from commit URLs.

## API Additions

New protected endpoints:

- `GET /api/admin/settings`
- `PATCH /api/admin/settings`
- `GET /api/admin/mods`
- `GET /api/translation-queue`
- `POST /api/translation-queue`
- `PATCH /api/translation-queue/{queue_id}`
- `POST /api/translation-queue/{queue_id}/start`
- `POST /api/translation-queue/{queue_id}/retry`
- `DELETE /api/translation-queue/{queue_id}`

`GET /api/admin/mods` should return a management-oriented summary derived from mod index, review items, jobs, queue rows, workflows, and pull request rows.

## Error Handling

Admin-auth errors return 401 for APIs and 404 for the hidden admin route when the suffix is wrong.

Queue operations should return 422 with actionable messages for:

- A mod that has no repo URL and no local source.
- A duplicate active queue item.
- Starting while another translation is already running.
- Missing GitHub token when source materialization is required.

Scheduler failures should be recorded on the queue row and as `job_events` when a job exists.

## Testing

Targeted tests should cover:

- Admin route hidden when auth is enabled.
- Correct secret sets cookie.
- Protected APIs reject requests without cookie.
- Public read APIs still work without cookie.
- Settings defaults and updates.
- Queue add/order/remove/retry behavior.
- Scheduler starts only one due queued item.
- Scheduler does not start while a translation job is active.
- Mod index AI repo URL points to branch after fork commit.
- Admin mod summary groups translated, review, queue, and fork-committed states correctly.

Because broad FastAPI `TestClient` suites can hang in this environment, tests should be targeted and isolated around the changed routes/repository helpers.
