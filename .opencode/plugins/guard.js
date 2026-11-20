// Guardrails for OpenCode: ask scripts/guard.py before every tool call and throw its reason
// when the call is blocked. The decisions live in scripts/guard.py (see docs/reference/guardrails.md).
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"

const script = fileURLToPath(new URL("../../scripts/guard.py", import.meta.url))

// A plain object: no package import (only Node built-ins), so a fresh clone needs no package install.
export default {
  id: "guardrails",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", (event) => {
      let answer
      try {
        const run = spawnSync("python3", [script, "--agent", "opencode"], {
          input: JSON.stringify({ tool: event.tool, args: event.input, cwd: ctx.location.directory }),
          encoding: "utf8",
          timeout: 30000,
        })
        if (run.status !== 0) return // a broken guard never blocks the agent
        answer = JSON.parse(run.stdout)
      } catch {
        return
      }
      if (answer.decision !== "allow") throw new Error(answer.reason)
    })
  },
}
