# Check if docker is installed


function ask_sudo() {
  if ! sudo -n true 2>/dev/null; then
    echo -e "Please enter your sudo password to create /usr/local/bin/iambic.\n"
    sudo -v
  fi
}

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

if echo $PATH | grep "/usr/local/bin" &> /dev/null; then
    echo "Detected /usr/local/bin is in the PATH, continuing..."
else
    echo "Please add the following line to your shell environment file: export PATH=\$PATH:/usr/local/bin"
fi

echo

ECR_PATH="public.ecr.aws/o4z3c2v2/iambic:latest"

echo "Installing iambic..."
DOCKER_CMD="#!/bin/bash

ENV_VAR_ARGS=\"\"
for var in \$(env | grep ^AWS_ | cut -d= -f1); do
  if [[ \$var == \"AWS_SHARED_CREDENTIALS_FILE\" ]]; then
    continue
  elif [[ \$var == \"AWS_CONFIG_FILE\" ]]; then
    continue
  elif [ -n \"\${!var}\" ]; then
    ENV_VAR_ARGS=\"\$ENV_VAR_ARGS -e \$var=\${!var}\"
  fi
done

if [ -f ~/.aws/config ]; then
    # Search for credential_process in .aws/config file
    if grep -q \"credential_process\" ~/.aws/config; then
        # Extract the binary name from the config file
        binaries=\$(awk -F\"=\" '/credential_process/ {print \$2}' ~/.aws/config | awk '{print \$1}' | tr -d \"'\")
        # Print a comma-separated list of unique binary names
        echo \"Credential process brokering is enabled using the following binaries in .aws/config file: \$(echo \"\$binaries\" | tr ' ' '\n' | sort -u | tr '\n' ', ' | sed 's/,$//')\"
        echo \"Please make sure that this scenario is properly handled by referencing the documentation\"
        echo \"for your credential process broker(s) on how to export the AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY\"
        echo \"and AWS_SESSION_TOKEN environment variables.\"
        echo
        read -p \"Press Enter to acknowledge this warning... or CTRL+C to exit\"
    fi
fi

ENV_VAR_ARGS=\"\$ENV_VAR_ARGS -e AWS_SHARED_CREDENTIALS_FILE=/app/.aws/credentials\"
ENV_VAR_ARGS=\"\$ENV_VAR_ARGS -e AWS_CONFIG_FILE=/app/.aws/config\"

docker run -w /templates -it -u \$(id -u):\$(id -g) -v \${HOME}/.aws:/app/.aws \$ENV_VAR_ARGS --mount \"type=bind,src=\$(pwd),dst=/templates\"  public.ecr.aws/o4z3c2v2/iambic:latest \"\$@\""

echo

echo "Setting up /usr/local/bin/iambic to launch the IAMbic docker container"
ask_sudo
echo "${DOCKER_CMD}" | sudo tee /usr/local/bin/iambic &>/dev/null
sudo chmod +x /usr/local/bin/iambic

echo "Caching the iambic docker container, this might take a minute"
$( which docker ) pull ${ECR_PATH}

echo

echo "IAMbic installed successfully. After running the source command for your shell environment, mentioned above, you will be able to use the 'iambic --help' command to get started with IAMbic."
