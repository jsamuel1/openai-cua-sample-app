import os
import json
from typing import Tuple, Optional
from playwright.sync_api import Browser, Page, Error as PlaywrightError
from ..shared.base_playwright import BasePlaywrightComputer
from dotenv import load_dotenv
import boto3
import time

load_dotenv()


class AgentCoreBrowser(BasePlaywrightComputer):
    """
    Amazon Bedrock AgentCore Browser provides a fully managed, pre-built cloud-based browser
    that enables generative AI agents to interact seamlessly with websites.
    
    This implementation uses Chrome DevTools Protocol (CDP) to connect to a remote browser
    session managed by AWS Bedrock AgentCore.
    
    For more information about Bedrock AgentCore Browser:
    https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser.html
    
    IMPORTANT: This AgentCore Browser computer requires AWS credentials configured either
    via environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    or via AWS CLI configuration (~/.aws/credentials).
    """

    def get_dimensions(self):
        return self.dimensions

    def __init__(
        self,
        width: int = 1024,
        height: int = 768,
        region: str = "us-east-1",
        virtual_mouse: bool = True,
        session_timeout: int = 3600,
    ):
        """
        Initialize the Amazon Bedrock AgentCore Browser instance.

        Args:
            width (int): The width of the browser viewport. Default is 1024.
            height (int): The height of the browser viewport. Default is 768.
            region (str): The AWS region for the AgentCore Browser service. Default is "us-east-1".
            virtual_mouse (bool): Whether to enable the virtual mouse cursor. Default is True.
            session_timeout (int): Browser session timeout in seconds. Default is 3600 (1 hour).
        """
        super().__init__()
        
        # AWS Configuration
        self.region = region
        self.session_timeout = session_timeout
        
        # Browser Configuration
        self.dimensions = (width, height)
        self.virtual_mouse = virtual_mouse
        
        # Session tracking
        self.browser_id = None
        self.session_id = None
        self.ws_url = None
        
        # Initialize AWS clients
        self.bedrock_agentcore_client = None
        self._initialize_aws_client()

    def _initialize_aws_client(self):
        """Initialize AWS Bedrock AgentCore client."""
        try:
            # Create boto3 session with environment credentials or default profile
            aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
            aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            aws_session_token = os.getenv("AWS_SESSION_TOKEN")
            
            if aws_access_key and aws_secret_key:
                session = boto3.Session(
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    aws_session_token=aws_session_token,
                    region_name=self.region
                )
            else:
                # Use default credentials (from ~/.aws/credentials or instance profile)
                session = boto3.Session(region_name=self.region)
            
            # Create Bedrock AgentCore client
            # Note: This uses the bedrock-agentcore service endpoint
            self.bedrock_agentcore_client = session.client(
                'bedrock-agentcore',
                region_name=self.region
            )
            
            print(f"✓ AWS Bedrock AgentCore client initialized in region: {self.region}")
            
        except Exception as e:
            print(f"Error initializing AWS client: {e}")
            print("Please ensure AWS credentials are properly configured.")
            raise

    def _create_browser_session(self) -> dict:
        """
        Create a new browser session on Amazon Bedrock AgentCore.

        Returns:
            dict: Session information including browser_id, session_id, and WebSocket URL.
        """
        try:
            width, height = self.dimensions
            
            # Create browser instance if not exists
            if not self.browser_id:
                print("Creating AgentCore browser instance...")
                browser_response = self.bedrock_agentcore_client.create_browser(
                    browserSettings={
                        'viewport': {
                            'width': width,
                            'height': height
                        }
                    },
                    timeoutSeconds=self.session_timeout
                )
                self.browser_id = browser_response['browserId']
                print(f"✓ Browser created: {self.browser_id}")
            
            # Create browser session
            print("Creating browser session...")
            session_response = self.bedrock_agentcore_client.create_browser_session(
                browserId=self.browser_id,
                sessionSettings={
                    'viewport': {
                        'width': width,
                        'height': height
                    }
                }
            )
            
            self.session_id = session_response['sessionId']
            
            # Generate WebSocket URL for CDP connection
            # Format: wss://bedrock-agentcore.<region>.amazonaws.com/browser-streams/{browser_id}/sessions/{session_id}/automation
            self.ws_url = f"wss://bedrock-agentcore.{self.region}.amazonaws.com/browser-streams/{self.browser_id}/sessions/{self.session_id}/automation"
            
            print(f"✓ Session created: {self.session_id}")
            print(f"WebSocket URL: {self.ws_url}")
            
            # Get automation endpoint (CDP WebSocket URL with auth)
            automation_response = self.bedrock_agentcore_client.get_automation_endpoint(
                browserId=self.browser_id,
                sessionId=self.session_id
            )
            
            return {
                'browser_id': self.browser_id,
                'session_id': self.session_id,
                'ws_url': automation_response.get('webSocketUrl', self.ws_url),
                'headers': automation_response.get('headers', {})
            }
            
        except Exception as e:
            print(f"Error creating browser session: {e}")
            # Fallback to constructing WebSocket URL manually
            if self.browser_id and self.session_id:
                return {
                    'browser_id': self.browser_id,
                    'session_id': self.session_id,
                    'ws_url': self.ws_url,
                    'headers': {}
                }
            raise

    def _get_browser_and_page(self) -> Tuple[Browser, Page]:
        """
        Create an AgentCore browser session and connect to it via CDP.

        Returns:
            Tuple[Browser, Page]: A tuple containing the connected browser and page objects.
        """
        # Create browser session
        session_info = self._create_browser_session()
        ws_url = session_info['ws_url']
        headers = session_info.get('headers', {})
        
        print(f"\nConnecting to AgentCore Browser via CDP...")
        print(f"Browser ID: {self.browser_id}")
        print(f"Session ID: {self.session_id}")
        
        # Connect to the remote browser session using CDP
        # Convert headers dict to the format Playwright expects
        connect_options = {
            'timeout': 60000,
        }
        
        if headers:
            # Add authorization headers if provided
            connect_options['headers'] = headers
        
        browser = self._playwright.chromium.connect_over_cdp(
            ws_url, 
            **connect_options
        )
        
        # Get the default context and page
        context = browser.contexts[0]
        
        # Add event listeners for page creation and closure
        context.on("page", self._handle_new_page)
        
        # Add virtual mouse cursor if enabled
        if self.virtual_mouse:
            self._add_virtual_mouse_cursor(context)
        
        # Get or create initial page
        page = context.pages[0] if context.pages else context.new_page()
        page.on("close", self._handle_page_close)
        
        # Navigate to initial URL
        try:
            page.goto("https://www.bing.com", timeout=30000)
            print("✓ Connected to AgentCore Browser successfully!")
        except Exception as e:
            print(f"Warning: Could not navigate to initial URL: {e}")
        
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
                        backgroundImage: 'url("data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 24 24\\' fill=\\'black\\' stroke=\\'white\\' stroke-width=\\'1\\' stroke-linejoin=\\'round\\' stroke-linecap=\\'round\\'><polygon points=\\'2,2 2,22 8,16 14,22 17,19 11,13 22,11\\'/></svg>")',
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

        # Clean up AgentCore session
        if self.bedrock_agentcore_client and self.session_id and self.browser_id:
            try:
                print(f"\nCleaning up AgentCore Browser session...")
                self.bedrock_agentcore_client.delete_browser_session(
                    browserId=self.browser_id,
                    sessionId=self.session_id
                )
                print(f"✓ Session {self.session_id} deleted")
            except Exception as e:
                print(f"Warning: Could not delete browser session: {e}")
        
        if self.bedrock_agentcore_client and self.browser_id:
            try:
                self.bedrock_agentcore_client.delete_browser(
                    browserId=self.browser_id
                )
                print(f"✓ Browser {self.browser_id} deleted")
            except Exception as e:
                print(f"Warning: Could not delete browser: {e}")
        
        print("✓ AgentCore Browser cleanup complete")
