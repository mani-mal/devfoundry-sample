"""Assets for OpsLedger: sites, assets, equipment, maintenance plans (T017, T018).

Includes the asset filtered list with stable pagination (T019): assets are
ordered by ``created_at ASC, id ASC`` -- a deterministic total order -- and
paged by a keyset cursor of ``(after_created_at, after_id)``, so identical
timestamps neither duplicate nor omit stable rows. Includes optimistic
version updates for assets (T020): a stale version surfaces a retryable
ConflictError and the second writer's stale write is refused. Includes the
site/asset archive rules (T021): archive sets ``archived_at`` (never DELETE,
referenced records are retained), archived objects are excluded from the
default lists and cannot accept new work (live assets block a site archive;
:func:`require_site_accepts_assets` refuses new assets on an archived site).
Includes the transactional audit (T022): :func:`update_asset_audited` runs
the optimistic-concurrency update and its audit event in one shared
transaction, so the business mutation and its audit/outbox record commit
atomically — a forced audit failure rolls back the business mutation too.
"""

from __future__ import annotations

from opsledger.assets.sites import (
    DUPLICATE_SITE_CODE_MESSAGE,
    SITE_NOT_FOUND_MESSAGE,
    create_site,
    get_site,
    list_sites,
    update_site,
)
from opsledger.assets.assets import (
    DUPLICATE_ASSET_TAG_MESSAGE,
    CRITICALITIES,
    create_asset,
    get_asset,
)
from opsledger.assets.listing import asset_page_cursor, list_assets
from opsledger.assets.updates import (
    STALE_VERSION_MESSAGE,
    update_asset,
    update_asset_audited,
)
from opsledger.assets.archiving import (
    ARCHIVED_SITE_MESSAGE,
    SITE_HAS_LIVE_ASSETS_MESSAGE,
    archive_asset,
    archive_site,
    require_site_accepts_assets,
    unarchive_asset,
    unarchive_site,
)

__all__ = [
    "ARCHIVED_SITE_MESSAGE",
    "SITE_HAS_LIVE_ASSETS_MESSAGE",
    "archive_asset",
    "archive_site",
    "require_site_accepts_assets",
    "unarchive_asset",
    "unarchive_site",
    "DUPLICATE_ASSET_TAG_MESSAGE",
    "DUPLICATE_SITE_CODE_MESSAGE",
    "SITE_NOT_FOUND_MESSAGE",
    "STALE_VERSION_MESSAGE",
    "CRITICALITIES",
    "asset_page_cursor",
    "create_asset",
    "create_site",
    "update_asset",
    "update_asset_audited",
    "get_asset",
    "get_site",
    "list_assets",
    "list_sites",
    "update_site",
]
