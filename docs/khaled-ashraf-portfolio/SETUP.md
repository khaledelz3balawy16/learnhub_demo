# Setup

Start from the sanitized original README when available. The entries below are extracted from this specific source snapshot.

## Environment

Supply your own development or sandbox service configuration. Environment templates contain placeholder values. Runtime credentials and production data are excluded.

- `backend/.env.example`
- `frontend/.env.example`

## JavaScript / TypeScript

### `frontend`

Package manager metadata: `not specified`.

| Existing script | Command in manifest |
| --- | --- |
| `npm run dev` | `vite` |
| `npm run build` | `tsc -b && vite build` |
| `npm run lint` | `oxlint` |
| `npm run typecheck` | `tsc -b` |

### `tools/harness`

Package manager metadata: `not specified`.


## Python requirement files

- `backend/requirements-dev.txt`
- `backend/requirements.txt`

## External integrations

Consult the source configuration for databases, identity providers, email, storage, payments, and other APIs. Select local or sandbox targets before running startup hooks, migrations, seeds, or integration tests. No external-service credentials are provided in this copy.
