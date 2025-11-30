// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://slipp.dev',
	integrations: [
		starlight({
			title: 'slipp',
			description: 'Build locally, slipp to production. 90% automation for self-hosted app deployments.',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/angelsen/slipp' },
			],
			sidebar: [
				{ label: 'Home', link: '/' },
				{
					label: 'Getting Started',
					items: [
						{ label: 'Installation', slug: 'getting-started/installation' },
						{ label: 'Quick Start', slug: 'getting-started/quickstart' },
					],
				},
				{
					label: 'Guides',
					autogenerate: { directory: 'guides' },
				},
				{
					label: 'Reference',
					autogenerate: { directory: 'reference' },
				},
			],
			editLink: {
				baseUrl: 'https://github.com/angelsen/slipp/edit/main/docs/',
			},
		}),
	],
});
