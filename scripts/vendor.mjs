import { mkdir, cp, readFile, writeFile } from "node:fs/promises";
await mkdir("vendor/leaflet", { recursive: true });
for (const file of ["leaflet.js", "leaflet.css", "images"])
  await cp(`node_modules/leaflet/dist/${file}`, `vendor/leaflet/${file}`, {
    recursive: true,
  });
await cp("node_modules/leaflet/LICENSE", "vendor/leaflet/LICENSE");
// Keep generated vendor text identical across macOS and Linux CI.
for (const file of ["leaflet.js", "leaflet.css", "LICENSE"]) {
  const path = `vendor/leaflet/${file}`;
  await writeFile(path, (await readFile(path, "utf8")).replace(/\r\n/g, "\n"));
}
