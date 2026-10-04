from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.auth.rbac import require_roles
from app.db.models.reviewer import ReviewerRole

RoleDependency = Callable[..., Any]

require_reviewer: RoleDependency = require_roles(ReviewerRole.REVIEWER)
require_source_owner: RoleDependency = require_roles(ReviewerRole.SOURCE_OWNER)
require_admin: RoleDependency = require_roles(ReviewerRole.ADMIN)
require_conflict_resolver: RoleDependency = require_roles(ReviewerRole.CONFLICT_RESOLVER)
