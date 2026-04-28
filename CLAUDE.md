# MLB HR Tracker — Project Notes

## n8n Workflow Gotchas

### Comma-separated API parameters
n8n's Query Parameters section URL-encodes commas (`%2C`), which breaks API calls that need literal commas (e.g., `hydrate=probablePitcher,team` or `personIds=123,456`). **Always embed comma-separated values directly in the URL string** instead of using Query Parameters.

### No fetch() in Code nodes
`fetch()` is restricted in n8n Code nodes and silently fails. When a workflow needs API calls, use **HTTP Request nodes** instead. Structure as: Code (prepare) → HTTP Request (fetch) → Code (process). If two rounds of API calls are needed, chain: Code → HTTP → Code → HTTP → Code.

### MLB API team abbreviations
The MLB Stats API uses `AZ` (not `ARI`) for Arizona and `ATH` (not `OAK`) for Oakland. The game log endpoint returns opponent as `{id, name, link}` without `abbreviation` — use the `/api/v1/teams` endpoint or boxscore data for abbreviation lookups.
