import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const surface =
    process.env.VITE_APP_SURFACE ||
    (["public", "staff", "mobile", "mobile-staff"].includes(mode)
      ? mode
      : "combined");
  if (
    !["public", "staff", "combined", "mobile", "mobile-staff"].includes(surface)
  )
    throw new Error("Invalid VITE_APP_SURFACE");
  if (surface.startsWith("mobile") && env.VITE_DATA_MODE === "api") {
    const api = new URL(env.VITE_API_BASE || "", "capacitor://localhost");
    if (
      api.protocol !== "https:" ||
      api.username ||
      api.password ||
      api.search ||
      api.hash ||
      api.pathname !== "/api/v1"
    )
      throw new Error(
        "Mobile API builds require VITE_API_BASE=https://your-backend/api/v1",
      );
  }
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
          new URL(
            `./src/app/routes-${surface === "mobile" ? "public" : surface}.js`,
            import.meta.url,
          ),
        ),
      },
    },
    build: {
      target: surface.startsWith("mobile") ? "safari16" : undefined,
      outDir: surface.startsWith("mobile")
        ? `dist/${surface}`
        : surface === "staff"
          ? "dist/staff"
          : "dist/site",
      emptyOutDir: true,
      manifest: true,
    },
  };
});
