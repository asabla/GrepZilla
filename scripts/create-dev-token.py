from datetime import timedelta

from backend.src.api.deps.auth import create_access_token
from backend.src.config.settings import get_settings

settings = get_settings()
token = create_access_token(
    user_id="dev-user",
    repository_ids=[],  # empty = admin/all repos
    branch_overrides={},  # or {"<repo_id>": "branch"}
    expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
)
print(token)
