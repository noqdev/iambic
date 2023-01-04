# Quick Start

Iambic's quick start guide will help you configure and run Iambic in less than 10 minutes. To prepare for this guide, you'll want to have credentials for the integrations that you would like to use, such as Okta, AWS, and/or Google.

First, you'll want to download and setup Iambic and its dependencies. to do this, you'll want to install Python 3.11.

1. Download and setup Iambic dependencies:

```bash
git clone https://github.com/noqdev/iambic.git
cd iambic
python3.10 -m venv env
. env/bin/activate
pip install -e .

```

2. Make an empty directory to store your configuration and imported cloud environment. In a production deployment, we recommend storing this in Git to get the full power of version control.

   ```
   mkdir ~/iambic-templates
   ```
3. Configure Iambic

```bash
iambic config <PATH>
```

TODO

3. iambic import

TODO

4. Make a change
