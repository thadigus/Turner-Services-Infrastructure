#!/usr/bin/env bash
# Seed the Proton Pass vault. Idempotent: existing items are skipped.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SENSITIVE_DIR="${REPO_ROOT}/turner-services-sensitive-repo"
VAULT="${VAULT:-Turner-Services-Infra}"

die() { echo "Error: $*" >&2; exit 1; }

command -v pass-cli >/dev/null 2>&1 || die "pass-cli not on PATH"
command -v jq       >/dev/null 2>&1 || die "jq required (dnf install -y jq)"
pass-cli info >/dev/null 2>&1       || die "pass-cli not logged in. Run: pass-cli login --interactive <you@proton.me>"

vault_count="$(pass-cli vault list --output json | jq --arg n "$VAULT" '[.vaults[] | select(.name==$n)] | length')"
if [[ "$vault_count" == 0 ]]; then
  echo "Creating vault: $VAULT"
  pass-cli vault create --name "$VAULT" >/dev/null
elif [[ "$vault_count" != 1 ]]; then
  die "$vault_count vaults named '$VAULT' exist. Delete duplicates in the Proton Pass UI (or via 'pass-cli vault delete') and re-run."
fi

EXISTING_ITEMS_JSON="$(pass-cli item list "$VAULT" --output json 2>/dev/null || echo '{"items":[]}')"

item_exists() {
  jq -e --arg t "$1" '.items[] | select(.title==$t)' <<<"$EXISTING_ITEMS_JSON" >/dev/null
}

ensure_note_from_file() {
  local title="$1" path="$2"
  if item_exists "$title"; then
    echo "skip (exists): $title"
    return 0
  fi
  [[ -f "$path" ]] || die "missing source file for $title: $path"
  echo "create note:   $title  <-  $path"
  jq -n --arg title "$title" --rawfile note "$path" '{title:$title, note:$note}' \
    | pass-cli item create note --vault-name "$VAULT" --from-template - >/dev/null
}

ensure_login() {
  local title="$1" username="$2" password="$3"
  if item_exists "$title"; then
    echo "skip (exists): $title"
    return 0
  fi
  [[ -n "$password" ]] || die "empty password for $title"
  echo "create login:  $title  (username=$username)"
  pass-cli item create login \
    --vault-name "$VAULT" \
    --title "$title" \
    --username "$username" \
    --password "$password" >/dev/null
}

prompt_secret() {
  local var="$1" label="$2" val="${!1:-}"
  if [[ -z "$val" ]]; then
    read -rsp "$label: " val; echo >&2
  fi
  [[ -n "$val" ]] || die "$label is required"
  printf '%s' "$val"
}

prompt_value() {
  local var="$1" label="$2" default="${3:-}" val="${!1:-}"
  if [[ -z "$val" ]]; then
    if [[ -n "$default" ]]; then
      read -rp "$label [$default]: " val
      val="${val:-$default}"
    else
      read -rp "$label: " val
    fi
  fi
  [[ -n "$val" ]] || die "$label is required"
  printf '%s' "$val"
}

# File-backed items
ensure_note_from_file ts-turneradmin-ssh-privkey   "${SENSITIVE_DIR}/turneradmin_id_rsa"
ensure_note_from_file ts-turnerans_svc-ssh-privkey "${SENSITIVE_DIR}/turnerans_svc_id_rsa"
ensure_note_from_file ts-main-prod-kubeconfig      "${SENSITIVE_DIR}/kubeconfigs/ts-main-prod.conf"
ensure_note_from_file ts-main-test-kubeconfig      "${SENSITIVE_DIR}/kubeconfigs/ts-main-test.conf"
ensure_note_from_file ts-cloudflare-dns01-token    "${SENSITIVE_DIR}/cloudflare-dns01-token.txt"
extra_seed_hook="${SENSITIVE_DIR}/ci/seed-extra-pass-items.sh"
if [[ -f "${extra_seed_hook}" ]]; then
  # shellcheck source=/dev/null
  source "${extra_seed_hook}"
fi

# Credential items (prompted unless TS_* is exported)
need_creds=0
for t in ts-windows-turneradmin ts-windows-turnerans_svc ts-proxmox-packer-apitoken ts-unifi-apikey ts-pulumi-access-token; do
  item_exists "$t" || { need_creds=1; break; }
done

if (( need_creds )); then
  echo
  echo "Enter credential values (leave blank to abort). Pre-set TS_* env vars to skip prompts."
  echo

  if ! item_exists ts-windows-turneradmin; then
    pw="$(prompt_secret TS_WIN_TURNERADMIN_PASSWD 'Windows turneradmin password')"
    ensure_login ts-windows-turneradmin turneradmin "$pw"
  fi
  if ! item_exists ts-windows-turnerans_svc; then
    pw="$(prompt_secret TS_WIN_TURNERANS_SVC_PASSWD 'Windows turnerans_svc password')"
    ensure_login ts-windows-turnerans_svc turnerans_svc "$pw"
  fi
  if ! item_exists ts-proxmox-packer-apitoken; then
    user="$(prompt_value  TS_PROXMOX_PACKER_USER   'Proxmox API token ID (e.g. root@pam!packer)')"
    pw="$(prompt_secret TS_PROXMOX_PACKER_APIKEY 'Proxmox API token secret')"
    ensure_login ts-proxmox-packer-apitoken "$user" "$pw"
  fi
  if ! item_exists ts-unifi-apikey; then
    pw="$(prompt_secret TS_UNIFI_API_KEY 'UniFi local Network API key')"
    ensure_login ts-unifi-apikey unifi "$pw"
  fi
  if ! item_exists ts-pulumi-access-token; then
    pw="$(prompt_secret PULUMI_ACCESS_TOKEN 'Pulumi access token')"
    ensure_login ts-pulumi-access-token pulumi "$pw"
  fi
fi

echo
echo "Vault '$VAULT' seeded. Next: ./scripts/bootstrap-secrets.sh"
