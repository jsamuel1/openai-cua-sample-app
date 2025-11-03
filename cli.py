import argparse
from agent.agent import Agent
from computers.config import *
from computers.default import *
from computers import computers_config


def acknowledge_safety_check_callback(message: str) -> bool:
    response = input(
        f"Safety Check Warning: {message}\nDo you want to acknowledge and proceed? (y/n): "
    ).lower()
    return response.lower().strip() == "y"


def main():
    parser = argparse.ArgumentParser(
        description="Select a computer environment from the available options."
    )
    parser.add_argument(
        "--computer",
        choices=computers_config.keys(),
        help="Choose the computer environment to use.",
        default="local-playwright",
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Initial input to use instead of asking the user.",
        default=None,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode for detailed output.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show images during the execution.",
    )
    parser.add_argument(
        "--start-url",
        type=str,
        help="Start the browsing session with a specific URL (only for browser environments).",
        default="https://bing.com",
    )
    
    # AgentCore Browser specific arguments
    # Note: Parameter names match AgentCoreBrowser.__init__ for easy passing
    parser.add_argument(
        "--region",
        type=str,
        help="AWS region for AgentCore Browser (default: us-east-1). Only used with agentcore-browser.",
        default="us-east-1",
        dest="agentcore_region",
    )
    parser.add_argument(
        "--recording-s3-bucket",
        type=str,
        help="S3 bucket name for AgentCore Browser session recordings. Only used with agentcore-browser.",
        default=None,
        dest="recording_s3_bucket",
    )
    parser.add_argument(
        "--recording-s3-prefix",
        type=str,
        help="S3 prefix for AgentCore Browser recordings (default: browser-recordings). Only used with agentcore-browser.",
        default="browser-recordings",
        dest="recording_s3_prefix",
    )
    parser.add_argument(
        "--no-browser-signing",
        action="store_true",
        help="Disable Web Bot Auth signing (enabled by default to reduce CAPTCHAs). Only used with agentcore-browser.",
        dest="no_browser_signing",
    )
    
    args = parser.parse_args()
    ComputerClass = computers_config[args.computer]

    # Prepare computer-specific kwargs
    computer_kwargs = {}
    
    if args.computer == "agentcore-browser":
        # Parameter names match AgentCoreBrowser.__init__ for direct passing
        computer_kwargs = {
            "region": args.agentcore_region,
            "no_browser_signing": args.no_browser_signing,
            "recording_s3_bucket": args.recording_s3_bucket,
            "recording_s3_prefix": args.recording_s3_prefix,
        }

    with ComputerClass(**computer_kwargs) as computer:
        agent = Agent(
            computer=computer,
            acknowledge_safety_check_callback=acknowledge_safety_check_callback,
        )
        items = []

        if args.computer in ["browserbase", "local-playwright", "agentcore-browser"]:
            if not args.start_url.startswith("http"):
                args.start_url = "https://" + args.start_url
            agent.computer.goto(args.start_url)

        while True:
            try:
                user_input = args.input or input("> ")
                if user_input == "exit":
                    break
            except EOFError as e:
                print(f"An error occurred: {e}")
                break
            items.append({"role": "user", "content": user_input})
            output_items = agent.run_full_turn(
                items,
                print_steps=True,
                show_images=args.show,
                debug=args.debug,
            )
            items += output_items
            args.input = None


if __name__ == "__main__":
    main()
