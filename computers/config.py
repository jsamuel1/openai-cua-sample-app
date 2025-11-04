from .default import *
from .contrib import *

computers_config = {
    "local-playwright": LocalPlaywrightBrowser,
    "docker": DockerComputer,
    "browserbase": BrowserbaseBrowser,
    "scrapybara-browser": ScrapybaraBrowser,
    "scrapybara-ubuntu": ScrapybaraUbuntu,
    "agentcore-browser": AgentCoreBrowser,
}

# Mapping of CLI argument names to computer class parameter names
# This allows CLI args to be namespaced (e.g., agentcore_region) while
# class parameters remain clean (e.g., region)
computers_arg_mapping = {
    "agentcore-browser": {
        "agentcore_region": "region",
        "execution_role_arn": "execution_role_arn",
        "recording_s3_bucket": "recording_s3_bucket",
        "recording_s3_prefix": "recording_s3_prefix",
        "no_browser_signing": "no_browser_signing",
    },
    # Add mappings for other computers as needed
}
