// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import mermaid from "astro-mermaid";
import icon from "astro-icon";

export default defineConfig({
  site: "https://slipp.dev",
  integrations: [
    mermaid(),
    icon(),
    starlight({
      title: "slipp.dev",
      description:
        "Build locally, slipp to production. Tooling for self-hosted deployment.",
      customCss: ["./src/styles/custom.css"],
      components: {
        PageTitle: "./src/components/PageTitle.astro",
        SiteTitle: "./src/components/SiteTitle.astro",
        Hero: "./src/components/Hero.astro",
      },
      head: [
        { tag: "script", attrs: { src: "/scripts/parallax.js", defer: true } },
      ],
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/angelsen/slipp",
        },
      ],
      sidebar: [
        { label: "Home", link: "/" },
        {
          label: "Getting Started",
          items: [
            { label: "Installation", slug: "getting-started/installation" },
            { label: "Quick Start", slug: "getting-started/quickstart" },
          ],
        },
        {
          label: "Guides",
          autogenerate: { directory: "guides" },
        },
        {
          label: "Reference",
          autogenerate: { directory: "reference" },
        },
      ],
      editLink: {
        baseUrl: "https://github.com/angelsen/slipp/edit/main/docs/",
      },
    }),
  ],
});
