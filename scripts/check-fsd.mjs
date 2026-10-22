import { graph, slice } from "./source-graph.mjs";
const { files, edges } = await graph();
const layers = ["app", "pages", "widgets", "features", "entities", "shared"];
const errors = [];
for (const file of files)
  if (!layers.includes(file.split("/")[0]))
    errors.push(`Unknown layer: ${file}`);
for (const { from, to } of edges) {
  const a = from.split("/"),
    b = to.split("/");
  if (a[0] === b[0] && (a[0] === "app" || a[0] === "shared")) continue;
  if (slice(from) === slice(to)) continue;
  if (layers.indexOf(a[0]) >= layers.indexOf(b[0]))
    errors.push(`Forbidden dependency: ${from} -> ${to}`);
  if (b[0] !== "shared" && b[0] !== "app" && b.length !== 3)
    errors.push(`Use slice public API: ${from} -> ${to}`);
}
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else
  console.log(`FSD: ${files.length} files, ${edges.length} imports checked.`);
