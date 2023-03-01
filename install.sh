# Check if docker is installed
echo "This script requires root privileges to install iambic in /usr/local/bin/; it also requires docker to be installed and running."

if [[ id -u != 0 ]]; then
    echo "Please run this script as root or with sudo. For example: curl https://iambic.org/install.sh | sudo bash"
    exit
fi

if ! command -v docker &> /dev/null
then
    echo "Docker is not installed on this system. Please install Docker before running this script. You can install docker by running the following command: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    exit
fi

if docker ps -q; then
    echo "Detected Docker is running, continuing..."
else
    echo "Docker is not running. Please start Docker before running this script. For example on most modern Linux systems you can start docker by running the following command: sudo systemctl start docker"
    exit
fi

if ! command -v git &> /dev/null
then
    echo "Git is not installed on this system. Please install Git before running this script. Refer to your operating system's package manager for installation instructions."
fi

if [[ -d /usr/local/bin ]]; then
    echo "Detected /usr/local/bin directory, continuing..."
else
    echo "Creating /usr/local/bin directory..."
    mkdir -p /usr/local/bin
fi

if echo $PATH | grep "/usr/local/bin" &> /dev/null; then
    echo "Detected /usr/local/bin is in the PATH, continuing..."
else
    echo "Please add the following line to your shell environment file: export PATH=\$PATH:/usr/local/bin"
fi

echo

IAMBIC_VERSION="${IAMBIC_VERSION:-latest}"
ECR_PATH="public.ecr.aws/o4z3c2v2/iambic:latest"

echo "Installing iambic..."
DOCKER_CMD="docker run -it -u \$(id -u):\$(id -g) -v \${HOME}/.aws:/app/.aws -e AWS_CONFIG_FILE=/app/.aws/config -e AWS_SHARED_CREDENTIALS_FILE=/app/.aws/credentials -e AWS_PROFILE=\${AWS_PROFILE} --mount \"type=bind,src=\$(pwd),dst=/templates\"  ${ECR_PATH} \"\$@\""

echo

echo "Setting up /usr/local/bin/iambic to launch the IAMbic docker container"
echo "#!/bin/bash" > /usr/local/bin/iambic
echo "${DOCKER_CMD}" >> /usr/local/bin/iambic
chmod +x /usr/local/bin/iambic

echo "Caching the latest iambic docker container, this might take a minute"
$( which docker ) pull ${ECR_PATH}

echo

echo "IAMbic installed successfully. After running the source command for your shell environment, mentioned above, you will be able to use the 'iambic --help' command to get started with IAMbic."
