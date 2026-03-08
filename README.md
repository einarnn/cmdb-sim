# CMDB Simulator

Simple `aiohttp` service that simulates ServiceNow-style CMDB records with periodic random mutations. Intended for use with pxGrid Direct push connectors on the Cisco Identity Services Engine. Readers can find a pxGrid Direct webinar [here](https://youtu.be/g8fzBPY8gU8). It is recommended that you be familiar with Docker and X.509 certificates to easily make use of this example.

## Quick Start

This repository includes private CA and server certs. At minimum users will need to regenerate the server set with an appropriate IP SAN, but the example may still be used with plain http instead of https. If https is chosen then the CA cert **must** be uploaded to ISE's trusted certificates unless cert validation is disabled.

Assuming the `docker-compose.yml` included has been used, these two URLs may be used to configure an ISE pxGrid Direct push connector for bulk and incremental sync over https:

* `https://<you-ip-address>:8443/api/v1/cmdb`
* `https://<you-ip-address>:8443/api/v1/cmdb?sys_updated_on.gte.{{.LATEST_VERSION}}`

The test server doesn't implement authentication, but this must be configured on ISE regardless. Just configure basic authentication with a dummy username and password.

Plain http may also be used if "https" is replaced by "http" and ":8443" is replaced by ":8080".

Changes to the data in the last 5 minutes can be queried **on macOS using bash** using a CLI command like:

```bash
#
# define a shell function for bash to URL encode a string
#
urlencode() {
  local LC_ALL=C
  local c

  while IFS= read -r -n1 c; do
    case "$c" in
      [a-zA-Z0-9.~_-])
        printf '%s' "$c"
        ;;
      *)
        printf '%%%02X' "'$c"
        ;;
    esac
  done
}

#
# create a timstamp string in the correct format for 5 minutes ago as
# part of the query URL
#
curl --silent "http://localhost:8080/api/v1/cmdb?sys_updated_on.gte.$(date -v -1M '+%Y-%m-%d %H:%M:%S' | urlencode)"
```

If you also have `jq` installed, you can get the number of changes in the last 5 minutes using:

```bash
# display changes in last 5 minutes, pretty printed
curl --silent "http://localhost:8080/api/v1/cmdb?sys_updated_on.gte.$(date -v -1M '+%Y-%m-%d %H:%M:%S' | urlencode)" | jq -C ' .result | length'

# count the number of changes
curl --silent "http://localhost:8080/api/v1/cmdb?sys_updated_on.gte.$(date -v -1M '+%Y-%m-%d %H:%M:%S' | urlencode)" | jq -C
```



## Features

- In-memory dataset generated at startup via `CMDB_RECORD_COUNT`
- Random incremental mutations for:
  - `sys_updated_on`
  - `u_segmentation_group_tag`
  - `u_sync` toggle
  - monotonic `sys_mod_count`
- Hard cap on changed records per hour (`MAX_RECORD_CHANGES_PER_HOUR`, default `1000`)
- `GET /api/v1/cmdb` returns `{"result":[...]}` sorted by `sys_updated_on` ascending
- `sys_updated_on` relational filters with query syntax:
  - `sys_updated_on.gt.<timestamp>`
  - `sys_updated_on.gte.<timestamp>`
  - `sys_updated_on.lt.<timestamp>`
  - `sys_updated_on.lte.<timestamp>`
  - `sys_updated_on.eq.<timestamp>`
- Optional TLS with provided cert/key or auto-generated self-signed certs
- Optional Postgres-backed persistence controlled by `PERSISTENCE_ENABLED`

Timestamp format is `YYYY-MM-DD HH:MM:SS`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.main
```

## Run with Docker Compose

```bash
docker compose up --build
```

Enable TLS:

```bash
TLS_ENABLED=true docker compose up --build
```

Generate PEM CA + server certs locally:

```bash
./certs/generate-certs.sh ./certs
```

Regenerate only server cert/key using existing CA:

```bash
./certs/generate-certs.sh ./certs --regen-server
```

If you wish to properly validate certs you will need to add IP SANs:

```bash
./certs/generate-certs.sh ./certs --regen-server --ip-san 127.0.0.1 --ip-san 10.0.0.15
```

You can set the TLS_CERT_FILE in `docker-compose.yml` to either `server-cert.pem` or create a `server-chain.pem` by running this command in the `certs` sub-directory:

```bash
cat server-cert.pem ca-cert.pem > server-chain.pem
```

Enable optional Postgres service profile:

```bash
docker compose --profile db up --build
```

## API examples

All records:

```bash
curl -s "http://localhost:8080/api/v1/cmdb"
```

Filter records updated after a timestamp:

```bash
curl -s "http://localhost:8080/api/v1/cmdb?sys_updated_on.gte.2021-08-03%2014:09:24"
```

Filter range:

```bash
curl -s "http://localhost:8080/api/v1/cmdb?sys_updated_on.gte.2021-08-03%2000:00:00&sys_updated_on.lt.2021-08-04%2000:00:00"
```

Health:

```bash
curl -s "http://localhost:8080/healthz"
```

Readiness:

```bash
curl -s "http://localhost:8080/readyz"
```

## Configuration

- `CMDB_HOST` (default `0.0.0.0`)
- `CMDB_PORT` (default `8080`)
- `CMDB_RECORD_COUNT` (default `1000`)
- `MAX_RECORD_CHANGES_PER_HOUR` (default `1000`)
- `MUTATION_TICK_SECONDS` (default `5`)
- `MAX_MUTATIONS_PER_TICK` (default `5`)
- `CMDB_RANDOM_SEED` (default `42`)
- `MUTATION_ENABLED` (default `true`)
- `PERSISTENCE_ENABLED` (`true` enables persistence, anything else disables)
- `DB_HOST` (default `localhost`)
- `DB_PORT` (default `5432`)
- `DB_USER` (default `cmdb`)
- `DB_PASSWORD` (default `cmdb`)
- `DB_NAME` (default `cmdb`)
- `TLS_ENABLED` (default `false`)
- `TLS_PORT` (default `8443`)
- `TLS_AUTO_GENERATE_CERTS` (default `true`)
- `TLS_KEEP_HTTP_LISTENER` (default `true`)
- `TLS_CERT_FILE` (default `/tmp/cmdb-cert.pem`)
- `TLS_KEY_FILE` (default `/tmp/cmdb-key.pem`)

## Tests

```bash
pytest -q
```

## Appendices

### A1 zsh-safe urlencode function

```zsh
urlencode() {
  emulate -L zsh
  local LC_ALL=C
  local s c

  s=$(cat)

  local i=1 len=${#s}
  while (( i <= len )); do
    c=${s[i]}
    case "$c" in
      [a-zA-Z0-9.~_-])
        printf '%s' "$c"
        ;;
      *)
        printf '%%%02X' "'$c"
        ;;
    esac
    (( i++ ))
  done
}
```
