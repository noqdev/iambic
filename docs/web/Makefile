.PHONY: build_and_upload

build_and_upload:
	yarn build
	aws s3 sync build s3://iambic-docs-public/
	aws s3 cp ../../install.sh s3://iambic-docs-public/scripts/install.sh
	aws s3 cp scripts/scripts.js s3://iambic-docs-public/scripts/scripts.js
