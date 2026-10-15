#!/usr/bin/env bash
# Render docs/diagrams/*.d2 to SVG. `--check` fails if any committed SVG is stale.
# D2 output depends on its version, so renders are pinned to one.
# D2's dark themes don't recolour explicit style colours, so each SVG gets
# _dark.css appended, which remaps the palette when the viewer prefers dark mode.
set -euo pipefail
cd "$(dirname "$0")"
want=v0.9.0
have=$(d2 --version)
[[ $have == "$want" ]] || { echo "need d2 $want, have $have" >&2; exit 1; }

missing=$(grep -ohi '#[0-9a-f]\{6\}' ./*.d2 | sort -u | grep -viFxf <(grep -ohi '#[0-9a-f]\{6\}' _dark.css) || true)
[[ -z $missing ]] || { echo "colours missing from _dark.css:" $missing >&2; exit 1; }

log=/dev/stderr
[[ ${1:-} == --check ]] && log=/dev/null
render() {  # render <src>: print its SVG with the dark palette appended
  local svg
  svg=$(d2 --theme 0 "$1" - 2>"$log")
  printf '%s<style>%s</style></svg>\n' "${svg%</svg>}" "$(<_dark.css)"
}

stale=0
for src in [!_]*.d2; do
  svg=${src%.d2}.svg
  if [[ ${1:-} == --check ]]; then
    tmp=$(mktemp --suffix=.svg)
    render "$src" >"$tmp"
    cmp -s "$tmp" "$svg" || { echo "stale: docs/diagrams/$svg" >&2; stale=1; }
    rm -f "$tmp"
  else
    render "$src" >"$svg"
  fi
done
exit $stale
