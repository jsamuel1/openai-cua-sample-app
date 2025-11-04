import os
from typing import Tuple
from playwright.sync_api import Browser, Page, Error as PlaywrightError
from ..shared.base_playwright import BasePlaywrightComputer
from dotenv import load_dotenv
from bedrock_agentcore.tools.browser_client import browser_session

load_dotenv()


class AgentCoreBrowser(BasePlaywrightComputer):
    """
    Amazon Bedrock AgentCore Browser provides a fully managed, pre-built cloud-based browser
    that enables generative AI agents to interact seamlessly with websites.
    
    This implementation uses Chrome DevTools Protocol (CDP) to connect to a remote browser
    session managed by AWS Bedrock AgentCore.
    
    Features:
    - Default browser: Use the built-in AgentCore browser (no setup required)
    - Session recording: Record sessions to S3 for replay and analysis (requires IAM role and S3 bucket)
    - Live view: Watch browser sessions in real-time via AWS Console
    - Web Bot Auth: Reduce CAPTCHAs using cryptographic identity verification (preview)
    - Reusable browsers: Automatically reuses browsers with matching configuration across application runs
    - Deterministic naming: Browser names are generated based on features for easy identification
    
    For more information:
    - Documentation: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser.html
    - Quickstart: https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/builtin-tools/quickstart-browser.md
    - Web Bot Auth: https://aws.amazon.com/blogs/machine-learning/reduce-captchas-for-ai-agents-browsing-the-web-with-web-bot-auth-preview-in-amazon-bedrock-agentcore-browser/
    
    IMPORTANT: This AgentCore Browser computer requires AWS credentials configured either
    via environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    or via AWS CLI configuration (~/.aws/credentials).
    
    For session recording, you need:
    1. An S3 bucket to store recordings
    2. (Optional) An IAM execution role - will be auto-created if not provided
    
    For Web Bot Auth (reduces CAPTCHAs):
    1. Enable browser_signing when creating a custom browser
    2. (Optional) execution_role_arn - will be auto-created if not provided
    3. Works with Cloudflare, HUMAN Security, and Akamai Technologies WAFs
    4. Domains must allow verified bots in their WAF configuration
    
    Note: IAM execution roles are automatically created with deterministic names
    and reused across runs when using the same configuration.
    """

    def get_dimensions(self):
        return self.dimensions
    
    def _generate_browser_name(self) -> str:
        """Generate a deterministic browser name based on configuration."""
        import hashlib
        
        features = []
        if self.enable_recording:
            features.append(f"rec_{self.recording_s3_bucket}_{self.recording_s3_prefix}")
        if self.browser_signing:
            features.append("signing")
        
        config_str = f"{'_'.join(features)}_{self.execution_role_arn}"
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
        
        feature_names = []
        if self.enable_recording:
            feature_names.append("Recording")
        if self.browser_signing:
            feature_names.append("Signing")
        
        return f"AgentCore_{'_'.join(feature_names)}_{config_hash}"
    
    def _find_existing_browser(self, browser_name: str) -> str:
        """Find an existing browser by name."""
        try:
            response = self.bedrock_agentcore_control.list_browsers()
            
            for browser in response.get('browserSummaries', []):
                if browser.get('name') == browser_name:
                    browser_id = browser.get('browserId')
                    print(f"♻️  Found existing browser: {browser_name} ({browser_id})")
                    return browser_id
            
            return None
        except Exception as e:
            print(f"Warning: Could not list browsers: {e}")
            return None
    
    def _create_or_get_execution_role(self) -> str:
        """
        Create or get an IAM execution role for AgentCore Browser.
        Uses deterministic naming based on features.
        
        Returns:
            str: Role ARN
        """
        import hashlib
        from botocore.exceptions import ClientError
        
        # Generate deterministic role name based on features
        features = []
        if self.enable_recording:
            features.append(f"rec-{self.recording_s3_bucket}")
        if self.browser_signing:
            features.append("signing")
        
        config_str = "-".join(features)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:8]
        
        role_name = f"AgentCoreBrowserRole-{config_hash}"
        
        try:
            # Try to get existing role
            response = self.iam_client.get_role(RoleName=role_name)
            role_arn = response['Role']['Arn']
            print(f"♻️  Found existing execution role: {role_name}")
            return role_arn
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                # Role doesn't exist, create it
                print(f"Creating execution role: {role_name}...")
                return self._create_execution_role(role_name)
            else:
                raise
    
    def _create_execution_role(self, role_name: str) -> str:
        """
        Create an IAM execution role with appropriate permissions.
        
        Args:
            role_name: Name for the role
            
        Returns:
            str: Role ARN
        """
        import json
        
        # Trust policy for AgentCore Browser
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": self.account_id
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account_id}:*"
                    }
                }
            }]
        }
        
        # Create role
        response = self.iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description=f"Auto-created execution role for AgentCore Browser",
            Tags=[
                {'Key': 'CreatedBy', 'Value': 'AgentCoreBrowser'},
                {'Key': 'Purpose', 'Value': 'BrowserAutomation'}
            ]
        )
        
        role_arn = response['Role']['Arn']
        print(f"✓ Created execution role: {role_name}")
        
        # Attach permissions policy
        policy_name = f"{role_name}-Policy"
        self._create_and_attach_policy(role_name, policy_name)
        
        # Wait a bit for IAM to propagate
        import time
        print("⏳ Waiting for IAM role to propagate...")
        time.sleep(10)
        
        return role_arn
    
    def _create_and_attach_policy(self, role_name: str, policy_name: str):
        """
        Create and attach permissions policy to the role.
        
        Args:
            role_name: Name of the role
            policy_name: Name for the policy
        """
        import json
        
        # Build policy based on features
        policy_statements = [
            {
                "Sid": "BrowserPermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:ConnectBrowserAutomationStream",
                    "bedrock-agentcore:ListBrowsers",
                    "bedrock-agentcore:GetBrowserSession",
                    "bedrock-agentcore:ListBrowserSessions",
                    "bedrock-agentcore:CreateBrowser",
                    "bedrock-agentcore:StartBrowserSession",
                    "bedrock-agentcore:StopBrowserSession",
                    "bedrock-agentcore:ConnectBrowserLiveViewStream",
                    "bedrock-agentcore:UpdateBrowserStream",
                    "bedrock-agentcore:DeleteBrowser",
                    "bedrock-agentcore:GetBrowser"
                ],
                "Resource": "*"
            },
            {
                "Sid": "CloudWatchLogsPermissions",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams"
                ],
                "Resource": "*"
            }
        ]
        
        # Add S3 permissions if recording is enabled
        if self.enable_recording:
            policy_statements.append({
                "Sid": "S3Permissions",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:ListMultipartUploadParts",
                    "s3:AbortMultipartUpload"
                ],
                "Resource": [
                    f"arn:aws:s3:::{self.recording_s3_bucket}",
                    f"arn:aws:s3:::{self.recording_s3_bucket}/*"
                ]
            })
        
        policy_document = {
            "Version": "2012-10-17",
            "Statement": policy_statements
        }
        
        # Create inline policy
        self.iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )
        
        print(f"✓ Attached permissions policy: {policy_name}")
    
    def _ensure_custom_browser(self):
        """Ensure a custom browser exists with the required features."""
        
        browser_name = self._generate_browser_name()
        
        # Try to find existing browser if reuse is enabled
        if self.reuse_browser:
            self.custom_browser_id = self._find_existing_browser(browser_name)
        
        # Create new browser if not found
        if not self.custom_browser_id:
            import uuid
            
            features = []
            if self.enable_recording:
                features.append("recording")
            if self.browser_signing:
                features.append("Web Bot Auth signing")
            
            print(f"Creating custom browser with {' and '.join(features)} enabled...")
            
            browser_params = {
                'name': browser_name,
                'description': f'Browser with {", ".join(features)}',
                'networkConfiguration': {
                    'networkMode': 'PUBLIC'
                },
                'executionRoleArn': self.execution_role_arn,
                'clientToken': str(uuid.uuid4())
            }
            
            if self.enable_recording:
                browser_params['recording'] = {
                    'enabled': True,
                    's3Location': {
                        'bucket': self.recording_s3_bucket,
                        'prefix': self.recording_s3_prefix
                    }
                }
            
            if self.browser_signing:
                browser_params['browserSigning'] = {
                    'enabled': True
                }
            
            browser_response = self.bedrock_agentcore_control.create_browser(**browser_params)
            self.custom_browser_id = browser_response.get('browserId')
            print(f"✓ Browser created: {browser_name} ({self.custom_browser_id})")
            
            # Wait for browser to become active
            self._wait_for_browser_active(self.custom_browser_id)
            
            if self.enable_recording:
                print(f"📹 Recordings will be stored at: s3://{self.recording_s3_bucket}/{self.recording_s3_prefix}/")
            if self.browser_signing:
                print(f"🔐 Web Bot Auth enabled - HTTP requests will be cryptographically signed")
                print(f"   This helps reduce CAPTCHAs on sites protected by Cloudflare, HUMAN Security, and Akamai")
        else:
            # Verify existing browser is active
            self._wait_for_browser_active(self.custom_browser_id)
    
    def _wait_for_browser_active(self, browser_id: str, max_wait: int = 60):
        """
        Wait for a browser to reach READY state.
        
        Args:
            browser_id: The browser ID to check
            max_wait: Maximum seconds to wait (default 60)
        """
        import time
        
        print(f"⏳ Waiting for browser {browser_id} to become ready...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                response = self.bedrock_agentcore_control.get_browser(browserId=browser_id)
                status = response.get('status')
                
                if status == 'READY':
                    print(f"✓ Browser is ready")
                    return
                elif status in ['FAILED', 'DELETING', 'DELETED']:
                    raise RuntimeError(f"Browser is in {status} state and cannot be used")
                else:
                    print(f"   Browser status: {status}...")
                    time.sleep(5)
            except Exception as e:
                print(f"   Error checking browser status: {e}")
                time.sleep(5)
        
        raise TimeoutError(f"Browser did not become ready within {max_wait} seconds")
    
    def _wait_for_session_ready(self, session_id: str, max_wait: int = 30):
        """
        Wait for a browser session to be fully ready for CDP connections.
        
        Args:
            session_id: The session ID to check
            max_wait: Maximum seconds to wait (default 30)
        """
        import time
        import boto3
        
        print(f"⏳ Waiting for session {session_id} to be ready for connections...")
        
        # Initialize bedrock-agentcore client if not already done
        if not hasattr(self, 'bedrock_agentcore_data'):
            self.bedrock_agentcore_data = boto3.client(
                'bedrock-agentcore',
                region_name=self.region
            )
        
        # Get the browser identifier
        browser_id = self.browser_identifier or self.custom_browser_id or 'aws.browser.v1'
        
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < max_wait:
            try:
                # Get session status
                response = self.bedrock_agentcore_data.get_browser_session(
                    browserIdentifier=browser_id,
                    sessionId=session_id
                )
                status = response.get('status')
                
                if status != last_status:
                    print(f"   Session status: {status}")
                    last_status = status
                
                if status == 'READY':
                    # Add a small additional delay to ensure automation endpoint is ready
                    print(f"   Waiting for automation endpoint to initialize...")
                    time.sleep(2)
                    print(f"✓ Session is ready for CDP connection")
                    return
                elif status == 'TERMINATED':
                    raise RuntimeError(f"Session was terminated before it could be used")
                else:
                    time.sleep(2)
            except Exception as e:
                # If we can't check status, wait a bit and try to connect anyway
                if "get_browser_session" in str(e) or "Parameter validation" in str(e):
                    print(f"   Note: Cannot verify session status ({e}), will attempt connection")
                    time.sleep(5)
                    return
                else:
                    raise
        
        # If we timeout, try to connect anyway
        print(f"   Timeout waiting for session status, attempting connection...")

    def __init__(
        self,
        width: int = 1024,
        height: int = 768,
        region: str = "us-east-1",
        virtual_mouse: bool = True,
        browser_identifier: str = None,
        execution_role_arn: str = None,
        recording_s3_bucket: str = None,
        recording_s3_prefix: str = "browser-recordings",
        no_browser_signing: bool = False,
        reuse_browser: bool = True,
    ):
        """
        Initialize the Amazon Bedrock AgentCore Browser instance.

        Args:
            width (int): The width of the browser viewport. Default is 1024.
            height (int): The height of the browser viewport. Default is 768.
            region (str): The AWS region for the AgentCore Browser service. Default is "us-east-1".
            virtual_mouse (bool): Whether to enable the virtual mouse cursor. Default is True.
            browser_identifier (str): Optional browser identifier to reuse an existing browser. If not provided, uses the default AgentCore browser.
            execution_role_arn (str): Optional IAM role ARN for browser execution. Required for recording/signing features.
            recording_s3_bucket (str): S3 bucket name for session recordings. Enables recording when provided.
            recording_s3_prefix (str): S3 prefix for recordings. Default is "browser-recordings".
            no_browser_signing (bool): Disable Web Bot Auth signing (enabled by default to reduce CAPTCHAs). Default is False.
            reuse_browser (bool): Whether to reuse existing browsers with matching configuration. Default is True.
        """
        super().__init__()
        
        # Browser Configuration
        self.dimensions = (width, height)
        self.virtual_mouse = virtual_mouse
        self.browser_identifier = browser_identifier
        self.region = region
        self.reuse_browser = reuse_browser
        
        # Recording Configuration
        self.execution_role_arn = execution_role_arn or os.getenv("AGENTCORE_BROWSER_EXECUTIONROLE_ARN")
        self.recording_s3_bucket = recording_s3_bucket
        self.recording_s3_prefix = recording_s3_prefix
        self.enable_recording = bool(recording_s3_bucket)
        
        # Web Bot Auth Configuration
        self.browser_signing = not no_browser_signing
        
        # Session tracking
        self.browser_session_client = None
        self.custom_browser_id = None
        
        # Initialize AWS clients if we need to create custom browsers
        if self.enable_recording or self.browser_signing:
            import boto3
            from botocore.exceptions import ClientError
            
            # Get account ID for role creation
            sts_client = boto3.client('sts')
            identity = sts_client.get_caller_identity()
            self.account_id = identity['Account']
            
            self.bedrock_agentcore_control = boto3.client(
                'bedrock-agentcore-control',
                region_name=self.region
            )
            self.iam_client = boto3.client('iam')
            
            print(f"✓ AWS Bedrock AgentCore client initialized in region: {self.region}")
            
            # Create or get execution role if not provided
            if not self.execution_role_arn:
                self.execution_role_arn = self._create_or_get_execution_role()
            
            # Ensure we have or create a custom browser
            self._ensure_custom_browser()




    def _get_browser_and_page(self) -> Tuple[Browser, Page]:
        """
        Create an AgentCore browser session and connect to it via CDP.

        Returns:
            Tuple[Browser, Page]: A tuple containing the connected browser and page objects.
        """
        print(f"✓ Initializing AgentCore Browser in region: {self.region}")
        
        try:
            # Import BrowserClient directly for manual session management
            from bedrock_agentcore.tools.browser_client import BrowserClient
            
            # Determine browser identifier
            identifier = self.browser_identifier or self.custom_browser_id or 'aws.browser.v1'
            
            if identifier != 'aws.browser.v1':
                print(f"Using custom browser: {identifier}")
            
            # Create browser client and start session with identifier
            client = BrowserClient(region=self.region)
            
            # Start session with identifier and viewport
            viewport = {'width': self.dimensions[0], 'height': self.dimensions[1]}
            session_id = client.start(
                identifier=identifier,
                viewport=viewport
            )
            
            # Store client for cleanup
            self.browser_session_client = client
            
            # Verify the session was created successfully
            if not hasattr(client, 'session_id') or not client.session_id:
                raise RuntimeError("Browser session was not created successfully - no session ID returned")
            
            print(f"✓ Browser session created: {client.session_id}")
            
            # Wait for session to be ready
            self._wait_for_session_ready(client.session_id)
            
            # Get WebSocket URL and authentication headers
            ws_url, headers = client.generate_ws_headers()
            
            print(f"Connecting to AgentCore Browser via CDP...")
            print(f"WebSocket URL: {ws_url}")
            
            # Connect to the remote browser session using CDP with auth headers
            browser = self._playwright.chromium.connect_over_cdp(
                ws_url,
                headers=headers,
                timeout=60000
            )
        except Exception as e:
            print(f"\n❌ Failed to create or connect to AgentCore Browser session:")
            print(f"   Error: {e}")
            print(f"\nTroubleshooting tips:")
            print(f"   1. Verify your AWS credentials are configured correctly")
            print(f"   2. Ensure you have permissions for bedrock-agentcore:StartBrowserSession")
            print(f"   3. Check that the region '{self.region}' supports AgentCore Browser")
            if self.custom_browser_id:
                print(f"   4. Verify the custom browser '{self.custom_browser_id}' exists and is in READY state")
            raise
        
        # Get the default context and page
        context = browser.contexts[0]
        
        # Add event listeners for page creation and closure
        context.on("page", self._handle_new_page)
        
        # Add virtual mouse cursor if enabled
        if self.virtual_mouse:
            self._add_virtual_mouse_cursor(context)
        
        # Get initial page
        page = context.pages[0]
        page.on("close", self._handle_page_close)
        
        # Navigate to initial URL
        page.goto("https://bing.com")
        print("✓ Connected to AgentCore Browser successfully!")
        
        return browser, page

    def _add_virtual_mouse_cursor(self, context):
        """Add virtual mouse cursor script to browser context."""
        context.add_init_script(
            """
            // Only run in the top frame
            if (window.self === window.top) {
                function initCursor() {
                    const CURSOR_ID = '__agentcore_cursor__';

                    // Check if cursor element already exists
                    if (document.getElementById(CURSOR_ID)) return;

                    const cursor = document.createElement('div');
                    cursor.id = CURSOR_ID;
                    Object.assign(cursor.style, {
                        position: 'fixed',
                        top: '0px',
                        left: '0px',
                        width: '20px',
                        height: '20px',
                        backgroundImage: 'url("data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 24 24\\' fill=\\'black\\' stroke=\\'white\\' stroke-width=\\'1\\' stroke-linejoin=\\'round\\' stroke-linecap=\\'round\\'><polygon points=\\'2,2 2,22 8,16 14,22 17,19 11,13 20,13\\'/></svg>")',
                        backgroundSize: 'cover',
                        pointerEvents: 'none',
                        zIndex: '99999',
                        transform: 'translate(-2px, -2px)',
                    });

                    document.body.appendChild(cursor);

                    document.addEventListener("mousemove", (e) => {
                        cursor.style.top = e.clientY + "px";
                        cursor.style.left = e.clientX + "px";
                    });
                }

                // Use requestAnimationFrame for early execution
                requestAnimationFrame(function checkBody() {
                    if (document.body) {
                        initCursor();
                    } else {
                        requestAnimationFrame(checkBody);
                    }
                });
            }
            """
        )

    def _handle_new_page(self, page: Page):
        """Handle the creation of a new page."""
        print("New page created in AgentCore Browser")
        self._page = page
        page.on("close", self._handle_page_close)

    def _handle_page_close(self, page: Page):
        """Handle the closure of a page."""
        print("Page closed in AgentCore Browser")
        if self._page == page:
            if self._browser.contexts[0].pages:
                self._page = self._browser.contexts[0].pages[-1]
            else:
                print("Warning: All pages have been closed.")
                self._page = None



    def screenshot(self) -> str:
        """
        Capture a screenshot of the current viewport using CDP.

        Returns:
            str: A base64 encoded string of the screenshot.
        """
        try:
            # Get CDP session from the page
            cdp_session = self._page.context.new_cdp_session(self._page)

            # Capture screenshot using CDP
            result = cdp_session.send(
                "Page.captureScreenshot", 
                {"format": "png", "fromSurface": True}
            )

            return result["data"]
        except PlaywrightError as error:
            print(f"CDP screenshot failed, falling back to standard screenshot: {error}")
            return super().screenshot()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Clean up resources when exiting the context manager.

        Args:
            exc_type: The type of the exception that caused the context to be exited.
            exc_val: The exception instance that caused the context to be exited.
            exc_tb: A traceback object encapsulating the call stack at the point 
                    where the exception occurred.
        """
        # Close page and browser
        if self._page:
            try:
                self._page.close()
            except Exception as e:
                print(f"Error closing page: {e}")
        
        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                print(f"Error closing browser: {e}")
        
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                print(f"Error stopping playwright: {e}")

        # Clean up AgentCore browser session using the SDK client
        if self.browser_session_client:
            try:
                print(f"\nCleaning up AgentCore Browser session...")
                self.browser_session_client.stop()
                print("✓ AgentCore Browser session stopped")
            except Exception as e:
                print(f"Warning: Could not stop browser session: {e}")
        
        print("✓ AgentCore Browser cleanup complete")
