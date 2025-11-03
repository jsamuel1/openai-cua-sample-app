import os
from typing import Tuple
from playwright.sync_api import Browser, Page, Error as PlaywrightError
from ..shared.base_playwright import BasePlaywrightComputer
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

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
    1. An IAM execution role with S3 write permissions
    2. An S3 bucket to store recordings
    3. Proper trust policy allowing bedrock-agentcore.amazonaws.com to assume the role
    
    For Web Bot Auth (reduces CAPTCHAs):
    1. Enable browser_signing when creating a custom browser
    2. Requires execution_role_arn parameter
    3. Works with Cloudflare, HUMAN Security, and Akamai Technologies WAFs
    4. Domains must allow verified bots in their WAF configuration
    """

    def get_dimensions(self):
        return self.dimensions

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
        browser_signing: bool = False,
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
            execution_role_arn (str): IAM role ARN for browser execution. Required for recording and browser_signing. Example: "arn:aws:iam::123456789012:role/AgentCoreBrowserRole"
            recording_s3_bucket (str): S3 bucket name for session recordings. Enables recording when provided with execution_role_arn.
            recording_s3_prefix (str): S3 prefix for recordings. Default is "browser-recordings".
            browser_signing (bool): Enable Web Bot Auth to reduce CAPTCHAs using cryptographic signatures (preview). Requires execution_role_arn. Default is False.
            reuse_browser (bool): Whether to reuse existing browsers with matching configuration. Default is True.
        """
        super().__init__()
        
        # Browser Configuration
        self.dimensions = (width, height)
        self.virtual_mouse = virtual_mouse
        self.browser_identifier = browser_identifier
        self.reuse_browser = reuse_browser
        
        # Recording Configuration
        self.execution_role_arn = execution_role_arn
        self.recording_s3_bucket = recording_s3_bucket
        self.recording_s3_prefix = recording_s3_prefix
        self.enable_recording = bool(recording_s3_bucket and execution_role_arn)
        
        # Web Bot Auth Configuration
        self.browser_signing = browser_signing
        
        # AWS Configuration
        self.region = region
        
        # Session tracking
        self.browser_id = None
        self.session_id = None
        self.browser_created = False  # Track if we created the browser
        
        # Initialize AWS clients
        self.bedrock_agentcore_client = None
        self.bedrock_agentcore_control = None
        self._initialize_aws_client()

    def _initialize_aws_client(self):
        """Initialize AWS Bedrock AgentCore client."""
        try:
            # Verify AWS credentials
            boto3.client('sts').get_caller_identity()
            
            # Create Bedrock AgentCore clients
            self.bedrock_agentcore_client = boto3.client(
                'bedrock-agentcore',
                region_name=self.region
            )

            self.bedrock_agentcore_control = boto3.client(
                'bedrock-agentcore-control',
                region_name=self.region
            )
            
            print(f"✓ AWS Bedrock AgentCore client initialized in region: {self.region}")
            
        except NoCredentialsError:
            print("\n⚠️  AWS Credentials NOT found. Please configure AWS credentials.")
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == 'InvalidClientTokenId':
                print("\n⚠️  AWS Credentials are NOT valid: The access key ID is invalid or does not exist.")
            elif error_code == 'ExpiredToken':
                print("\n⚠️  AWS Credentials are NOT valid: The security token is expired.")
            else:
                print(f"\n⚠️  AWS Credentials check failed: {e}")
            raise
        except Exception as e:
            print(f"Error initializing AWS client: {e}")
            print("Please ensure AWS credentials are properly configured.")
            raise

    def _generate_browser_name(self) -> str:
        """
        Generate a deterministic browser name based on configuration.
        
        Returns:
            str: Deterministic browser name
        """
        import hashlib
        
        # Create a deterministic name based on features
        features = []
        if self.enable_recording:
            features.append(f"rec-{self.recording_s3_bucket}-{self.recording_s3_prefix}")
        if self.browser_signing:
            features.append("signing")
        
        # Include execution role ARN in the hash for uniqueness
        config_str = f"{'-'.join(features)}-{self.execution_role_arn}"
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
        
        # Create readable name
        feature_names = []
        if self.enable_recording:
            feature_names.append("Recording")
        if self.browser_signing:
            feature_names.append("Signing")
        
        return f"AgentCore-{'-'.join(feature_names)}-{config_hash}"
    
    def _find_existing_browser(self, browser_name: str) -> str:
        """
        Find an existing browser by name.
        
        Args:
            browser_name: The browser name to search for
            
        Returns:
            str: Browser ID if found, None otherwise
        """
        try:
            # List browsers and find matching name
            response = self.bedrock_agentcore_control.list_browsers()
            
            for browser in response.get('browsers', []):
                if browser.get('name') == browser_name:
                    browser_id = browser.get('browserId') or browser.get('browserIdentifier')
                    print(f"♻️  Found existing browser: {browser_name} ({browser_id})")
                    return browser_id
            
            return None
        except Exception as e:
            print(f"Warning: Could not list browsers: {e}")
            return None

    def _create_browser_session(self) -> dict:
        """
        Create a new browser session on Amazon Bedrock AgentCore.

        Returns:
            dict: Session information including browser_id, session_id, and WebSocket URL.
        """
        width, height = self.dimensions
        
        # Use existing browser or create a new one
        if self.browser_identifier:
            self.browser_id = self.browser_identifier
            print(f"Using specified browser: {self.browser_id}")
        elif self.enable_recording or self.browser_signing:
            # Generate deterministic browser name
            browser_name = self._generate_browser_name()
            
            # Try to find existing browser if reuse is enabled
            if self.reuse_browser:
                self.browser_id = self._find_existing_browser(browser_name)
            
            # Create new browser if not found
            if not self.browser_id:
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
                
                # Add recording configuration if enabled
                if self.enable_recording:
                    browser_params['recording'] = {
                        'enabled': True,
                        's3Location': {
                            'bucket': self.recording_s3_bucket,
                            'prefix': self.recording_s3_prefix
                        }
                    }
                
                # Add browser signing configuration if enabled
                if self.browser_signing:
                    browser_params['browserSigning'] = {
                        'enabled': True
                    }
                
                browser_response = self.bedrock_agentcore_control.create_browser(**browser_params)
                self.browser_id = browser_response.get('browserId') or browser_response.get('browserIdentifier')
                self.browser_created = True
                print(f"✓ Browser created: {browser_name} ({self.browser_id})")
                
                if self.enable_recording:
                    print(f"📹 Recordings will be stored at: s3://{self.recording_s3_bucket}/{self.recording_s3_prefix}/")
                if self.browser_signing:
                    print(f"🔐 Web Bot Auth enabled - HTTP requests will be cryptographically signed")
                    print(f"   This helps reduce CAPTCHAs on sites protected by Cloudflare, HUMAN Security, and Akamai")
        else:
            # Use default AgentCore browser (no custom browser needed)
            print("Using default AgentCore browser...")
            self.browser_id = None
        
        # Start browser session
        print("Starting browser session...")
        session_params = {}
        
        if self.browser_id:
            session_params['browserId'] = self.browser_id
        
        session_response = self.bedrock_agentcore_client.start_browser_session(**session_params)
        
        self.session_id = session_response['sessionId']
        print(f"✓ Session started: {self.session_id}")
        
        # Get automation endpoint (CDP WebSocket URL with auth)
        automation_params = {'sessionId': self.session_id}
        if self.browser_id:
            automation_params['browserId'] = self.browser_id
            
        automation_response = self.bedrock_agentcore_client.get_automation_endpoint(**automation_params)
        
        return {
            'browser_id': self.browser_id,
            'session_id': self.session_id,
            'ws_url': automation_response['webSocketUrl'],
            'headers': automation_response.get('headers', {})
        }

    def _get_browser_and_page(self) -> Tuple[Browser, Page]:
        """
        Create an AgentCore browser session and connect to it via CDP.

        Returns:
            Tuple[Browser, Page]: A tuple containing the connected browser and page objects.
        """
        # Create browser session
        session_info = self._create_browser_session()
        
        print(f"\nConnecting to AgentCore Browser via CDP...")
        
        # Connect to the remote browser session using CDP
        connect_options = {'timeout': 60000}
        if session_info.get('headers'):
            connect_options['headers'] = session_info['headers']
        
        browser = self._playwright.chromium.connect_over_cdp(
            session_info['ws_url'], 
            **connect_options
        )
        
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

    def list_browsers(self) -> list:
        """
        List all custom browsers in the account.
        
        Returns:
            list: List of browser dictionaries with name, id, and status
        """
        try:
            response = self.bedrock_agentcore_control.list_browsers()
            browsers = []
            
            for browser in response.get('browsers', []):
                browsers.append({
                    'name': browser.get('name'),
                    'id': browser.get('browserId') or browser.get('browserIdentifier'),
                    'status': browser.get('status'),
                    'created': browser.get('createdAt')
                })
            
            return browsers
        except Exception as e:
            print(f"Error listing browsers: {e}")
            return []
    
    def delete_browser_by_id(self, browser_id: str) -> bool:
        """
        Delete a specific browser by ID.
        
        Args:
            browser_id: The browser identifier to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.bedrock_agentcore_control.delete_browser(
                browserIdentifier=browser_id
            )
            print(f"✓ Browser {browser_id} deleted")
            return True
        except Exception as e:
            print(f"Error deleting browser {browser_id}: {e}")
            return False

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

        # Clean up AgentCore session
        if self.bedrock_agentcore_client and self.session_id:
            try:
                print(f"\nCleaning up AgentCore Browser session...")
                
                # Stop browser session
                stop_params = {'sessionId': self.session_id}
                if self.browser_id:
                    stop_params['browserId'] = self.browser_id
                
                self.bedrock_agentcore_client.stop_browser_session(**stop_params)
                print(f"✓ Session {self.session_id} stopped")
                
                # If recording was enabled, show where to find it
                if self.enable_recording:
                    print(f"📹 Session recording available at: s3://{self.recording_s3_bucket}/{self.recording_s3_prefix}/")
                    print(f"   View in AWS Console: https://{self.region}.console.aws.amazon.com/bedrock-agentcore/builtInTools")
                
            except Exception as e:
                print(f"Warning: Could not stop browser session: {e}")
        
        # Note: Browsers are NEVER deleted automatically to enable reuse across runs
        # This is intentional behavior for the reuse_browser feature
        # Benefits:
        #   - Faster startup on subsequent runs (no browser creation overhead)
        #   - Consistent configuration across application restarts
        #   - Reduced API calls to control plane
        # 
        # To manually delete browsers:
        #   - Use browser.list_browsers() and browser.delete_browser_by_id()
        #   - Or use AWS Console: bedrock-agentcore/builtInTools
        #   - Or use AWS CLI: aws bedrock-agentcore-control delete-browser
        
        if self.browser_id and (self.enable_recording or self.browser_signing):
            print(f"ℹ️  Browser {self.browser_id} will be reused in future runs")
        
        print("✓ AgentCore Browser cleanup complete")
