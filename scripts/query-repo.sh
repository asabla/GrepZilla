# Run uv run ./scripts/create-dev-token.py and save the output to TOKEN variable
TOKEN=$(uv run ./scripts/create-dev-token.py)

# Take first argument as repository url with (.git)
REPO_ID=$1

# Question to ask, argument with default value
QUESTION=${2:-"Where is the IRC implementation?"}

# Save response into variable
RESPONSE=$(curl -X POST http://localhost:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$QUESTION\", \"repositories\": [\"$REPO_ID\"], \"agent_mode\": true}"
)

# Pretty print the json response
printf '%s' "$RESPONSE" | jq .

# Pretty print "answer" field as markdown
printf '%s' "$RESPONSE" | jq -r '.answer' | pandoc -f markdown -t plain
