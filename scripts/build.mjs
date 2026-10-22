import { cp, mkdir, rm } from "node:fs/promises";
await rm("dist/site", { recursive: true, force: true });
await mkdir("dist/site", { recursive: true });
for (const file of ["index.html", "styles.css", "src", "assets", "vendor"])
  await cp(file, `dist/site/${file}`, { recursive: true });
console.log(
  "Static site ready: dist/site. Deploy these files to a static host.",
);
