"""Assets for OpsLedger: sites, assets, equipment, maintenance plans (T017, T018)."""

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

__all__ = [
    "DUPLICATE_ASSET_TAG_MESSAGE",
    "DUPLICATE_SITE_CODE_MESSAGE",
    "SITE_NOT_FOUND_MESSAGE",
    "CRITICALITIES",
    "create_asset",
    "create_site",
    "get_asset",
    "get_site",
    "list_sites",
    "update_site",
]
