_ts_workspace_root() {
  local d="${PWD}"
  while [[ "${d}" != "/" ]]; do
    if [[ -f "${d}/.gitmodules" ]] && [[ -d "${d}/.devcontainer" ]]; then
      printf '%s' "${d}"
      return 0
    fi
    d="$(dirname "${d}")"
  done
  printf '%s' "/workspaces/Turner-Services-Infrastructure"
}

_ts_banner() {
  printf '\n\033[33m[Turner Services]\033[0m %s\n' "$1"
  shift
  for line in "$@"; do
    printf '  %s\n' "${line}"
  done
  printf '\n'
}

if ! command -v pass-cli >/dev/null 2>&1; then
  _ts_banner "pass-cli not installed in this shell's PATH." \
    "Rebuild the devcontainer or install it manually:" \
    "curl -fsSL https://proton.me/download/pass-cli/install.sh | bash"
elif ! pass-cli info >/dev/null 2>&1; then
  _ts_banner "Proton Pass is not logged in." \
    "Run:  pass-cli login --interactive <you@proton.me>" \
    "Then: ./scripts/bootstrap-secrets.sh"
else
  _ts_ws="$(_ts_workspace_root)"
  if [[ -f "${_ts_ws}/.secrets/env.sh" ]]; then
    # shellcheck disable=SC1090
    source "${_ts_ws}/.secrets/env.sh"
  else
    _ts_banner "Logged in to Proton Pass, but .secrets/ is empty." \
      "Run: ${_ts_ws}/scripts/bootstrap-secrets.sh"
  fi
  unset _ts_ws
fi

unset -f _ts_workspace_root _ts_banner
