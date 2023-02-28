# Check if docker is installed
if ! command -v docker &> /dev/null
then
    echo "Docker is not installed on this system. Please install Docker before running this script. You can install docker by running the following command: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    exit
fi

if ps aux | grep -q "[d]ockerd"; then
    echo "Detected Docker is running, continuing..."
else
    echo "Docker is not running. Please start Docker before running this script. For example on most modern Linux systems you can start docker by running the following command: sudo systemctl start docker"
    exit
fi

if id -nG "$USER" | grep -qw "docker"; then
    echo "Detected user is in the docker group, continuing..."
else
    echo "User is not in the docker group. Please add the user to the docker group before running this script. For example on most modern Linux systems you can add the user to the docker group by running the following command: sudo usermod -aG docker $USER"
    exit
fi

if ! command -v git &> /dev/null
then
    echo "Git is not installed on this system. Please install Git before running this script. Refer to your operating system's package manager for installation instructions."
fi

echo
echo

IAMBIC_GIT_REPO_PATH="${IAMBIC_GIT_REPO_PATH:-${HOME}/iambic-templates}"
ECR_PATH="public.ecr.aws/o4z3c2v2/iambic:latest"

echo "Installing iambic..."
echo "We are creating an iambic git repository in the directory ${IAMBIC_GIT_REPO_PATH}. If you want to change this directory, please edit the DEFAULT_IAMBIC_GIT_REPO variable in the install.sh script."
mkdir -p ${IAMBIC_GIT_REPO_PATH}
CWD=$(pwd)
cd ${IAMBIC_GIT_REPO_PATH}
$(which git) init .
cd $CWD
DOCKER_CMD="docker run -it -u $(id -u):$(id -g) -v ${HOME}/.aws:/app/.aws -e AWS_CONFIG_FILE=/app/.aws/config -e AWS_SHARED_CREDENTIALS_FILE=/app/.aws/credentials -e AWS_PROFILE=\${AWS_PROFILE} -v \${CWD}:/templates:Z ${ECR_PATH}"

echo
echo

echo "#!/bin/bash" > ~/.local/bin/iambic
echo "${DOCKER_CMD}" >> ~/.local/bin/iambic
chmod +x ~/.local/bin/iambic

echo "Caching the latest iambic docker container, this might take a minute"
$( which docker ) pull ${ECR_PATH}

echo

echo "IAMbic installed successfully. After running the source command for your shell environment, mentioned above, you will be able to use the 'iambic --help' command to get started with IAMbic."

echo
echo

echo "Note: if you did not get a source command for your shell environment, please add the following line to your shell environment file: ${DOCKER_CMD}"
echo "You'll know if it's working by testing with the following command: iambic --help"
