.PHONY: docs docs-dev docs-deploy

# Build docs
docs:
	cd docs && npm run build

# Dev server
docs-dev:
	cd docs && npm run dev

# Deploy to GitHub Pages
docs-deploy: docs
	cd docs/dist && \
		git init && \
		git checkout -b gh-pages && \
		git add -A && \
		git commit -m "Deploy $$(date +%Y-%m-%d)" && \
		git push -f git@github.com:angelsen/slipp.git gh-pages
	@echo "Deployed to https://slipp.dev"
