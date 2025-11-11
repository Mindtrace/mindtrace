#!/usr/bin/env python3
"""
Simple CLI for running camera test scenarios.

Usage:
    python run_test.py --list                    # List available tests
    python run_test.py --config smoke_test       # Run smoke test
    python run_test.py --config capture_stress   # Run capture stress test
"""

import argparse
import asyncio
import sys

from mindtrace.hardware.test_suite.cameras.config_loader import list_available_configs
from mindtrace.hardware.test_suite.cameras.scenario_factory import create_scenario_from_config
from mindtrace.hardware.test_suite.core.monitor import HardwareMonitor
from mindtrace.hardware.test_suite.core.runner import HardwareTestRunner


async def run_test(config_name: str):
    """
    Run a test scenario from config file.

    Args:
        config_name: Name of config file
    """
    try:
        # Create scenario from config
        print(f"\n📋 Loading configuration: {config_name}")
        scenario = create_scenario_from_config(config_name)

        print(f"✅ Scenario loaded: {scenario.name}")
        print(f"   Description: {scenario.description}")
        print(f"   API URL: {scenario.api_base_url}")
        print(f"   Operations: {len(scenario.operations)}")
        print(f"   Estimated duration: {scenario.estimate_duration():.1f}s")
        print(f"   Total timeout: {scenario.total_timeout}s")
        print(f"   Expected success rate: {scenario.expected_success_rate:.1%}")

        # Confirm execution
        print("\n🚀 Starting test execution...")

        # Execute scenario
        async with HardwareTestRunner(api_base_url=scenario.api_base_url) as runner:
            monitor = HardwareMonitor(scenario.name)
            result = await runner.execute_scenario(scenario, monitor)

            # Print results
            print("\n" + "=" * 70)
            monitor.print_summary()

            # Overall result
            if result.status.value == "completed":
                if result.success_rate >= scenario.expected_success_rate:
                    print("\n✅ TEST PASSED")
                    print(f"   Success rate: {result.success_rate:.1%} (>= {scenario.expected_success_rate:.1%})")
                    return 0
                else:
                    print("\n⚠️  TEST COMPLETED WITH WARNINGS")
                    print(f"   Success rate: {result.success_rate:.1%} (< {scenario.expected_success_rate:.1%})")
                    return 1
            else:
                print("\n❌ TEST FAILED")
                print(f"   Status: {result.status.value}")
                if result.error:
                    print(f"   Error: {result.error}")
                return 2

    except FileNotFoundError as e:
        print(f"\n❌ Configuration not found: {e}")
        print("\n💡 Available configurations:")
        for cfg in list_available_configs():
            print(f"   - {cfg}")
        return 3

    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        import traceback

        traceback.print_exc()
        return 4


def list_configs():
    """List all available test configurations."""
    print("\n📋 Available Test Configurations:\n")

    configs = list_available_configs()

    for config_name in configs:
        try:
            scenario = create_scenario_from_config(config_name)
            print(f"  {config_name}")
            print(f"    Description: {scenario.description}")
            print(f"    Duration: ~{scenario.estimate_duration():.0f}s")
            print(f"    Tags: {', '.join(scenario.tags)}")
            print()
        except Exception as e:
            print(f"  {config_name} (error loading: {e})")
            print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Camera Test Suite - Run stress tests on camera hardware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available tests
  python run_test.py --list

  # Run smoke test
  python run_test.py --config smoke_test

  # Run capture stress test
  python run_test.py --config capture_stress

  # Run multi-camera test
  python run_test.py --config multi_camera
        """,
    )

    parser.add_argument("--list", "-l", action="store_true", help="List all available test configurations")

    parser.add_argument(
        "--config", "-c", type=str, help="Name of test configuration to run (e.g., smoke_test, capture_stress)"
    )

    args = parser.parse_args()

    # Handle list command
    if args.list:
        list_configs()
        return 0

    # Handle run command
    if args.config:
        exit_code = asyncio.run(run_test(args.config))
        sys.exit(exit_code)

    # No arguments - show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
