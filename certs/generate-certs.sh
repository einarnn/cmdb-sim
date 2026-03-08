#!/usr/bin/env bash
set -euo pipefail

# Generates a PEM CA key/cert and a CA-signed server key/cert.
#
# Usage:
#   ./certs/generate-certs.sh [output_dir] [--regen-server] [--ip-san <ip> ...]
#
# Output files (PEM):
#   ca-key.pem
#   ca-cert.pem
#   server-key.pem
#   server-cert.pem
#
# Optional env vars:
#   CERT_DAYS        (default: 365)
#   CA_CN            (default: CMDB Sim Local CA)
#   SERVER_CN        (default: localhost)
#   SERVER_SAN_DNS   (default: localhost,cmdb-sim)
#   SERVER_SAN_IPS   (default: empty, comma separated; merged with --ip-san values)

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required but not found in PATH" >&2
  exit 1
fi

DEFAULT_OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${DEFAULT_OUT_DIR}"
REGEN_SERVER_ONLY=0
IP_SANS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --regen-server)
      REGEN_SERVER_ONLY=1
      shift
      ;;
    --ip-san)
      if [[ $# -lt 2 ]]; then
        echo "--ip-san requires a value" >&2
        exit 1
      fi
      IP_SANS+=("$2")
      shift 2
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      OUT_DIR="$1"
      shift
      ;;
  esac
done

CERT_DAYS="${CERT_DAYS:-365}"
CA_CN="${CA_CN:-CMDB Sim Local CA}"
SERVER_CN="${SERVER_CN:-localhost}"
SERVER_SAN_DNS="${SERVER_SAN_DNS:-localhost,cmdb-sim}"
SERVER_SAN_IPS="${SERVER_SAN_IPS:-}"

mkdir -p "${OUT_DIR}"

CA_KEY="${OUT_DIR}/ca-key.pem"
CA_CERT="${OUT_DIR}/ca-cert.pem"
SERVER_KEY="${OUT_DIR}/server-key.pem"
SERVER_CSR="${OUT_DIR}/server.csr"
SERVER_CERT="${OUT_DIR}/server-cert.pem"
SERVER_EXT="${OUT_DIR}/server-ext.cnf"

cat > "${SERVER_EXT}" <<EOF
[v3_server]
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=critical,serverAuth
subjectAltName=@alt_names
[alt_names]
EOF

IFS=',' read -r -a SAN_ARRAY <<< "${SERVER_SAN_DNS}"
idx=1
for dns in "${SAN_ARRAY[@]}"; do
  trimmed="$(echo "${dns}" | xargs)"
  if [[ -n "${trimmed}" ]]; then
    echo "DNS.${idx}=${trimmed}" >> "${SERVER_EXT}"
    idx=$((idx + 1))
  fi
done

if [[ -n "${SERVER_SAN_IPS}" ]]; then
  IFS=',' read -r -a ENV_IP_SANS <<< "${SERVER_SAN_IPS}"
  for env_ip in "${ENV_IP_SANS[@]}"; do
    trimmed="$(echo "${env_ip}" | xargs)"
    if [[ -n "${trimmed}" ]]; then
      IP_SANS+=("${trimmed}")
    fi
  done
fi

ip_idx=1
if [[ ${#IP_SANS[@]} -gt 0 ]]; then
  for ip in "${IP_SANS[@]}"; do
    trimmed="$(echo "${ip}" | xargs)"
    if [[ -n "${trimmed}" ]]; then
      echo "IP.${ip_idx}=${trimmed}" >> "${SERVER_EXT}"
      ip_idx=$((ip_idx + 1))
    fi
  done
fi

if [[ "${REGEN_SERVER_ONLY}" -eq 1 ]]; then
  if [[ ! -f "${CA_KEY}" || ! -f "${CA_CERT}" ]]; then
    echo "--regen-server requested, but CA files were not found in ${OUT_DIR}" >&2
    echo "Expected: ${CA_KEY} and ${CA_CERT}" >&2
    exit 1
  fi
else
  openssl genrsa -out "${CA_KEY}" 4096
  openssl req -x509 -new -nodes \
    -key "${CA_KEY}" \
    -sha256 \
    -days "${CERT_DAYS}" \
    -out "${CA_CERT}" \
    -subj "/CN=${CA_CN}"
fi

openssl genrsa -out "${SERVER_KEY}" 2048
openssl req -new \
  -key "${SERVER_KEY}" \
  -out "${SERVER_CSR}" \
  -subj "/CN=${SERVER_CN}"

openssl x509 -req \
  -in "${SERVER_CSR}" \
  -CA "${CA_CERT}" \
  -CAkey "${CA_KEY}" \
  -CAcreateserial \
  -out "${SERVER_CERT}" \
  -days "${CERT_DAYS}" \
  -sha256 \
  -extfile "${SERVER_EXT}" \
  -extensions v3_server

rm -f "${SERVER_CSR}" "${SERVER_EXT}" "${OUT_DIR}/ca-cert.srl"

echo "Generated PEM files in ${OUT_DIR}:"
if [[ "${REGEN_SERVER_ONLY}" -eq 0 ]]; then
  echo "  ${CA_KEY}"
  echo "  ${CA_CERT}"
else
  echo "  (reused existing CA key/cert)"
fi
echo "  ${SERVER_KEY}"
echo "  ${SERVER_CERT}"
