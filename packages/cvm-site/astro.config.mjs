// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://opencvm.org",
  vite: {
    plugins: [tailwindcss()],
  },
  integrations: [
    starlight({
      title: "OpenCVM",
      description:
        "Open-source API for Brazilian equities — filings, prices, fundamentals.",
      logo: { src: "./src/assets/logo.svg" },
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/opencvm/opencvm",
        },
      ],
      defaultLocale: "root",
      locales: {
        root: { label: "English", lang: "en" },
        pt: { label: "Português (Brasil)", lang: "pt-BR" },
      },
      customCss: ["./src/styles/global.css"],
      sidebar: [
        {
          label: "Start here",
          translations: { "pt-BR": "Começar" },
          items: [
            { slug: "start/quickstart" },
            { slug: "start/self-host" },
          ],
        },
        {
          label: "API",
          items: [
            { slug: "api/overview" },
          ],
        },
      ],
    }),
  ],
});
