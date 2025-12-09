# Run uv run ./scripts/create-dev-token.py and save the output to TOKEN variable
TOKEN=$(uv run ./scripts/create-dev-token.py)

# Take first argument as repository url with (.git)
REPO_URL=$1

curl -X POST http://localhost:8000/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$(basename -s .git $REPO_URL)\", \"git_url\": \"$REPO_URL\", \"default_branch\": \"main\"}"
