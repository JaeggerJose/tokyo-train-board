export const meta = {
  name: 'csl-component-framework',
  description: 'Turn csl into a component-composition statusline engine: decoupled named components (tokens/ctx/git/dir/model/clock/jrboard) arranged into multi-row layouts via CSL_ROWS, with byte-identical backward-compat for existing themes',
  phases: [
    { title: '引擎+元件', detail: 'render_classic fallback + CSL_ROWS composer + lib/components.sh built-ins' },
    { title: 'JR元件+主題', detail: 'comp_jrboard/comp_jrtable + jr-status multi-row theme' },
    { title: '全主題驗證', detail: 'backward-compat for existing themes + new multi-line theme' },
  ],
}

const CSL = '/Users/minghsuan/.claude/statusline'
const JRREPO = '/Users/minghsuan/Downloads/JR-timetable'

const CSL_FACTS = `
csl is a bash statusLine theme manager at ${CSL}. Key facts (READ these files first):
- ${CSL}/run.sh : entry. Reads stdin JSON into $input, self-locates SL_DIR, sources lib/paths.sh then lib/render.sh, then the active theme file (which may override functions), then calls \`render "$input"\`.
- ${CSL}/lib/render.sh : defines base ANSI palette + defaults (ART_MODE, SHOW_GIT/STYLE/CTXBAR/RATE/TIME), render_art(), and render() — currently a single function that composes segments (user/dir/git/style/ctx(model+bar+pct)/rate(5h/7d)/time) into ONE line via printf '%b'.
- ${CSL}/lib/paths.sh : theme resolution (repo themes/ + ~/.config/csl/themes/).
- Themes: built-in ${CSL}/themes/*.sh (nord, minimal, blank) and user ${CSL}/themes or ~/.config/csl/themes/*.sh (bastille-day, maplestory, pixel-frames, jr-board, jr-timetable). A theme is sourced AFTER render.sh and may set palette vars / SHOW_* toggles / ART_MODE, or fully override render().
- The Claude statusLine JSON has: .session_id .workspace.current_dir|.cwd .model.display_name .output_style.name .context_window.used_percentage .rate_limits.five_hour.used_percentage .rate_limits.seven_day.used_percentage (NO terminal width field).
- jrboard is a pip-installed Python CLI: \`python3 -m jrboard --mode statusline --claude-stdin --columns N\` prints a one-line board (NO --tokens => pure transit board); \`--mode minitable\` prints a multi-line table. It reads the SAME Claude JSON from stdin.
`

const CONTRACT = `
COMPONENT + LAYOUT CONTRACT (implement EXACTLY):

1) Backward-compat (HARD REQUIREMENT): preserve the CURRENT render() body VERBATIM as a new function \`render_classic()\`. The new \`render()\` dispatches:
     if [ "\${#CSL_ROWS[@]}" -gt 0 ] 2>/dev/null; then _csl_compose "$1"; else render_classic "$1"; fi
   So every existing theme that does NOT set CSL_ROWS renders byte-identically to before. Do not change existing theme files.

2) Components live in a new file ${CSL}/lib/components.sh (sourced by render.sh). Each component is a function:
     comp_<name> "$input" "$columns"   # echoes the rendered segment (ANSI escapes as literal \\033... so the composer's printf '%b' expands them), or echoes nothing when N/A. No global mutation. Never errors out.
   Implement these built-ins (port visuals from render_classic so they match the classic look):
     comp_user  comp_dir  comp_git  comp_model  comp_ctx (model + 10-block bar + pct)  comp_tokens (5h:NN% 7d:NN%)  comp_style  comp_clock
   Parse JSON with jq (same fields render_classic uses). comp_tokens/comp_ctx are the DECOUPLED token/context gauges.

3) Layout: a theme sets:
     CSL_ROWS=( "model ctx tokens git" "jrboard" )   # each element = one output LINE; within a line = ordered component names
     CSL_SEP=" · "                                    # optional within-row separator (default " · ")
   \`_csl_compose\` (in render.sh): for each row, split on spaces into names; for each name run \`comp_<name> "$input" "$cols"\`; collect non-empty results; join with CSL_SEP; join rows with a newline. Call render_art once first (top). Use printf '%b'. Unknown component name => skip silently. An all-empty row => omit the line (no blank line).

4) Columns: pass a per-row width to components (default: a sane fixed width like 80, or honor a CSL_COLUMNS var). Components that don't care ignore it; comp_jrboard/comp_jrtable pass it as --columns.
`

phase('引擎+元件')
const engine = await agent(
  `Refactor the csl engine into a component composer WITHOUT breaking existing themes. ${CSL_FACTS}\n\n${CONTRACT}\n\n` +
  `Tasks:\n` +
  `1. Back up ${CSL}/lib/render.sh to ${CSL}/lib/render.sh.precompose.bak (copy, for safety).\n` +
  `2. In render.sh: rename the existing render() body to render_classic() VERBATIM (no logic change). Add the new dispatching render() per contract item (1). Source lib/components.sh near the top (after the palette defaults). Add _csl_compose() per contract item (3).\n` +
  `3. Create ${CSL}/lib/components.sh with comp_user/dir/git/model/ctx/tokens/style/clock per contract item (2), matching the classic visuals/colours (reuse the T_* palette vars and SEP from render.sh).\n` +
  `4. Verify backward-compat NOW: pipe a sample Claude JSON through \`bash ${CSL}/run.sh nord\` and \`bash ${CSL}/run.sh minimal\` BEFORE-vs-AFTER and confirm output is byte-identical to render_classic (since they set no CSL_ROWS). Also confirm a throwaway theme that sets CSL_ROWS=("model ctx tokens" "user dir") produces TWO lines with the named components.\n` +
  `Return the exact component function names, the render() dispatch snippet, and the byte-identical proof.`,
  { label: 'engine', phase: '引擎+元件', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      components: { type: 'array', items: { type: 'string' } },
      backward_compatible: { type: 'boolean' },
      multiline_works: { type: 'boolean' },
      files: { type: 'array', items: { type: 'string' } },
      notes: { type: 'string' },
    },
    required: ['components', 'backward_compatible', 'multiline_works'],
  } }
)
log(`engine: components=${(engine?.components||[]).join(',')} bc=${engine?.backward_compatible} ml=${engine?.multiline_works}`)

phase('JR元件+主題')
const theme = await agent(
  `Add the JR transit components and a multi-row theme to csl. ${CSL_FACTS}\n\n${CONTRACT}\n\n` +
  `The engine now supports components (from phase 1): ${JSON.stringify(engine?.components ?? [])}, and CSL_ROWS layout.\n\n` +
  `Tasks:\n` +
  `1. Add to ${CSL}/lib/components.sh:\n` +
  `   comp_jrboard "$input" "$cols": printf '%s' "$input" | python3 -m jrboard --mode statusline --claude-stdin --columns "\${cols:-80}" 2>/dev/null   (NO --tokens — the transit board only; tokens are the separate comp_tokens). Echo nothing on failure.\n` +
  `   comp_jrtable "$input" "$cols": same but --mode minitable (multi-line board). \n` +
  `   Both must pass the JSON via STDIN (never argv) and tolerate jrboard being absent (echo nothing).\n` +
  `2. Create theme ${CSL}/themes-or-config -> write to ~/.config/csl/themes/jr-status.sh + jr-status.json manifest. The .sh sets:\n` +
  `     CSL_ROWS=( "model ctx tokens" "jrboard" )   # row1 = session/token components, row2 = the JR marquee\n` +
  `     CSL_SEP=" · " ; CSL_COLUMNS default ~90 ; allow JR_CITY/JR_BY_SESSION-style overrides to flow to comp_jrboard if easy (optional).\n` +
  `   It must NOT override render() (it relies on the composer). Add comments showing how to reorder/add components (e.g. CSL_ROWS=("jrboard" "model ctx tokens git")).\n` +
  `3. Mirror the theme files into the repo at ${JRREPO}/integrations/csl/jr-status.{sh,json} (copies).\n` +
  `4. Verify: pipe a sample Claude JSON through \`bash ${CSL}/run.sh jr-status\` and show the TWO-LINE output (row1 model/ctx/tokens, row2 JR board). Strip ANSI in the pasted excerpt.\n` +
  `Return the theme path + the rendered 2-line sample.`,
  { label: 'jr-theme', phase: 'JR元件+主題', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      files: { type: 'array', items: { type: 'string' } },
      sample_output: { type: 'string' },
      notes: { type: 'string' },
    },
    required: ['files', 'sample_output'],
  } }
)
log(`theme: ${(theme?.files||[]).join(', ')}`)

phase('全主題驗證')
const verify = await agent(
  `Verify the csl component refactor did not break anything and the new layout works. ${CSL_FACTS}\n\n` +
  `Use a realistic sample Claude statusLine JSON (session_id, model.display_name, workspace.current_dir, context_window.used_percentage=72, rate_limits.five_hour.used_percentage=20, seven_day.used_percentage=27). Save to /tmp/cc.json.\n\n` +
  `Do and paste evidence (strip ANSI with sed 's/\\x1b\\[[0-9;]*m//g' in excerpts):\n` +
  `1. BACKWARD-COMPAT: for EACH existing theme that sets no CSL_ROWS — nord, minimal, blank, and any user themes (bastille-day, maplestory, pixel-frames, jr-board, jr-timetable) — run \`cat /tmp/cc.json | bash ${CSL}/run.sh <theme>\` and confirm it still renders (single line as before, no errors, no stray blank lines). Compare against ${CSL}/lib/render.sh.precompose.bak behaviour if useful. Report any theme whose output changed and FIX the engine (not the theme) so classic output is preserved.\n` +
  `2. NEW: \`cat /tmp/cc.json | bash ${CSL}/run.sh jr-status\` => confirm TWO lines: row1 = model+ctx-bar+5h/7d tokens, row2 = the JR board. \n` +
  `3. RECOMPOSE: temporarily set CSL_ROWS=("jrboard" "model ctx tokens git") in a scratch copy and confirm the ORDER/rows change accordingly (proves decoupled + arrangeable). \n` +
  `4. EMPTY-COMPONENT: feed JSON missing rate_limits => comp_tokens disappears with no leftover separator/blank line.\n` +
  `5. Do NOT change the user's ACTIVE theme (leave settings.json untouched). \n` +
  `6. If jrboard isn't importable in this shell, note it; the board component should degrade to empty without breaking the row.\n` +
  `Report per-theme pass/fail, fixes applied, and the new jr-status 2-line sample.`,
  { label: 'verify', phase: '全主題驗證', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      themes_checked: { type: 'array', items: { type: 'object', properties: { theme: { type: 'string' }, ok: { type: 'boolean' }, note: { type: 'string' } }, required: ['theme', 'ok'] } },
      jr_status_multiline: { type: 'boolean' },
      recompose_works: { type: 'boolean' },
      fixes: { type: 'array', items: { type: 'string' } },
      summary: { type: 'string' },
    },
    required: ['themes_checked', 'jr_status_multiline', 'summary'],
  } }
)

return { engine, theme, verify }
