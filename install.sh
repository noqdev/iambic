# Check if docker is installed
if ! command -v docker &> /dev/null
then
    echo "Docker is not installed on this system. Please install Docker before running this script. You can install docker by running the following command: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    exit
fi

if ! command -v git &> /dev/null
then
    echo "Git is not installed on this system. Please install Git before running this script. Refer to your operating system's package manager for installation instructions."
fi

SHELL_NAME=$(ps -p $$ -o args= | awk '{print $1}')
echo "Detected shell: ${SHELL_NAME}"
IAMBIC_GIT_REPO_PATH="${IAMBIC_GIT_REPO_PATH:-${HOME}/iambic_templates}"

echo "Installing iambic..."
echo "We are creating an iambic git repository in the directory ${IAMBIC_GIT_REPO_PATH}. If you want to change this directory, please edit the DEFAULT_IAMBIC_GIT_REPO variable in the install.sh script."
mkdir -p ${IAMBIC_GIT_REPO_PATH}
CWD=$(pwd)
cd ${IAMBIC_GIT_REPO_PATH}
$(which git) init .
cd $CWD
DOCKER_ALIAS="alias iambic='docker run -it -u $(id -u):$(id -g) -v ${HOME}/.aws:/app/.aws -e AWS_CONFIG_FILE=/app/.aws/config -e AWS_SHARED_CREDENTIALS_FILE=/app/.aws/credentials -e AWS_PROFILE=${AWS_PROFILE} -v ${IAMBIC_GIT_REPO_PATH}:/templates:Z public.ecr.aws/s2p9s3r8/iambic:latest'"

if [ "$SHELL_NAME" = "bash" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.bashrc
    source ~/.bashrc
elif [ "$SHELL_NAME" = "sh" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.profile
    source ~/.profile
elif [ "$SHELL_NAME" = "zsh" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.zshrc
    source ~/.zshrc
elif [ "$SHELL_NAME" = "ksh" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.kshrc
    source ~/.kshrc
elif [ "$SHELL_NAME" = "dash" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.profile
    source ~/.profile
elif [ "$SHELL_NAME" = "csh" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.cshrc
    source ~/.cshrc
elif [ "$SHELL_NAME" = "tcsh" ]; then
    echo "${DOCKER_ALIAS}" >> ~/.tcshrc
    source ~/.tcshrc
else
    echo "${DOCKER_ALIAS}" >> ~/.profile
    source ~/.profile
fi

echo "Caching the latest iambic docker container"
$( which docker ) pull public.ecr.aws/s2p9s3r8/iambic:latest
echo "IAMbic installed successfully. You can now use the 'iambic --help' command to get started with IAMbic."
