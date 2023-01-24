docker_buildx := docker buildx build \
	--platform=linux/amd64 \
	-t "public.ecr.aws/s2p9s3r8/iambic:latest"

.PHONY: docker_build_no_buildkit
docker_build_no_buildkit:
	DOCKER_BUILDKIT=0 docker build -t "iambic" .

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
# 	pytest --cov-report html --cov iambic functional_tests/aws/role/test_create_template.py -s
# 	pytest --cov-report html --cov iambic functional_tests/aws/managed_policy/test_template_expiration.py -s


docker_base_image_buildx := docker buildx build \
	--platform=linux/amd64 \
	-t "public.ecr.aws/s2p9s3r8/iambic_container_base:1.0" -f Dockerfile.base_image

.PHONY: build_docker_base_image
build_docker_base_image:
	@echo "--> Creating Iambic Docker base container image"
	$(docker_base_image_buildx) .

.PHONY: upload_docker_base_image
upload_docker_base_image:
	@echo "--> Uploading Iambic Docker base container image"
	bash -c "AWS_PROFILE=development/development_admin aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/s2p9s3r"
	$(docker_base_image_buildx) --push .
