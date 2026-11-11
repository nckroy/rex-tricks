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
--
-- Labels use the same scheme as the hook:
--   🔴 PROD · …   remote target looks like production
--   🟡 SUDO · …   something in the pane runs as root via sudo/su/doas
--   🌐 …          remote session
--
-- It never downgrades a label: it only replaces a label that signals less
-- (🔴 > 🟡 > 🌐/🟢 > anything else), and when the context ends it restores the
-- previous label, but only if nobody changed the label in the meantime.
-- It can't recolour text; only the zsh hook can do that.

-- Words that mark a host as production, matched against the host name split
-- on non-alphanumeric characters (so "db1.prod.example" and "web-prd-2" match,
-- "product" doesn't). Keep in step with REX_PROD_NAME_RE in the zsh hook.
local PROD_WORDS = { prod = true, prd = true, production = true }

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

local function is_prod(host)
  for word in host:lower():gmatch("%w+") do
    if PROD_WORDS[word] then return true end
  end
  return false
end

local function argv_of(pid)
  local r = rex.exec({ "ps", "-o", "args=", "-p", tostring(pid) }, { timeout = 2 })
  if not r or not r.ok then return {} end
  local words = {}
  for w in r.stdout:gmatch("%S+") do words[#words + 1] = w end
  return words
end

-- Target host of an ssh command line: the first non-option word, skipping the
-- arguments of options that take one.
local SSH_OPTS_WITH_ARG = "bcDEeFIiJLlmOoPpQRSWw"
local function ssh_host(argv)
  local i = 2
  while i <= #argv do
    local w = argv[i]
    if w:sub(1, 1) == "-" then
      if #w == 2 and SSH_OPTS_WITH_ARG:find(w:sub(2, 2), 1, true) then i = i + 1 end
    else
      return (w:gsub("^ssh://", ""):gsub("^.*@", ""))
    end
    i = i + 1
  end
end

-- Describe a remote session for one process, or nil.
local function remote_of(p)
  local name = p.name or ""
  if REMOTE_ALWAYS[name] then
    if name == "ssh" or name == "autossh" then
      local host = ssh_host(argv_of(p.pid))
      if host then return { host = host, what = "ssh " .. host } end
      return { what = name }
    end
    if name == "session-manager-plugin" then return { what = "aws ssm" } end
    if name == "mosh-client" then return { what = "mosh" } end
    return { what = name }
  end
  local subs = REMOTE_SUBCOMMANDS[name]
  if subs then
    local argv = argv_of(p.pid)
    for i = 2, #argv do
      if subs[argv[i]] then return { what = name .. " " .. argv[i] } end
    end
  end
end

-- What the pane is doing: { sev = 0..3, label = "…" }.
local function classify(ev)
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

  if remote and remote.host and is_prod(remote.host) then
    return { sev = 3, label = "🔴 PROD" .. (sudo and " · SUDO" or "") .. " · " .. remote.what }
  end
  if sudo then
    return { sev = 2, label = "🟡 SUDO · " .. sudo_what .. (remote and (" · " .. remote.what) or "") }
  end
  if remote then return { sev = 1, label = "🌐 " .. remote.what } end
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

rex.on("terminal.process_changed", function(ctx, ev)
  local c = classify(ev)
  local cur = current_label(ctx)
  local st = mine[ctx.block_id]
  local owned = st and cur == st.set

  if c.sev > 0 then
    if owned then
      if c.label ~= cur then set_label(ctx, c.label); st.set = c.label end
    elseif c.sev > severity(cur) then
      mine[ctx.block_id] = { set = c.label, prev = cur }
      set_label(ctx, c.label)
    end
  else
    if owned then set_label(ctx, st.prev or "") end
    mine[ctx.block_id] = nil
  end
end)

rex.on("block_closed", function(ctx, ev)
  mine[ev.block_id or ctx.block_id or ""] = nil
end)
