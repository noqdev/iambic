.PHONY: build_docker
build_docker:
	@echo "--> Creating Iambic Docker image"
	docker buildx build --platform=linux/amd64,linux/arm64 -t iambic -t "iambic:latest" -t "public.ecr.aws/s2p9s3r8/iambic:latest" .

.PHONY: upload_docker
upload_docker: build_docker
	@echo "--> Uploading Iambic Docker image"
	bash -c "AWS_PROFILE=development/development_admin aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/s2p9s3r"
	docker push public.ecr.aws/s2p9s3r8/iambic:latest