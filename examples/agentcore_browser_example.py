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
import boto3
from botocore.exceptions import ClientError, CredentialRetrievalError
import botocore.session
from computers.contrib.agentcore_browser import AgentCoreBrowser 
from agent import Agent

def main():
    try:
        with AgentCoreBrowser(width=1024, height=768, region="us-east-1") as computer:
            # Create agent with the browser computer
            agent = Agent(computer=computer)
            
            # Define a simple task
            task = "Navigate to wikipedia.org and take a screenshot"
            print(f"Task: {task}\n")
            agent.run_full_turn(task)
            
    except Exception as e:
        print(f"Error in example: {e}")


if __name__ == "__main__":
    main()
