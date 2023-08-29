BUILD_VERSION := $(shell python build_utils/tag_and_build_container.py print-current-version)
IAMBIC_PUBLIC_ECR_ALIAS := iambic

.PHONY: clean
clean:
	rm -rf dist/ || echo $?
	rm -rf build/ || echo $?
	rm -rf *.egg-info || echo $?
	rm -rf .eggs/ || echo $?
	rm -rf .pytest_cache/ || echo $?
	rm -rf .coverage* || echo $
	find . -name '*.pyc' -delete
	find . -name '*.pyo' -delete
	find . -name '*.egg-link' -delete


.PHONY: prepare_for_dist
prepare_for_dist:
	rm -f proposed_changes.yaml # especially important if this is run locally

.PHONY: auth_to_ecr
auth_to_ecr:
	bash -c "AWS_PROFILE=iambic_open_source/iambic_image_builder aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}"

docker_buildx := docker buildx build \
	--platform=linux/amd64 \
	-t "public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic:latest" -t "public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic:${BUILD_VERSION}"

.PHONY: docker_build_no_buildkit
docker_build_no_buildkit:
	DOCKER_BUILDKIT=0 docker build -t "iambic" .

.PHONY: build_docker
build_docker: prepare_for_dist
	@echo "--> Creating Iambic Docker image"
	@echo ${BUILD_VERSION}
	$(docker_buildx) .

.PHONY: upload_docker
upload_docker:
	@echo "--> Uploading Iambic Docker image"
	$(docker_buildx) --push .

.PHONY: trivy_scan
trivy_scan:
	trivy image --output iambic.trivy.scan.txt --timeout 15m --skip-files /app/docs/web/docs/getting_started/aws/aws.mdx --secret-config trivy-secret.yaml --severity HIGH,CRITICAL public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic:latest

.PHONY: trivy_sbom
trivy_sbom:
	trivy image --format spdx-json --timeout 15m --output iambic.sbom.json public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic:latest

.PHONY: create_manifest
create_manifest:
	docker manifest create public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic:latest

.PHONY: push_manifest
push_manifest:
	docker manifest push public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic

.PHONY: test
test:
	python -m pytest --cov iambic --cov-report xml:cov_unit_tests.xml --cov-report html:cov_unit_tests.html . --ignore functional_tests/ -s -n auto --dist loadscope

.PHONY: functional_wizard_test
functional_wizard_test:
	pytest --cov-report html --cov iambic --cov-report lcov:cov_functional_tests_wizard.lcov --cov-report xml:cov_functional_tests_wizard.xml --cov-report html:cov_functional_tests_wizard.html  functional_tests/test_wizard.py -s --durations=20

.PHONY: functional_test
functional_test:
	pytest --cov-report html --cov iambic --cov-report lcov:cov_functional_tests.lcov --cov-report xml:cov_functional_tests.xml --cov-report html:cov_functional_tests.html  functional_tests --ignore functional_tests/test_config_discovery.py -s -n auto --dist loadscope --reruns 3 --reruns-delay 5 -r aR --durations=20
	pytest --cov-report html --cov iambic --cov-report lcov:cov_functional_tests_config_discovery.lcov --cov-report xml:cov_functional_tests_config_discovery.xml --cov-report html:cov_functional_tests_config_discovery.html  functional_tests/test_config_discovery.py -s --durations=20
# 	pytest --cov-report html --cov iambic functional_tests -s
# 	pytest --cov-report html --cov iambic functional_tests/aws/user/test_update_template.py -s
# 	pytest --cov-report html --cov iambic functional_tests/aws/managed_policy/test_template_expiration.py -s

.PHONY: functional_test_without_cicd
functional_test_without_cicd:
	pytest --cov-report html --cov iambic functional_tests -s

docker_base_image_buildx := docker buildx build \
	--platform=linux/amd64 \
	-t "public.ecr.aws/${IAMBIC_PUBLIC_ECR_ALIAS}/iambic_container_base:1.0" -f Dockerfile.base_image

.PHONY: build_docker_base_image
build_docker_base_image:
	@echo "--> Creating Iambic Docker base container image"
	$(docker_base_image_buildx) .

.PHONY: upload_docker_base_image
upload_docker_base_image:
	@echo "--> Uploading Iambic Docker base container image"
	$(docker_base_image_buildx) --push .
