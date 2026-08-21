# Deployment Troubleshooting

## Frontend issues

### API calls fail with `503`

- Confirm `NEXT_PUBLIC_API_URL` points to the deployed backend origin.
- Check `curl https://your-backend.example/api/health`.
- Redeploy Vercel after changing a `NEXT_PUBLIC_*` variable.
- Review the browser Network panel and backend provider logs.

### Browser reports a CORS error

- Set `CORS_ORIGINS` to the exact Vercel/custom origin, including `https://`.
- Separate multiple origins with commas and omit trailing slashes.
- Restart/redeploy the backend after changing the variable.
- Confirm the request preflight allows `OPTIONS` and `Content-Type`.

### Page does not load

- Review Vercel build logs.
- Confirm the Vercel root directory is `frontend/`.
- Run `npm ci`, `npm run typecheck`, and `npm run build` locally.
- Check the browser console for runtime errors.

## Backend issues

### Production startup fails: `DATABASE_URL required in production`

Add a valid PostgreSQL connection string to the provider environment settings,
then restart the service. Do not put the password in source control or logs.

### Production startup fails: `OPENAI_API_BASE required in production`

Add the base URL of the OpenAI-compatible model service, usually ending in
`/v1`, then restart the service.

### Production startup fails: `CORS_ORIGINS required in production`

Set one or more exact frontend origins, for example
`https://your-app.vercel.app,https://your-domain.example`.

### Models are not available

- Confirm the provider has network access to the configured model endpoint.
- Do not set `HF_HUB_OFFLINE=1` or `TRANSFORMERS_OFFLINE=1` in a deployment that
  must download model assets.
- Confirm the configured model identifier and optional `HF_TOKEN`.
- Prefer an external OpenAI-compatible endpoint for serverless deployments.

### Health check reports an error

`/api/health` returns process liveness plus individual dependency states. Check
the database URL, model endpoint reachability, RAG backend configuration, and
provider logs. A `not_configured` state is expected for optional services in
development.

## Test the connection

From a browser console on the deployed frontend:

```javascript
fetch('https://your-backend.example/api/health')
  .then((response) => response.json())
  .then((data) => console.log('✅ CORS working:', data))
  .catch((error) => console.error('❌ Connection error:', error));
```

From a terminal:

```bash
curl https://your-backend.example/api/health
curl -X POST https://your-backend.example/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"test","language":"en"}'
```

## Common API errors

| Error | Meaning | Recovery |
| --- | --- | --- |
| `422 validation_error` | Request fields are invalid or missing. | Follow `contracts/api-contract.md`. |
| `503 service_unavailable` | A required backend dependency is unavailable. | Check health checks and provider logs. |
| CORS error | The browser origin is not allowed. | Update `CORS_ORIGINS` and restart. |
| `404 Not Found` | The URL or route is incorrect. | Use `/api/health`, `/api/chat`, `/api/eligibility`, `/api/programs`, or `/api/sources`. |
| `500 internal_error` | Unexpected backend failure. | Inspect sanitized provider logs and reproduce locally. |
