#!/bin/sh
# Lanceur commun des hooks super-reprompt : run.sh <script.py> [--guard]
# Trouve un VRAI Python 3 (les raccourcis du Microsoft Store dans WindowsApps ne sont pas des interpreteurs :
# ils sortent en code 49 et un hook PreToolUse qui sort en 49 n'est qu'une erreur, jamais un blocage).
# Le chemin retenu est mis en cache pour eviter de rechercher a chaque appel (latence A20).
# --guard : pare-feu L4. Sans interpreteur, il echoue FERME (exit 2) si une mission scellee est trouvee
# en remontant depuis le dossier courant ; sinon il reste silencieux (exit 0), comme les autres hooks.
script="$1"; mode="$2"
case "$0" in */*) here="${0%/*}" ;; *) here=. ;; esac
root="$here/.."
target="$root/scripts/$script"
cache="${SR_HOME:-$HOME/.claude/super-reprompt}/python-path"

usable() {
  case "$1" in ""|*WindowsApps*) return 1 ;; esac
  [ -x "$1" ] || [ -f "$1" ]
}

py=""
if [ -r "$cache" ]; then
  read -r py < "$cache" 2>/dev/null
  usable "$py" || py=""
fi
if [ -z "$py" ]; then
  for c in python3 python; do
    p=$(command -v "$c" 2>/dev/null)
    if usable "$p" && "$p" -c "import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)" >/dev/null 2>&1; then py="$p"; break; fi
  done
  if [ -z "$py" ] && command -v py >/dev/null 2>&1; then
    py=$(py -3 -c "import sys; print(sys.executable)" 2>/dev/null)
    usable "$py" || py=""
  fi
  if [ -n "$py" ]; then
    mkdir -p "${cache%/*}" 2>/dev/null && printf '%s\n' "$py" > "$cache" 2>/dev/null
  fi
fi

if [ -z "$py" ]; then
  if [ "$mode" = "--guard" ]; then
    d=$(pwd)
    while :; do
      for s in "$d"/.super-reprompt/*/SCELLE.json; do
        if [ -f "$s" ] && [ ! -e "${s%/*}/FERME" ]; then
          echo "PARE-FEU F00 : aucun interpreteur Python 3 utilisable, mission scellee : action refusee (fail-closed)." >&2
          exit 2
        fi
      done
      case "$d" in /|?:/|?:) break ;; esac
      up="${d%/*}"; [ -z "$up" ] && up=/
      [ "$up" = "$d" ] && break; d="$up"
    done
  fi
  exit 0
fi

if [ "$mode" = "--guard" ]; then
  exec "$py" -I -S "$target"
fi
"$py" "$target"
exit 0
