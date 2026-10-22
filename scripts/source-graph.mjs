import { readdir, readFile, stat } from "node:fs/promises";
import { resolve, dirname, relative } from "node:path";
const root = resolve("src");
async function walk(dir) {
  const result = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = resolve(dir, entry.name);
    if (entry.isDirectory()) result.push(...(await walk(p)));
    else if (/\.(js|vue)$/.test(entry.name)) result.push(p);
  }
  return result;
}
export function slice(file) {
  const parts = file.split("/");
  return ["app", "shared"].includes(parts[0])
    ? parts[0] === "shared"
      ? parts.slice(0, 2).join("/")
      : parts[0]
    : parts.slice(0, 2).join("/");
}
export async function graph() {
  const paths = (await walk(root)).sort(),
    files = paths.map((p) => relative(root, p));
  const edges = [];
  for (const file of paths) {
    const source = await readFile(file, "utf8");
    const refs = [
      ...source.matchAll(/(?:from\s*|import\s*)(?:['"])([^'"]+)['"]/g),
      ...source.matchAll(/import\(['"]([^'"]+)['"]\)/g),
    ];
    for (const match of refs) {
      const ref = match[1];
      if (!ref.startsWith(".") && !ref.startsWith("@/")) continue;
      if (ref.endsWith(".css")) continue;
      const base = ref.startsWith("@/")
        ? resolve(root, ref.slice(2))
        : resolve(dirname(file), ref);
      let target;
      for (const candidate of [
        base,
        base + ".js",
        base + ".vue",
        resolve(base, "index.js"),
      ]) {
        try {
          if ((await stat(candidate)).isFile()) {
            target = candidate;
            break;
          }
        } catch {}
      }
      if (!target)
        throw new Error(`Missing import: ${relative(root, file)} -> ${ref}`);
      edges.push({ from: relative(root, file), to: relative(root, target) });
    }
  }
  return { files, edges };
}
