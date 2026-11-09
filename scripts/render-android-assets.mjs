import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const namespace = "http://schemas.android.com/apk/res/android";
const header = '<?xml version="1.0" encoding="utf-8"?>\n';
const staffPalette = {
  "#53694A": "#DFE6D0",
  "#344A35": "#F4F3ED",
  "#A87A46": "#D9B88B",
};
const escapeXml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&apos;",
      })[character],
  );

function attributes(source, allowed) {
  const result = {};
  const rest = source.replace(
    /([\w:-]+)\s*=\s*(["'])(.*?)\2/gs,
    (_, name, quote, value) => {
      if (
        !allowed.includes(name) ||
        Object.hasOwn(result, name) ||
        value.includes("&")
      )
        throw new Error(`Unsupported or duplicate SVG attribute: ${name}`);
      result[name] = value;
      return "";
    },
  );
  if (rest.trim()) throw new Error("Invalid SVG attributes");
  return result;
}

// The canonical mark uses paths only. Reject unsupported SVG features instead of
// silently losing transforms, masks or strokes during native asset generation.
function parseLogo(source) {
  const document = source.trim().match(/^<svg\b([^>]*)>([\s\S]*)<\/svg>$/);
  if (!document) throw new Error("Expected a single SVG document");
  const root = attributes(document[1], [
    "xmlns",
    "width",
    "height",
    "viewBox",
    "fill",
  ]);
  const box = (root.viewBox || "")
    .trim()
    .split(/[\s,]+/)
    .map(Number);
  if (
    box.length !== 4 ||
    box.some((n) => !Number.isFinite(n)) ||
    box[0] !== 0 ||
    box[1] !== 0 ||
    box[2] <= 0 ||
    box[2] !== box[3]
  )
    throw new Error("Logo must have a square viewBox starting at 0 0");
  const paths = [];
  const rest = document[2].replace(/<path\b([^>]*?)\/>/gs, (_, path) => {
    const attrs = attributes(path, [
      "d",
      "fill",
      "stroke",
      "stroke-width",
      "stroke-linecap",
      "stroke-linejoin",
      "fill-rule",
    ]);
    if (!attrs.d?.trim()) throw new Error("Logo path has no geometry");
    paths.push({ ...attrs, fill: attrs.fill ?? root.fill ?? "#000000" });
    return "";
  });
  if (rest.trim() || paths.length === 0)
    throw new Error("Logo must contain only self-closing path elements");
  return { size: box[2], paths };
}

function pathXml(path, staff, monochrome) {
  const color = (value) => {
    if (value === "none") return "#00000000";
    if (!/^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(value))
      throw new Error(`Unsupported SVG color: ${value}`);
    if (monochrome) return "#FFFFFF";
    return staff ? staffPalette[value.toUpperCase()] || value : value;
  };
  const attrs = {
    pathData: path.d,
    fillColor: color(path.fill),
  };
  if (path.stroke && path.stroke !== "none") {
    const width = Number(path["stroke-width"] ?? 1);
    if (!Number.isFinite(width) || width <= 0)
      throw new Error("Invalid stroke width");
    attrs.strokeColor = color(path.stroke);
    attrs.strokeWidth = width;
    if (path["stroke-linecap"]) {
      if (!["butt", "round", "square"].includes(path["stroke-linecap"]))
        throw new Error("Invalid stroke linecap");
      attrs.strokeLineCap = path["stroke-linecap"];
    }
    if (path["stroke-linejoin"]) {
      if (!["miter", "round", "bevel"].includes(path["stroke-linejoin"]))
        throw new Error("Invalid stroke linejoin");
      attrs.strokeLineJoin = path["stroke-linejoin"];
    }
  }
  if (path["fill-rule"]) {
    if (!["nonzero", "evenodd"].includes(path["fill-rule"]))
      throw new Error("Invalid fill rule");
    attrs.fillType = path["fill-rule"] === "evenodd" ? "evenOdd" : "nonZero";
  }
  return `    <path ${Object.entries(attrs)
    .map(([key, value]) => `android:${key}="${escapeXml(value)}"`)
    .join("\n        ")} />`;
}

function vector(
  logo,
  {
    staff,
    monochrome = false,
    size = 108,
    box = 66,
    background,
    round = false,
  },
) {
  const inset = (108 - box) / 2;
  const scale = Number((box / logo.size).toFixed(8));
  const backdrop = background
    ? `  <path android:fillColor="${background}" android:pathData="${
        round
          ? "M54,0 A54,54 0,1 1,54,108 A54,54 0,1 1,54,0 Z"
          : "M24,0 H84 A24,24 0,0 1,108,24 V84 A24,24 0,0 1,84,108 H24 A24,24 0,0 1,0,84 V24 A24,24 0,0 1,24,0 Z"
      }" />\n`
    : "";
  return `${header}<vector xmlns:android="${namespace}" android:width="${size}dp" android:height="${size}dp" android:viewportWidth="108" android:viewportHeight="108">\n${backdrop}  <group android:translateX="${inset}" android:translateY="${inset}" android:scaleX="${scale}" android:scaleY="${scale}">\n${logo.paths.map((path) => pathXml(path, staff, monochrome)).join("\n")}\n  </group>\n</vector>\n`;
}

function adaptive(monochrome = false) {
  return `${header}<adaptive-icon xmlns:android="${namespace}">\n  <background android:drawable="@color/tynys_brand_background" />\n  <foreground android:drawable="@drawable/tynys_launcher_foreground" />\n${monochrome ? '  <monochrome android:drawable="@drawable/tynys_launcher_monochrome" />\n' : ""}</adaptive-icon>\n`;
}

export async function renderAndroidAssets(root = repository) {
  const logo = parseLogo(
    await readFile(join(root, "public/assets/logo.svg"), "utf8"),
  );
  const projects = ["android", "android-staff"];
  for (const project of projects) {
    await access(join(root, project, "app/src/main/res"));
  }
  const outputs = [];
  for (const project of projects) {
    const staff = project === "android-staff";
    const background = staff ? "#344A35" : "#F4F3ED";
    // 66x66 centred in a 108x108 layer keeps the mark in the adaptive safe zone.
    const foreground = vector(logo, { staff });
    const files = {
      "values/tynys_brand.xml": `${header}<resources>\n  <color name="tynys_brand_background">${background}</color>\n</resources>\n`,
      "drawable/tynys_launcher_foreground.xml": foreground,
      "drawable/tynys_launcher_monochrome.xml": vector(logo, {
        staff,
        monochrome: true,
      }),
      "drawable/tynys_splash_icon.xml": vector(logo, { staff, size: 288 }),
      "drawable/tynys_splash.xml": `${header}<layer-list xmlns:android="${namespace}">\n  <item android:drawable="@color/tynys_brand_background" />\n  <item android:width="160dp" android:height="160dp" android:gravity="center" android:drawable="@drawable/tynys_splash_icon" />\n</layer-list>\n`,
      "mipmap-anydpi/tynys_launcher.xml": vector(logo, {
        staff,
        size: 48,
        box: 88,
        background,
      }),
      "mipmap-anydpi/tynys_launcher_round.xml": vector(logo, {
        staff,
        size: 48,
        box: 88,
        background,
        round: true,
      }),
      "mipmap-anydpi-v26/tynys_launcher.xml": adaptive(),
      "mipmap-anydpi-v26/tynys_launcher_round.xml": adaptive(),
      "mipmap-anydpi-v33/tynys_launcher.xml": adaptive(true),
      "mipmap-anydpi-v33/tynys_launcher_round.xml": adaptive(true),
    };
    for (const [relative, content] of Object.entries(files)) {
      const destination = join(root, project, "app/src/main/res", relative);
      await mkdir(dirname(destination), { recursive: true });
      await writeFile(destination, content);
      outputs.push(destination);
    }
  }
  return outputs;
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    const outputs = await renderAndroidAssets();
    console.log(
      `Generated ${outputs.length} Android resources from public/assets/logo.svg`,
    );
  } catch (error) {
    console.error(`Android assets: ${error.message}`);
    process.exitCode = 1;
  }
}
