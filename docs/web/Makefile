.PHONY: build_and_upload

build_and_upload:
	aws s3 cp static/scripts/scripts.js s3://iambic-docs-public/scripts/scripts.js
	aws s3 cp ../../install.sh s3://iambic-docs-public/scripts/install.sh
	yarn build
	aws s3 sync build s3://iambic-docs-public/
