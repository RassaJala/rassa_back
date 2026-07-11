// pg-mcp.ts — Wrapper cross-platform para PostgreSQL MCP
// Carga DATABASE_URL del .env (via --env-file=.env) y solo expone POSTGRES_URL al child.
// Funciona en Linux, macOS y Windows porque Bun es cross-platform.

const url = Bun.env.DATABASE_URL;
if (!url) {
  console.error(
    "DATABASE_URL no está definida. " +
      "Asegurate de que back/.env existe y se carga con --env-file=.env",
  );
  process.exit(1);
}

const child = Bun.spawn(
  ["bunx", "-y", "@modelcontextprotocol/server-postgres@latest", url],
  {
    env: { ...process.env, POSTGRES_URL: url },
    stdio: ["inherit", "inherit", "inherit"],
  },
);

await child.exited;
process.exit(child.exitCode ?? 0);
