import {
  cp,
  lstat,
  mkdir,
  readFile,
  readdir,
  writeFile,
} from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export async function validateWebRelease(surface, root = repository) {
  if (!["site", "staff"].includes(surface))
    throw new Error("Choose exactly one website: site or staff");
  const source = resolve(root, "dist", surface);
  let release;
  try {
    release = JSON.parse(
      await readFile(resolve(source, ".vite/release.json"), "utf8"),
    );
  } catch {
    throw new Error(
      "Missing website release metadata; rebuild with build:release:public or build:release:staff",
    );
  }
  if (
    release.version !== 1 ||
    release.dataMode !== "api" ||
    release.apiBase !== "/api" ||
    release.surface !== (surface === "site" ? "public" : "staff")
  )
    throw new Error(
      "Only an API website with the selected audience and /api proxy can be published",
    );
  const manifest = JSON.parse(
    await readFile(resolve(source, ".vite/manifest.json"), "utf8"),
  );
  if (
    Object.entries(manifest).some(([key, chunk]) =>
      [
        key,
        chunk.src,
        ...(chunk.imports || []),
        ...(chunk.dynamicImports || []),
      ]
        .filter(Boolean)
        .some((name) => name.startsWith("src/app/providers/demo")),
    )
  )
    throw new Error(
      "Demo transport found in production website; rebuild in API mode",
    );
  return manifest;
}

export async function packageWeb(surface, destination, root = repository) {
  if (!["site", "staff"].includes(surface))
    throw new Error("Choose exactly one website: site or staff");
  const source = resolve(root, "dist", surface);
  const target = resolve(root, destination);
  const output = resolve(root, "output");
  if (!target.startsWith(`${output}${sep}`))
    throw new Error(
      "The deployment artifact must be a new directory in output/",
    );
  const manifest = await validateWebRelease(surface, root);
  const pages = Object.keys(manifest).filter((key) =>
    key.startsWith("src/pages/"),
  );
  const includes = (name) =>
    pages.some((key) => key.startsWith(`src/pages/${name}/`));
  const publicPages = [
    "catalog",
    "resort-profile",
    "room-profile",
    "guest-auth",
    "guest-profile",
  ];
  const staffPages = [
    "workspace",
    "analytics",
    "staff-guest",
    "login",
    "accounting",
  ];
  const required = surface === "site" ? publicPages : staffPages;
  const forbidden = surface === "site" ? staffPages : publicPages;
  if (required.some((name) => !includes(name)) || forbidden.some(includes))
    throw new Error(
      "Build audience does not match selected website; run build:release",
    );
  const assets = resolve(source, "assets");
  async function validate(path) {
    const stat = await lstat(path);
    if (stat.isSymbolicLink())
      throw new Error("Deployment assets cannot contain symlinks");
    if (stat.isDirectory()) {
      for (const name of await readdir(path)) {
        if (name === ".DS_Store") continue;
        if (name.startsWith(".") || /\.(pem|key|env)$/i.test(name))
          throw new Error("Unexpected private file in website assets");
        await validate(resolve(path, name));
      }
    }
  }
  await validate(resolve(source, "index.html"));
  await validate(assets);
  const config = JSON.parse(
    await readFile(
      resolve(root, surface === "site" ? "vercel.json" : "vercel.staff.json"),
      "utf8",
    ),
  );
  Object.assign(config, {
    framework: null,
    installCommand: null,
    buildCommand: null,
    outputDirectory: ".",
  });
  await mkdir(output, { recursive: true });
  // Never merge into a previous release or copy repository/configuration secrets.
  await mkdir(target);
  await cp(resolve(source, "index.html"), resolve(target, "index.html"));
  await cp(assets, resolve(target, "assets"), {
    recursive: true,
    filter: (path) => !path.endsWith(`${sep}.DS_Store`),
  });
  await writeFile(
    resolve(target, "vercel.json"),
    `${JSON.stringify(config, null, 2)}\n`,
  );
  return target;
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const [, , surface, destination] = process.argv;
  if (!surface || !destination || process.argv.length !== 4) {
    console.error(
      "Usage: node scripts/package-web.mjs <site|staff> output/<new-release>",
    );
    process.exitCode = 1;
  } else {
    try {
      console.log(await packageWeb(surface, destination));
    } catch (error) {
      console.error(error.message);
      process.exitCode = 1;
    }
  }
}
