# Rex production-context highlighting for zsh.
#
# Labels the Rex pane by context and shows a red PROD segment in the
# Powerlevel10k prompt when the pane is working against production:
#   🔴 PROD · <reason>   production context (red-shifted text)
#   🟡 SUDO · <command>  while a sudo/su/doas command runs (yellow-shifted text)
#   🌐 <host>            ssh/mosh to a non-prod host
#   🌐 <host> · <dir>    this shell itself runs on a remote machine
#   💻 local · <dir>     anything else
#
# Signals checked before every prompt (first match wins, all are listed):
#   ssh/mosh  - a running ssh/mosh command whose target matches REX_PROD_HOST_RE
#   host      - this shell runs on a remote host that matches REX_PROD_HOST_RE
#   kube      - kubectl current-context
#   aws       - AWS_PROFILE / AWS_VAULT / AWS_DEFAULT_PROFILE
#   tofu      - TF_WORKSPACE or .terraform/environment in the current directory
#   dir       - a path component named prod/prd/production, or REX_PROD_DIRS globs
#
# Override any of these before sourcing this file (e.g. in ~/.zshrc):
#   REX_PROD_NAME_RE  regex for prod-looking names (case-insensitive)
#   REX_PROD_HOST_RE  regex for prod SSH hosts (defaults to REX_PROD_NAME_RE)
#   REX_PROD_HOSTS    array of hosts or globs that are prod whatever their name,
#                     e.g. (bastion.example.org '*.live.example.org'). Lines from
#                     REX_PROD_HOSTS_FILE (default ~/.config/rex/prod-hosts, one
#                     per line, # comments) are added; context-watch.lua reads
#                     the same file. SSH aliases are resolved with `ssh -G`.
#   REX_PROD_DIRS     array of extra directory globs, e.g. (~/src/infra/live/*)
#   REX_LOCAL_HOSTS   array of short hostnames that count as local. When unset,
#                     macOS counts as local and anything else as remote. A shell
#                     reached over SSH (SSH_CONNECTION/SSH_CLIENT/SSH_TTY) is
#                     always remote.

[[ -n $REX_BLOCK && -n $REX_SESSION ]] || return 0
(( $+commands[rex] && $+commands[jq] )) || return 0

: ${REX_PROD_NAME_RE:='(^|[^[:alnum:]])(prod|prd|production)([^[:alnum:]]|$)'}
: ${REX_PROD_HOST_RE:=$REX_PROD_NAME_RE}
(( ${+REX_PROD_DIRS} )) || typeset -ga REX_PROD_DIRS=()
(( ${+REX_PROD_HOSTS} )) || typeset -ga REX_PROD_HOSTS=()
: ${REX_PROD_HOSTS_FILE:=${XDG_CONFIG_HOME:-$HOME/.config}/rex/prod-hosts}

_rex_prod_load_hosts() {
  [[ -r $REX_PROD_HOSTS_FILE ]] || return
  local line
  while IFS= read -r line || [[ -n $line ]]; do
    line=${${line%%\#*}//[[:space:]]/}
    [[ -n $line ]] && REX_PROD_HOSTS+=(${(L)line})
  done < $REX_PROD_HOSTS_FILE
}
_rex_prod_load_hosts

typeset -g REX_PROD_REASON=''   # read by the p10k segment
typeset -g _rex_prod_last_label=''

_rex_prod_matches() {  # $1 = regex, $2 = text; case-insensitive
  [[ ${(L)2} =~ ${(L)1} ]]
}

_rex_prod_kube_context() {
  local cfg=${${KUBECONFIG:-$HOME/.kube/config}%%:*} line
  [[ -r $cfg ]] || return
  while IFS= read -r line; do
    if [[ $line == current-context:* ]]; then
      line=${line#current-context:}; line=${line//[\"\' ]/}
      print -r -- $line; return
    fi
  done < $cfg
}

_rex_prod_remote_host() {  # short hostname if this shell runs remotely, else nothing
  local h=${HOST%%.*}
  if [[ -n $SSH_CONNECTION || -n $SSH_CLIENT || -n $SSH_TTY ]]; then
    print -r -- $h
  elif (( ${+REX_LOCAL_HOSTS} )); then
    (( ${REX_LOCAL_HOSTS[(Ie)$h]} )) || print -r -- $h
  elif [[ $OSTYPE != darwin* ]]; then
    print -r -- $h
  fi
}
typeset -g _rex_prod_remote=$(_rex_prod_remote_host)   # fixed for the shell's life

_rex_prod_tofu_workspace() {
  if [[ -n $TF_WORKSPACE ]]; then print -r -- $TF_WORKSPACE
  elif [[ -r .terraform/environment ]]; then print -r -- "$(<.terraform/environment)"
  fi
}

_rex_prod_set_label() {
  [[ $1 == $_rex_prod_last_label ]] && return
  _rex_prod_last_label=$1
  # Synchronous (~30 ms, only on change) so labels can't arrive out of order.
  rex --timeout 2s api call -s "$REX_SESSION" session.set_block_label \
    "$(jq -cn --arg b "$REX_BLOCK" --arg l "$1" '{block_id:$b,label:$l}')" >/dev/null 2>&1
}

_rex_prod_ssh_target() {  # host an ssh/mosh command line connects to, or nothing
  local -a words=(${(z)1})
  [[ ${words[1]} == (ssh|mosh) ]] || return
  local i=2 w
  while (( i <= $#words )); do
    w=${words[i]}
    if [[ $w == --* ]]; then ;                       # long option (mosh)
    elif [[ $w == -[bcDEeFIiJLlmOoPpQRSWw] ]]; then (( i++ ))  # option + argument
    elif [[ $w == -* ]]; then ;                      # flags or -oValue
    else print -r -- ${${w#*@}#ssh://}; return
    fi
    (( i++ ))
  done
}

_rex_prod_host_named() {  # $1 = host; true if its name or REX_PROD_HOSTS mark it prod
  local h=${(L)1} p
  _rex_prod_matches $REX_PROD_HOST_RE $h && return 0
  for p in $REX_PROD_HOSTS; do [[ $h == ${~p} ]] && return 0; done
  return 1
}

_rex_prod_is_prod_host() {  # $1 = ssh target, possibly an ~/.ssh/config alias
  _rex_prod_host_named $1 && return 0
  (( $+commands[ssh] )) || return 1
  local real=${${(M)${(f)"$(ssh -G $1 2>/dev/null)"}:#hostname *}#hostname }
  [[ -n $real && ${(L)real} != ${(L)1} ]] && _rex_prod_host_named $real
}

_rex_prod_reasons() {  # $1 = optional command about to run
  local -a reasons=()
  local v g

  local target=$(_rex_prod_ssh_target "$1")
  [[ -n $target ]] && _rex_prod_is_prod_host $target && reasons+=("ssh $target")

  [[ -n $_rex_prod_remote ]] \
    && { _rex_prod_host_named $_rex_prod_remote || _rex_prod_host_named $HOST; } \
    && reasons+=("host $_rex_prod_remote")

  v=$(_rex_prod_kube_context)
  [[ -n $v ]] && _rex_prod_matches $REX_PROD_NAME_RE $v && reasons+=("kube $v")

  for v in $AWS_PROFILE $AWS_VAULT $AWS_DEFAULT_PROFILE; do
    _rex_prod_matches $REX_PROD_NAME_RE $v && { reasons+=("aws $v"); break; }
  done

  v=$(_rex_prod_tofu_workspace)
  [[ -n $v ]] && _rex_prod_matches $REX_PROD_NAME_RE $v && reasons+=("tofu $v")

  if _rex_prod_matches '/(prod|prd|production)(/|$)' $PWD; then
    reasons+=("dir ${PWD:t}")
  else
    for g in $REX_PROD_DIRS; do
      [[ $PWD == ${~g} || $PWD == ${~g}/* ]] && { reasons+=("dir ${PWD:t}"); break; }
    done
  fi

  print -r -- ${(j:, :)reasons}
}

# Red-shifted text colours for prod panes. Rex honours program-set foreground
# and palette colours (OSC 10 / OSC 4) but not the background, so this recolours
# the text only. Override REX_PROD_FG / REX_PROD_PALETTE before sourcing.
: ${REX_PROD_FG:='#ffd7d7'}
(( ${+REX_PROD_PALETTE} )) || typeset -ga REX_PROD_PALETTE=(
  '#3a1414' '#ff4d4d' '#e0a060' '#ffb070'   # 0 black  1 red  2 green→amber  3 yellow
  '#c07090' '#ff70b0' '#e09090' '#f0c8c8'   # 4 blue→mauve  5 magenta  6 cyan→rose  7 white
  '#805050' '#ff7070' '#f0c080' '#ffd090'   # 8-15: bright variants
  '#e090b0' '#ff90c8' '#f0b0b0' '#ffe8e8'
)
# Yellow-shifted text colours while a sudo/su/doas command runs.
: ${REX_SUDO_FG:='#fff3c4'}
(( ${+REX_SUDO_PALETTE} )) || typeset -ga REX_SUDO_PALETTE=(
  '#2e2810' '#ff8a50' '#c8d060' '#ffd84d'   # 0 black  1 red→orange  2 green→lime  3 yellow
  '#b8a868' '#e0a070' '#d8d090' '#f0e8c0'   # 4 blue→khaki  5 magenta→tan  6 cyan→straw  7 white
  '#807040' '#ffa070' '#e0e080' '#ffe680'   # 8-15: bright variants
  '#d8c890' '#f0b890' '#f0e8a0' '#fffbe0'
)
typeset -g _rex_prod_colored=none

_rex_prod_recolor() {  # $1 = prod, sudo, or none to restore the theme
  [[ $1 == $_rex_prod_colored ]] && return
  _rex_prod_colored=$1
  local i fg seq=$'\e]104\a\e]110\a'   # start from the theme's palette and foreground
  local -a pal
  case $1 in
    prod) fg=$REX_PROD_FG pal=($REX_PROD_PALETTE) ;;
    sudo) fg=$REX_SUDO_FG pal=($REX_SUDO_PALETTE) ;;
  esac
  if [[ -n $fg ]]; then
    seq+=$'\e]10;'"$fg"$'\a'
    for i in {1..${#pal}}; do seq+=$'\e]4;'"$((i-1));${pal[i]}"$'\a'; done
  fi
  printf '%s' "$seq" > /dev/tty
}

_rex_sudo_desc() {  # describes a sudo/su/doas command line, or prints nothing
  local -a words=(${(z)1})
  while [[ ${words[1]} == *=* ]]; do shift words; done   # skip FOO=bar prefixes
  [[ ${words[1]} == (sudo|su|doas) ]] || return
  local w
  if [[ ${words[1]} == su ]]; then
    w=${${words[2,-1]:#-*}[1]}
    [[ -z $w || $w == root ]] && print 'root shell' || print -r -- "shell as $w"
    return
  fi
  shift words
  while [[ ${words[1]} == -* ]]; do
    [[ ${words[1]} == -([is]|-login|-shell) ]] && { print 'root shell'; return; }
    [[ ${words[1]} == -[ugCDhpRrTt] ]] && shift words   # option + argument
    shift words
  done
  if (( ! $#words )) || [[ ${words[1]} == (su|bash|zsh|sh|fish) ]]; then
    print 'root shell'
  else
    w=${(j: :)words}; print -r -- ${w[1,40]}
  fi
}

_rex_prod_update() {  # $1 = optional command about to run
  REX_PROD_REASON=$(_rex_prod_reasons "$1")
  local sudo=$(_rex_sudo_desc "$1")
  if [[ -n $REX_PROD_REASON ]]; then _rex_prod_recolor prod
  elif [[ -n $sudo ]]; then          _rex_prod_recolor sudo
  else                               _rex_prod_recolor none
  fi
  if [[ -n $REX_PROD_REASON ]]; then
    _rex_prod_set_label "🔴 PROD${sudo:+ · SUDO} · $REX_PROD_REASON"
  elif [[ -n $sudo ]]; then
    _rex_prod_set_label "🟡 SUDO · $sudo"
  elif [[ -n $(_rex_prod_ssh_target "$1") ]]; then
    _rex_prod_set_label "🌐 $(_rex_prod_ssh_target "$1")"
  elif [[ -n $_rex_prod_remote ]]; then
    _rex_prod_set_label "🌐 $_rex_prod_remote · ${${PWD/#$HOME/~}:t}"
  elif [[ $PWD == $HOME ]]; then
    _rex_prod_set_label "💻 local · ~"
  else
    _rex_prod_set_label "💻 local · ${PWD:t}"
  fi
}

_rex_prod_precmd()  { _rex_prod_update; }
_rex_prod_preexec() {
  [[ ${1%% *} == (ssh|mosh) || -n $(_rex_sudo_desc "$1") ]] && _rex_prod_update "$1"
}

# Run before p10k's own precmd so the segment sees the fresh state.
precmd_functions=(_rex_prod_precmd ${precmd_functions:#_rex_prod_precmd})
preexec_functions+=(_rex_prod_preexec)

# Powerlevel10k segment: white-on-red "PROD <reason>" at the start of the prompt.
prompt_rex_prod() {
  [[ -n $REX_PROD_REASON ]] || return
  p10k segment -b 1 -f 15 -i '⚠' -t "PROD ${REX_PROD_REASON}"
}
if (( ${+POWERLEVEL9K_LEFT_PROMPT_ELEMENTS} )) &&
   (( ! ${POWERLEVEL9K_LEFT_PROMPT_ELEMENTS[(Ie)rex_prod]} )); then
  POWERLEVEL9K_LEFT_PROMPT_ELEMENTS=(rex_prod $POWERLEVEL9K_LEFT_PROMPT_ELEMENTS)
  (( $+functions[p10k] )) && p10k reload 2>/dev/null
fi
