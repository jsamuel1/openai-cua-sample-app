"""
Unit tests for the AgentCore Browser implementation.

Note: These tests check the structure and basic functionality.
Integration tests with actual AWS credentials are not included
to avoid unexpected charges during automated testing.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from computers.contrib.agentcore_browser import AgentCoreBrowser


class TestAgentCoreBrowserStructure(unittest.TestCase):
    """Test the structure and initialization of AgentCoreBrowser."""
    
    def test_class_exists(self):
        """Test that AgentCoreBrowser class exists."""
        self.assertTrue(hasattr(AgentCoreBrowser, '__init__'))
    
    def test_default_initialization_parameters(self):
        """Test that default parameters are set correctly."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser()
                
                self.assertEqual(browser.dimensions, (1024, 768))
                self.assertEqual(browser.region, "us-east-1")
                self.assertTrue(browser.virtual_mouse)
                self.assertEqual(browser.session_timeout, 3600)
    
    def test_custom_initialization_parameters(self):
        """Test that custom parameters are set correctly."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser(
                    width=1920,
                    height=1080,
                    region="eu-west-1",
                    virtual_mouse=False,
                    session_timeout=7200
                )
                
                self.assertEqual(browser.dimensions, (1920, 1080))
                self.assertEqual(browser.region, "eu-west-1")
                self.assertFalse(browser.virtual_mouse)
                self.assertEqual(browser.session_timeout, 7200)
    
    def test_get_environment(self):
        """Test that get_environment returns 'browser'."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser()
                self.assertEqual(browser.get_environment(), "browser")
    
    def test_get_dimensions(self):
        """Test that get_dimensions returns correct dimensions."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser(width=1280, height=720)
                self.assertEqual(browser.get_dimensions(), (1280, 720))


class TestAgentCoreBrowserMethods(unittest.TestCase):
    """Test the methods of AgentCoreBrowser."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.boto3_patcher = patch('computers.contrib.agentcore_browser.boto3.Session')
        self.mock_boto3 = self.boto3_patcher.start()
        
        self.init_aws_patcher = patch.object(AgentCoreBrowser, '_initialize_aws_client')
        self.mock_init_aws = self.init_aws_patcher.start()
        
        self.browser = AgentCoreBrowser()
    
    def tearDown(self):
        """Clean up patches."""
        self.boto3_patcher.stop()
        self.init_aws_patcher.stop()
    
    def test_has_required_computer_methods(self):
        """Test that all required Computer interface methods exist."""
        required_methods = [
            'get_environment',
            'get_dimensions',
            'screenshot',
            'click',
            'double_click',
            'scroll',
            'type',
            'wait',
            'move',
            'keypress',
            'drag',
            'get_current_url'
        ]
        
        for method in required_methods:
            self.assertTrue(
                hasattr(self.browser, method),
                f"AgentCoreBrowser missing required method: {method}"
            )
    
    def test_has_browser_specific_methods(self):
        """Test that browser-specific methods exist."""
        browser_methods = ['goto', 'back', 'forward']
        
        for method in browser_methods:
            self.assertTrue(
                hasattr(self.browser, method),
                f"AgentCoreBrowser missing browser method: {method}"
            )
    
    def test_context_manager_methods(self):
        """Test that context manager methods exist."""
        self.assertTrue(hasattr(self.browser, '__enter__'))
        self.assertTrue(hasattr(self.browser, '__exit__'))


class TestAgentCoreBrowserAWSIntegration(unittest.TestCase):
    """Test AWS integration aspects (mocked)."""
    
    def test_initialize_aws_client_with_env_vars(self):
        """Test AWS client initialization with environment variables."""
        with patch.dict(os.environ, {
            'AWS_ACCESS_KEY_ID': 'test_key',
            'AWS_SECRET_ACCESS_KEY': 'test_secret',
            'AWS_SESSION_TOKEN': 'test_token'
        }):
            with patch('computers.contrib.agentcore_browser.boto3.Session') as mock_session:
                mock_client = Mock()
                mock_session.return_value.client.return_value = mock_client
                
                browser = AgentCoreBrowser()
                
                # Verify Session was called with credentials
                mock_session.assert_called_once()
                call_kwargs = mock_session.call_args[1]
                self.assertEqual(call_kwargs['aws_access_key_id'], 'test_key')
                self.assertEqual(call_kwargs['aws_secret_access_key'], 'test_secret')
                self.assertEqual(call_kwargs['aws_session_token'], 'test_token')
    
    def test_create_browser_session_structure(self):
        """Test that _create_browser_session has correct structure."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser()
                
                # Mock the bedrock client
                mock_client = Mock()
                browser.bedrock_agentcore_client = mock_client
                
                # Mock responses
                mock_client.create_browser.return_value = {'browserId': 'test-browser-id'}
                mock_client.create_browser_session.return_value = {'sessionId': 'test-session-id'}
                mock_client.get_automation_endpoint.return_value = {
                    'webSocketUrl': 'wss://test-url',
                    'headers': {'Authorization': 'Bearer test-token'}
                }
                
                # Call method
                result = browser._create_browser_session()
                
                # Verify result structure
                self.assertIn('browser_id', result)
                self.assertIn('session_id', result)
                self.assertIn('ws_url', result)
                self.assertIn('headers', result)
                
                # Verify API calls were made
                mock_client.create_browser.assert_called_once()
                mock_client.create_browser_session.assert_called_once()
                mock_client.get_automation_endpoint.assert_called_once()


class TestAgentCoreBrowserScreenshot(unittest.TestCase):
    """Test screenshot functionality."""
    
    def test_screenshot_method_exists(self):
        """Test that screenshot method exists and has correct signature."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser()
                
                self.assertTrue(hasattr(browser, 'screenshot'))
                self.assertTrue(callable(browser.screenshot))


class TestAgentCoreBrowserConfig(unittest.TestCase):
    """Test that AgentCoreBrowser is properly configured in the system."""
    
    def test_agentcore_in_computers_config(self):
        """Test that AgentCoreBrowser is registered in computers config."""
        from computers.config import computers_config
        
        self.assertIn('agentcore-browser', computers_config)
        self.assertEqual(computers_config['agentcore-browser'], AgentCoreBrowser)
    
    def test_agentcore_in_contrib_init(self):
        """Test that AgentCoreBrowser is exported from contrib module."""
        from computers.contrib import AgentCoreBrowser as ImportedBrowser
        
        self.assertEqual(ImportedBrowser, AgentCoreBrowser)


class TestAgentCoreBrowserDocumentation(unittest.TestCase):
    """Test that proper documentation exists."""
    
    def test_class_has_docstring(self):
        """Test that class has docstring."""
        self.assertIsNotNone(AgentCoreBrowser.__doc__)
        self.assertIn("Amazon Bedrock AgentCore", AgentCoreBrowser.__doc__)
    
    def test_init_has_docstring(self):
        """Test that __init__ method has docstring."""
        self.assertIsNotNone(AgentCoreBrowser.__init__.__doc__)
    
    def test_important_methods_have_docstrings(self):
        """Test that important methods have docstrings."""
        with patch('computers.contrib.agentcore_browser.boto3.Session'):
            with patch.object(AgentCoreBrowser, '_initialize_aws_client'):
                browser = AgentCoreBrowser()
                
                important_methods = [
                    '_initialize_aws_client',
                    '_create_browser_session',
                    '_get_browser_and_page',
                    'screenshot',
                    '__exit__'
                ]
                
                for method_name in important_methods:
                    method = getattr(browser, method_name)
                    self.assertIsNotNone(
                        method.__doc__,
                        f"Method {method_name} is missing docstring"
                    )


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCoreBrowserStructure))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCoreBrowserMethods))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCoreBrowserAWSIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCoreBrowserScreenshot))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCoreBrowserConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentCoreBrowserDocumentation))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
