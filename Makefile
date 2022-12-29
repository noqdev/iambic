docker_buildx := docker buildx build \
	--platform=linux/amd64,linux/arm64 \
	-t "public.ecr.aws/s2p9s3r8/iambic:latest"

.PHONY: build_docker
build_docker:
	@echo "--> Creating Iambic Docker image"
	$(docker_buildx) .

.PHONY: upload_docker
upload_docker:
	@echo "--> Uploading Iambic Docker image"
	bash -c "AWS_PROFILE=development/development_admin aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/s2p9s3r"
	$(docker_buildx) --push .

.PHONY: create_manifest
create_manifest:
	docker manifest create public.ecr.aws/s2p9s3r8/iambic public.ecr.aws/s2p9s3r8/iambic:latest

.PHONY: push_manifest
push_manifest:
	docker manifest push public.ecr.aws/s2p9s3r8/iambic

.PHONY: test
test:
	python3.10 -m pytest test

.PHONY: functional_test
functional_test:
	pytest --cov-report html --cov iambic functional_tests -s
