"""
Example script demonstrating the Amazon Bedrock AgentCore Browser implementation.

This example shows how to:
1. Initialize the AgentCore Browser
2. Navigate to a website
3. Take a screenshot
4. Perform basic interactions

Prerequisites:
- AWS credentials configured (see AGENTCORE_BROWSER_GUIDE.md)
- Required packages installed (boto3, playwright, etc.)
"""

import os
import base64
from computers.contrib.agentcore_browser import AgentCoreBrowser
from agent import Agent


def save_screenshot(screenshot_b64: str, filename: str = "screenshot.png"):
    """Save a base64 encoded screenshot to a file."""
    screenshot_bytes = base64.b64decode(screenshot_b64)
    with open(filename, "wb") as f:
        f.write(screenshot_bytes)
    print(f"Screenshot saved to {filename}")


def example_basic_navigation():
    """Basic example: Navigate and take screenshot."""
    print("\n=== Example 1: Basic Navigation ===\n")
    
    try:
        with AgentCoreBrowser(width=1280, height=720, region="us-east-1") as computer:
            print("Browser initialized successfully!")
            
            # Navigate to a website
            print("\nNavigating to example.com...")
            computer.goto("https://example.com")
            computer.wait(2000)  # Wait 2 seconds
            
            # Take a screenshot
            print("Taking screenshot...")
            screenshot = computer.screenshot()
            save_screenshot(screenshot, "example_navigation.png")
            
            # Get current URL
            current_url = computer.get_current_url()
            print(f"Current URL: {current_url}")
            
            print("\n✓ Example completed successfully!")
            
    except Exception as e:
        print(f"Error in example: {e}")


def example_with_agent():
    """Example using the Agent class with AgentCore Browser."""
    print("\n=== Example 2: Using Agent Class ===\n")
    
    try:
        with AgentCoreBrowser(width=1024, height=768, region="us-east-1") as computer:
            # Create agent with the browser computer
            agent = Agent(computer=computer)
            
            # Define a simple task
            task = "Navigate to wikipedia.org and take a screenshot"
            print(f"Task: {task}\n")
            
            # Note: This example shows the setup. Actual agent execution
            # requires OpenAI API key and may perform actions.
            print("Agent created successfully!")
            print("(Skipping actual agent.run() to avoid API usage)")
            
            # Manual navigation for demonstration
            computer.goto("https://www.wikipedia.org")
            computer.wait(3000)
            
            screenshot = computer.screenshot()
            save_screenshot(screenshot, "example_wikipedia.png")
            
            print("\n✓ Example completed successfully!")
            
    except Exception as e:
        print(f"Error in example: {e}")


def example_mouse_interactions():
    """Example demonstrating mouse interactions."""
    print("\n=== Example 3: Mouse Interactions ===\n")
    
    try:
        with AgentCoreBrowser(
            width=1280, 
            height=720, 
            region="us-east-1",
            virtual_mouse=True  # Enable virtual cursor
        ) as computer:
            print("Browser initialized with virtual mouse!")
            
            # Navigate to a simple page
            computer.goto("https://example.com")
            computer.wait(2000)
            
            # Move mouse to center of screen
            print("Moving mouse to center...")
            width, height = computer.get_dimensions()
            computer.move(width // 2, height // 2)
            computer.wait(1000)
            
            # Click at current position
            print("Clicking at center...")
            computer.click(width // 2, height // 2)
            computer.wait(1000)
            
            # Scroll down
            print("Scrolling down...")
            computer.scroll(width // 2, height // 2, 0, 200)
            computer.wait(1000)
            
            # Take final screenshot
            screenshot = computer.screenshot()
            save_screenshot(screenshot, "example_interactions.png")
            
            print("\n✓ Example completed successfully!")
            
    except Exception as e:
        print(f"Error in example: {e}")


def example_custom_region():
    """Example using a different AWS region."""
    print("\n=== Example 4: Custom Region ===\n")
    
    try:
        # Use a different region (change to your preferred region)
        with AgentCoreBrowser(
            width=1024,
            height=768,
            region="us-west-2",  # West Coast region
            session_timeout=1800  # 30 minutes
        ) as computer:
            print(f"Browser initialized in region: us-west-2")
            
            computer.goto("https://aws.amazon.com")
            computer.wait(2000)
            
            screenshot = computer.screenshot()
            save_screenshot(screenshot, "example_custom_region.png")
            
            print("\n✓ Example completed successfully!")
            
    except Exception as e:
        print(f"Error in example: {e}")


def main():
    """Run all examples."""
    print("=" * 60)
    print("Amazon Bedrock AgentCore Browser - Examples")
    print("=" * 60)
    
    # Check for AWS credentials
    if not (os.getenv("AWS_ACCESS_KEY_ID") or os.path.exists(os.path.expanduser("~/.aws/credentials"))):
        print("\n⚠️  WARNING: AWS credentials not detected!")
        print("Please configure AWS credentials before running these examples.")
        print("See AGENTCORE_BROWSER_GUIDE.md for setup instructions.\n")
        return
    
    # Run examples
    try:
        example_basic_navigation()
        
        # Uncomment to run additional examples
        # example_with_agent()
        # example_mouse_interactions()
        # example_custom_region()
        
    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user.")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
