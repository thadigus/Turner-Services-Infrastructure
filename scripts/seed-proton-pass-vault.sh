#!/usr/bin/env bash
# Seed the Proton Pass vault. Idempotent: existing items are skipped.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SENSITIVE_DIR="${REPO_ROOT}/turner-services-sensitive-repo"
SECRETS_DIR="${REPO_ROOT}/.secrets"
VAULT="${VAULT:-Turner-Services-Infra}"
PBS_ONLY=0
if [[ "${1:-}" == "--pbs-only" ]]; then
  PBS_ONLY=1
  shift
fi
[[ $# -eq 0 ]] || { echo "Usage: $0 [--pbs-only]" >&2; exit 2; }

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
  jq -e --arg t "$1" '.items[] | select(.title==$t or .content.title==$t)' <<<"$EXISTING_ITEMS_JSON" >/dev/null
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
  shift 3
  if item_exists "$title"; then
    echo "skip (exists): $title"
    return 0
  fi
  [[ -n "$password" ]] || die "empty password for $title"
  echo "create login:  $title  (username=$username)"
  local cmd=(pass-cli item create login
    --vault-name "$VAULT"
    --title "$title"
    --username "$username"
    --password "$password")
  local url
  for url in "$@"; do
    [[ -n "$url" ]] && cmd+=(--url "$url")
  done
  "${cmd[@]}" >/dev/null
}

get_item_field() {
  local title="$1" field="$2"
  pass-cli item view --vault-name "$VAULT" --item-title "$title" --field "$field"
}

ensure_pbs_autoinstall_items() {
  local answer_title="ts-pbs-autoinstall-answer"
  local root_title="ts-pbs-root"
  if item_exists "$answer_title"; then
    echo "skip (exists): $answer_title"
    return 0
  fi

  [[ -f "${SENSITIVE_DIR}/turnerans_svc_id_rsa.pub" ]] || die "missing PBS root SSH public key: ${SENSITIVE_DIR}/turnerans_svc_id_rsa.pub"
  command -v openssl >/dev/null 2>&1 || die "openssl required to generate PBS root password hash"

  local root_password root_hash pubkey answer_file
  if item_exists "$root_title"; then
    echo "reuse (exists): $root_title"
    root_password="$(get_item_field "$root_title" password)"
  else
    root_password="$(openssl rand -base64 36 | tr -d '\n')"
    ensure_login "$root_title" root "$root_password" "https://pbs.turnerservices.cloud:8007"
  fi
  root_hash="$(printf '%s\n' "$root_password" | openssl passwd -6 -stdin)"
  pubkey="$(tr -d '\r\n' < "${SENSITIVE_DIR}/turnerans_svc_id_rsa.pub")"
  answer_file="$(mktemp)"

  cat > "$answer_file" <<EOF_PBS_ANSWER
[global]
keyboard = "en-us"
country = "us"
fqdn = "pbs-primary-01.turnerservices.cloud"
mailto = "admin@turnerservices.cloud"
timezone = "America/Indiana/Indianapolis"
root-password-hashed = "$root_hash"
root-ssh-keys = [
  "$pubkey"
]

[network]
source = "from-dhcp"

[disk-setup]
filesystem = "ext4"
lvm.swapsize = 0
lvm.maxvz = 0
disk-list = ["sda"]

[first-boot]
source = "from-iso"
ordering = "network-online"
EOF_PBS_ANSWER

  ensure_note_from_file "$answer_title" "$answer_file"
  rm -f "$answer_file"
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

if (( PBS_ONLY )); then
  ensure_pbs_autoinstall_items
  echo
  echo "Vault $VAULT updated with PBS autoinstall items. Next: ./scripts/bootstrap-secrets.sh"
  exit 0
fi

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
ensure_pbs_autoinstall_items

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
