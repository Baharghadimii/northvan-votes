import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  integrations: [react(), sitemap()],
  output: "static",
  site: "https://northvanvotes.ca",
  build: { inlineStylesheets: "auto" },
  devToolbar: { enabled: false },
  // Promises and votes became the home page on 2026-11-19; keep old links working.
  redirects: { "/promises-and-votes": "/" },
});
