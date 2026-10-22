import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
export default defineConfig(({ mode }) => {
  const surface =
    process.env.VITE_APP_SURFACE ||
    (["public", "staff"].includes(mode) ? mode : "combined");
  if (!["public", "staff", "combined"].includes(surface))
    throw new Error("Invalid VITE_APP_SURFACE");
  return {
    define: { "import.meta.env.VITE_APP_SURFACE": JSON.stringify(surface) },
    server: {
      proxy: {
        "/api": "http://127.0.0.1:8000",
        "/media": "http://127.0.0.1:8000",
      },
    },
    preview: {
      proxy: {
        "/api": "http://127.0.0.1:8000",
        "/media": "http://127.0.0.1:8000",
      },
    },
    plugins: [vue()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
        "#surface-routes": fileURLToPath(
          new URL(`./src/app/routes-${surface}.js`, import.meta.url),
        ),
      },
    },
    build: {
      outDir: surface === "staff" ? "dist/staff" : "dist/site",
      emptyOutDir: true,
      manifest: true,
    },
  };
});
