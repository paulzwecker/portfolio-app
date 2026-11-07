import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function localLinks(markdown) {
  const prose = markdown.replace(
    /^\s*(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\s*\1\s*$/gm,
    "",
  );
  return [...prose.matchAll(/\]\((<[^>]+>|[^)\s]+)(?:\s+"[^"]*")?\)/g)]
    .map((match) => match[1].replace(/^<|>$/g, "").split("#")[0])
    .filter((target) => target && !/^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(target))
    .map((target) => decodeURIComponent(target));
}

function main() {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const tracked = execFileSync("git", ["ls-files", "-z"], {
    cwd: root,
    encoding: "utf8",
  })
    .split("\0")
    .filter(Boolean);
  const known = new Set(tracked.map((file) => path.resolve(root, file)));
  let sparse = false;
  try {
    sparse =
      execFileSync("git", ["config", "--bool", "core.sparseCheckout"], {
        cwd: root,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim() === "true";
  } catch {
    /* A full checkout has no sparse setting. */
  }
  let checked = 0;
  let skipped = 0;
  const errors = [];
  for (const file of tracked.filter((name) => name.endsWith(".md"))) {
    const source = path.resolve(root, file);
    if (!existsSync(source)) {
      if (sparse) {
        skipped++;
        continue;
      }
      errors.push(`${file} is missing`);
      continue;
    }
    checked++;
    for (const target of localLinks(readFileSync(source, "utf8"))) {
      const resolved = path.resolve(path.dirname(source), target);
      if (existsSync(resolved)) continue;
      if (sparse && known.has(resolved)) {
        skipped++;
        continue;
      }
      errors.push(`${file} -> ${target}`);
    }
  }
  for (const error of errors) console.error(error);
  console.log(
    `Markdown files checked ${checked}; sparse files/targets skipped ${skipped}; broken links ${errors.length}`,
  );
  process.exitCode = errors.length ? 1 : 0;
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
)
  main();
