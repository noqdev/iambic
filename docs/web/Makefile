.PHONY: build_and_upload

build_and_upload:
	yarn build
	aws s3 sync build s3://iambic-docs-public/
