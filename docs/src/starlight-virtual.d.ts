declare module 'virtual:starlight/git-info' {
	export function getNewestCommitDate(file: string): Date;
}

declare module 'virtual:starlight/user-css' {}

declare module 'virtual:starlight/optional-css' {}

declare module 'virtual:starlight/user-images' {
	type ImageMetadata = import('astro').ImageMetadata;
	export const logos: {
		dark?: ImageMetadata;
		light?: ImageMetadata;
	};
}

declare module 'virtual:starlight/collection-config' {
	export const collections: import('astro:content').ContentConfig['collections'] | undefined;
}

declare module 'virtual:starlight/route-middleware' {
	export const routeMiddleware: Array<import('@astrojs/starlight/route-data').RouteMiddlewareHandler>;
}

declare module 'virtual:starlight/pagefind-config' {
	export const pagefindUserConfig: Partial<
		Extract<import('@astrojs/starlight/types').StarlightConfig['pagefind'], object>
	>;
}

declare module 'virtual:starlight/components/Banner' {
	const Banner: typeof import('@astrojs/starlight/components/Banner.astro').default;
	export default Banner;
}
declare module 'virtual:starlight/components/ContentPanel' {
	const ContentPanel: typeof import('@astrojs/starlight/components/ContentPanel.astro').default;
	export default ContentPanel;
}
declare module 'virtual:starlight/components/PageTitle' {
	const PageTitle: typeof import('@astrojs/starlight/components/PageTitle.astro').default;
	export default PageTitle;
}
declare module 'virtual:starlight/components/FallbackContentNotice' {
	const FallbackContentNotice: typeof import('@astrojs/starlight/components/FallbackContentNotice.astro').default;
	export default FallbackContentNotice;
}
declare module 'virtual:starlight/components/DraftContentNotice' {
	const DraftContentNotice: typeof import('@astrojs/starlight/components/DraftContentNotice.astro').default;
	export default DraftContentNotice;
}

declare module 'virtual:starlight/components/Footer' {
	const Footer: typeof import('@astrojs/starlight/components/Footer.astro').default;
	export default Footer;
}
declare module 'virtual:starlight/components/LastUpdated' {
	const LastUpdated: typeof import('@astrojs/starlight/components/LastUpdated.astro').default;
	export default LastUpdated;
}
declare module 'virtual:starlight/components/Pagination' {
	const Pagination: typeof import('@astrojs/starlight/components/Pagination.astro').default;
	export default Pagination;
}
declare module 'virtual:starlight/components/EditLink' {
	const EditLink: typeof import('@astrojs/starlight/components/EditLink.astro').default;
	export default EditLink;
}

declare module 'virtual:starlight/components/Header' {
	const Header: typeof import('@astrojs/starlight/components/Header.astro').default;
	export default Header;
}
declare module 'virtual:starlight/components/LanguageSelect' {
	const LanguageSelect: typeof import('@astrojs/starlight/components/LanguageSelect.astro').default;
	export default LanguageSelect;
}
declare module 'virtual:starlight/components/Search' {
	const Search: typeof import('@astrojs/starlight/components/Search.astro').default;
	export default Search;
}
declare module 'virtual:starlight/components/SiteTitle' {
	const SiteTitle: typeof import('@astrojs/starlight/components/SiteTitle.astro').default;
	export default SiteTitle;
}
declare module 'virtual:starlight/components/SocialIcons' {
	const SocialIcons: typeof import('@astrojs/starlight/components/SocialIcons.astro').default;
	export default SocialIcons;
}
declare module 'virtual:starlight/components/ThemeSelect' {
	const ThemeSelect: typeof import('@astrojs/starlight/components/ThemeSelect.astro').default;
	export default ThemeSelect;
}

declare module 'virtual:starlight/components/Head' {
	const Head: typeof import('@astrojs/starlight/components/Head.astro').default;
	export default Head;
}
declare module 'virtual:starlight/components/Hero' {
	const Hero: typeof import('@astrojs/starlight/components/Hero.astro').default;
	export default Hero;
}
declare module 'virtual:starlight/components/MarkdownContent' {
	const MarkdownContent: typeof import('@astrojs/starlight/components/MarkdownContent.astro').default;
	export default MarkdownContent;
}

declare module 'virtual:starlight/components/PageSidebar' {
	const PageSidebar: typeof import('@astrojs/starlight/components/PageSidebar.astro').default;
	export default PageSidebar;
}
declare module 'virtual:starlight/components/TableOfContents' {
	const TableOfContents: typeof import('@astrojs/starlight/components/TableOfContents.astro').default;
	export default TableOfContents;
}
declare module 'virtual:starlight/components/MobileTableOfContents' {
	const MobileTableOfContents: typeof import('@astrojs/starlight/components/MobileTableOfContents.astro').default;
	export default MobileTableOfContents;
}

declare module 'virtual:starlight/components/Sidebar' {
	const Sidebar: typeof import('@astrojs/starlight/components/Sidebar.astro').default;
	export default Sidebar;
}
declare module 'virtual:starlight/components/SkipLink' {
	const SkipLink: typeof import('@astrojs/starlight/components/SkipLink.astro').default;
	export default SkipLink;
}
declare module 'virtual:starlight/components/ThemeProvider' {
	const ThemeProvider: typeof import('@astrojs/starlight/components/ThemeProvider.astro').default;
	export default ThemeProvider;
}

declare module 'virtual:starlight/components/PageFrame' {
	const PageFrame: typeof import('@astrojs/starlight/components/PageFrame.astro').default;
	export default PageFrame;
}
declare module 'virtual:starlight/components/MobileMenuToggle' {
	const MobileMenuToggle: typeof import('@astrojs/starlight/components/MobileMenuToggle.astro').default;
	export default MobileMenuToggle;
}
declare module 'virtual:starlight/components/MobileMenuFooter' {
	const MobileMenuFooter: typeof import('@astrojs/starlight/components/MobileMenuFooter.astro').default;
	export default MobileMenuFooter;
}

declare module 'virtual:starlight/components/TwoColumnContent' {
	const TwoColumnContent: typeof import('@astrojs/starlight/components/TwoColumnContent.astro').default;
	export default TwoColumnContent;
}
