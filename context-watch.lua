-- context-watch.lua: label Rex panes by what is actually running in them.
--
-- Run with:  rex do --all context-watch.lua
--
-- Companion to prod-highlight.zsh. The zsh hook only sees commands typed into
-- a hooked zsh. This watcher looks at each pane's foreground process and its
-- parents, as Rex reports them, so it also catches:
--   * remote sessions started through aliases, functions or scripts
--     (ssh, mosh, et, autossh, kubectl exec/attach/debug, docker/podman
--     exec/attach/run, aws ssm, tailscale ssh)
--   * root shells and sudo in any shell, including bash, and in panes
--     started directly with a program
--   * a second hop through a bastion: while an ssh session runs, a shell on
--     the far side that reports its directory (OSC 7, file://host/path) names
--     the host the pane is really on, so "ssh bastion" then "ssh db1.prod"
--     is labeled PROD
--
-- Labels use the same scheme as the hook:
--   🔴 PROD · …   remote target looks like production
--   🟡 SUDO · …   something in the pane runs as root via sudo/su/doas
--   🌐 …          remote session
--
-- It never downgrades a label: it only replaces a label that signals less
-- (🔴 > 🟡 > 🌐/🟢 > anything else), and when the context ends it restores the
-- previous label, but only if nobody changed the label in the meantime.
-- It can't recolor text; only the zsh hook can do that.

-- Words that mark a host as production, matched against the host name split
-- on non-alphanumeric characters (so "db1.prod.example" and "web-prd-2" match,
-- "product" doesn't). Keep in step with REX_PROD_NAME_RE in the zsh hook.
local PROD_WORDS = { prod = true, prd = true, production = true }

-- Hosts that are prod whatever their name: one host or glob (* and ?) per line
-- in ~/.config/rex/prod-hosts, # starts a comment. The zsh hook reads the same
-- file. Read once at startup; restart the watcher after editing it.
local PROD_HOSTS_FILE = (os.getenv("XDG_CONFIG_HOME") or ((os.getenv("HOME") or "") .. "/.config"))
  .. "/rex/prod-hosts"

local function glob_to_pattern(glob)
  return "^" .. glob:gsub("[%^%$%(%)%%%.%[%]%+%-]", "%%%0"):gsub("%*", ".*"):gsub("%?", ".") .. "$"
end

local PROD_HOST_PATTERNS = {}
do
  local f = io.open(PROD_HOSTS_FILE, "r")
  if f then
    for line in f:lines() do
      line = line:gsub("#.*", ""):gsub("%s+", ""):lower()
      if line ~= "" then PROD_HOST_PATTERNS[#PROD_HOST_PATTERNS + 1] = glob_to_pattern(line) end
    end
    f:close()
  end
end

-- Processes that always mean a remote session, and ones that do only with
-- certain subcommands (checked against the process's arguments).
local REMOTE_ALWAYS = {
  ssh = true, ["mosh-client"] = true, et = true, autossh = true,
  ["session-manager-plugin"] = true,
}
local REMOTE_SUBCOMMANDS = {
  kubectl = { exec = true, attach = true, debug = true },
  docker  = { exec = true, attach = true, run = true },
  podman  = { exec = true, attach = true, run = true },
  aws     = { ssm = true },
  tailscale = { ssh = true },
}
local SUDO_NAMES = { sudo = true, su = true, doas = true }
local SHELLS = { sh = true, bash = true, zsh = true, fish = true, dash = true, ksh = true, tcsh = true }

local function severity(label)
  if not label then return 0 end
  if label:find("^🔴") then return 3 end
  if label:find("^🟡") then return 2 end
  if label:find("^🌐") or label:find("^🟢") then return 1 end
  return 0
end

local function named_prod(host)
  host = host:lower()
  for word in host:gmatch("%w+") do
    if PROD_WORDS[word] then return true end
  end
  for _, pat in ipairs(PROD_HOST_PATTERNS) do
    if host:find(pat) then return true end
  end
  return false
end

-- Also resolves ~/.ssh/config aliases with `ssh -G`; cached per host because
-- process events fire often.
local prod_cache = {}
local function is_prod(host)
  if prod_cache[host] ~= nil then return prod_cache[host] end
  local result = named_prod(host)
  if not result then
    local r = rex.exec({ "ssh", "-G", host }, { timeout = 2 })
    local real = r and r.ok and r.stdout:match("\nhostname (%S+)") or r and r.ok and r.stdout:match("^hostname (%S+)")
    if real and real:lower() ~= host:lower() then result = named_prod(real) end
  end
  prod_cache[host] = result
  return result
end

local function argv_of(pid)
  local r = rex.exec({ "ps", "-o", "args=", "-p", tostring(pid) }, { timeout = 2 })
  if not r or not r.ok then return {} end
  local words = {}
  for w in r.stdout:gmatch("%S+") do words[#words + 1] = w end
  return words
end

-- Target host of an ssh command line: the first non-option word, skipping the
-- arguments of options that take one. Also returns the options before it.
local SSH_OPTS_WITH_ARG = "bcDEeFIiJLlmOoPpQRSWw"
local function ssh_host(argv)
  local i = 2
  while i <= #argv do
    local w = argv[i]
    if w:sub(1, 1) == "-" then
      if #w == 2 and SSH_OPTS_WITH_ARG:find(w:sub(2, 2), 1, true) then i = i + 1 end
    else
      local opts = {}
      for j = 2, i - 1 do opts[#opts + 1] = argv[j] end
      return (w:gsub("^ssh://", ""):gsub("^.*@", "")), opts
    end
    i = i + 1
  end
end

-- The host an ssh target really connects to, from `ssh -G` with the session's
-- own options, so ~/.ssh/config aliases, -F and -o HostName= all count.
-- Lower-cased; nil if it can't be resolved. Cached per command line.
local real_cache = {}
local function ssh_real(host, opts)
  local key = table.concat(opts or {}, "\0") .. "\0" .. host
  if real_cache[key] == nil then
    local cmd = { "ssh", "-G" }
    for _, o in ipairs(opts or {}) do cmd[#cmd + 1] = o end
    cmd[#cmd + 1] = host
    local r = rex.exec(cmd, { timeout = 2 })
    local real = r and r.ok and (r.stdout:match("\nhostname (%S+)") or r.stdout:match("^hostname (%S+)"))
    real_cache[key] = real and real:lower() or false
  end
  return real_cache[key] or nil
end

-- Host named by an OSC 7 directory report (file://host/path), or nil.
local function pwd_host(pwd)
  local host = type(pwd) == "string" and pwd:match("^file://([^/]+)")
  if host and host ~= "" then return host:lower() end
end

local function short(host) return (host or ""):lower():match("^[^.]*") end

-- Is a reported host the first hop itself? It may report the name typed after
-- ssh, or the real host name an alias stands for.
local function is_first_hop(reported, remote)
  local s = short(reported)
  return s == short(remote.host) or (remote.real ~= nil and s == short(remote.real))
end

-- Describe a remote session for one process, or nil.
local function remote_of(p)
  local name = p.name or ""
  if REMOTE_ALWAYS[name] then
    if name == "ssh" or name == "autossh" then
      local host, opts = ssh_host(argv_of(p.pid))
      if host then return { pid = p.pid, host = host, real = ssh_real(host, opts), what = "ssh " .. host } end
      return { pid = p.pid, what = name }
    end
    if name == "session-manager-plugin" then return { pid = p.pid, what = "aws ssm" } end
    if name == "mosh-client" then return { pid = p.pid, what = "mosh" } end
    return { pid = p.pid, what = name }
  end
  local subs = REMOTE_SUBCOMMANDS[name]
  if subs then
    local argv = argv_of(p.pid)
    for i = 2, #argv do
      if subs[argv[i]] then return { pid = p.pid, what = name .. " " .. argv[i] } end
    end
  end
end

-- What the pane is doing: { sev = 0..3, label = "…", remote = {…} or nil }.
-- nested is the host the far side last reported with OSC 7, or nil.
local function classify(ev, nested)
  local chain = {}
  -- ancestors are listed nearest first; walk from the terminal's child out to
  -- the foreground process. Skip login, which always runs as root.
  local anc = ev.ancestors or {}
  for i = #anc, 1, -1 do
    if anc[i].name ~= "login" then chain[#chain + 1] = anc[i] end
  end
  if ev.foreground then chain[#chain + 1] = ev.foreground end

  local remote, sudo
  for _, p in ipairs(chain) do
    remote = remote or remote_of(p)
    if SUDO_NAMES[p.name or ""] or p.user_id == 0 then sudo = true end
  end

  local fg = ev.foreground or {}
  local fgname = fg.name or "?"
  local sudo_what
  if fg.user_id == 0 then
    sudo_what = SHELLS[fgname] and "root shell" or fgname
  elseif SUDO_NAMES[fgname] then
    sudo_what = fgname                                 -- e.g. at the password prompt
  elseif SHELLS[fgname] then
    sudo_what = "shell as " .. (fg.user or "?")        -- su to another user
  else
    sudo_what = fgname
  end

  -- A reported host other than the first hop means a further hop (a bastion).
  local via
  if remote and nested and not is_first_hop(nested, remote) then via = nested end

  if remote and ((via and is_prod(via)) or (not via and remote.host and is_prod(remote.host))) then
    local where = via and (via .. " via " .. remote.what) or remote.what
    return { sev = 3, remote = remote, via = via, label = "🔴 PROD" .. (sudo and " · SUDO" or "") .. " · " .. where }
  end
  if sudo then
    return { sev = 2, remote = remote, label = "🟡 SUDO · " .. sudo_what .. (remote and (" · " .. remote.what) or "") }
  end
  if remote then
    return { sev = 1, remote = remote, via = via, label = "🌐 " .. (via and (via .. " via " .. remote.what) or remote.what) }
  end
  return { sev = 0 }
end

-- The block's current label, from the session's view.
local function find_label(node, block_id)
  if type(node) ~= "table" then return nil end
  if node.block_id == block_id and node.label then return node.label end
  for _, v in pairs(node) do
    local found = find_label(v, block_id)
    if found then return found end
  end
end

local function current_label(ctx)
  local view = rex.session.view{ session_id = ctx.session_id }
  return view and find_label(view, ctx.block_id)
end

local function set_label(ctx, label)
  rex.session.set_block_label{ session_id = ctx.session_id, block_id = ctx.block_id, label = label }
end

-- Per block: the label this watcher set, and the one it replaced.
local mine = {}
-- Per block: the last process event, and the host the current remote session
-- last reported with OSC 7 (forgotten when that session ends).
local last_ev, nested = {}, {}

local function apply(ctx, c)
  local cur = current_label(ctx)
  local st = mine[ctx.block_id]
  local owned = st and cur == st.set

  if c.sev > 0 then
    if owned and not c.via and st.prev and c.sev <= severity(st.prev) then
      -- Back on the first hop and no stronger than the label we replaced: hand it back.
      set_label(ctx, st.prev); mine[ctx.block_id] = nil
    elseif owned then
      if c.label ~= cur then set_label(ctx, c.label); st.set = c.label end
    elseif c.sev > severity(cur) then
      mine[ctx.block_id] = { set = c.label, prev = cur }
      set_label(ctx, c.label)
    end
  else
    if owned then set_label(ctx, st.prev or "") end
    mine[ctx.block_id] = nil
  end
end

rex.on("terminal.process_changed", function(ctx, ev)
  last_ev[ctx.block_id] = ev
  local n = nested[ctx.block_id]
  local c = classify(ev, n and n.host)
  -- A different (or no) remote session: forget what the old one reported.
  if not c.remote or not n or n.pid ~= c.remote.pid then
    nested[ctx.block_id] = nil
    c = classify(ev, nil)
  end
  apply(ctx, c)
end)

rex.on("terminal.pwd_changed", function(ctx, ev)
  local ev_p = last_ev[ctx.block_id]
  local host = pwd_host(ev and ev.pwd)
  if not ev_p or not host then return end
  local c = classify(ev_p, nil)
  if not c.remote then return end          -- a local shell reporting its own directory
  nested[ctx.block_id] = { pid = c.remote.pid, host = host }
  apply(ctx, classify(ev_p, host))
end)

rex.on("block_closed", function(ctx, ev)
  local id = ev.block_id or ctx.block_id or ""
  mine[id], last_ev[id], nested[id] = nil, nil, nil
end)
