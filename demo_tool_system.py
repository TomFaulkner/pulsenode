#!/usr/bin/env python3

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from pulsenode.agent.tools import (
    ToolExecutor,
    SecurityChecker,
    ApprovalManager,
    ToolRegistry,
    ToolCall,
)
from pulsenode.agent.agent_config import HttpConfig


async def demo_tool_system():
    """Demonstrate the tool system."""
    print("🔧 PulseNode Tool System Demo")
    print("=" * 50)

    # Use current directory for demo
    demo_dir = Path.cwd() / ".pulsenode_demo"

    try:
        # Initialize components
        print("1️⃣ Initializing tool system...")

        # Security checker
        security_checker = SecurityChecker(
            allowed_commands=["ls", "cat", "grep", "find", "python", "echo"],
            allowed_directories=[str(demo_dir)],
            access_home_directory=False,
        )

        # Approval manager (30 second timeout for demo)
        approval_manager = ApprovalManager(timeout_seconds=30)

        # HTTP config (allow all hosts for demo)
        http_config = HttpConfig(
            enabled=True,
            allowed_hosts=[],
            blocked_hosts=[],
            require_confirmation=False,
            default_timeout=30,
        )

        # Tool executor
        tool_executor = ToolExecutor(security_checker, approval_manager, http_config)

        # Tool registry
        tool_registry = ToolRegistry(tool_executor)

        print("✅ Tool system initialized")
        print()

        # Demonstrate tool parsing
        print("2️⃣ Demonstrating tool call parsing...")

        test_tool_calls = [
            '{"tool": "shell", "action": "exec", "command": "ls -la"}',
            '{"tool": "file", "action": "write", "path": "test.txt", "content": "Hello World!"}',
            '{"tool": "file", "action": "list", "path": "."}',
            '{"tool": "file", "action": "exists", "path": "test.txt"}',
        ]

        for i, tool_call_json in enumerate(test_tool_calls, 1):
            print(f"Test {i}: {tool_call_json}")

            # Parse tool call
            tool_call = tool_registry.parse_tool_call(tool_call_json)
            if tool_call:
                print(f"  ✓ Parsed: {tool_call.tool_type}.{tool_call.action}")
                print(f"  ✓ Args: {tool_call.args}")
            else:
                print("  ✗ Failed to parse")
            print()

        # Demonstrate safe tool execution
        print("3️⃣ Demonstrating safe tool execution...")

        # Create demo workspace
        workspace = demo_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        # File operations (safe)
        print("Testing file operations...")

        # Write a file
        write_call = ToolCall(
            tool_type="file",
            action="write",
            args={
                "path": str(workspace / "demo.txt"),
                "content": "Hello from tool system!",
            },
        )

        result = await tool_executor.execute_tool_call(write_call)
        print(f"  Write file: {'✅' if result.success else '❌'} {result.output[:50]}")
        if result.error:
            print(f"  Error: {result.error}")

        # List directory
        list_call = ToolCall(
            tool_type="file", action="list", args={"path": str(workspace)}
        )

        result = await tool_executor.execute_tool_call(list_call)
        print(f"  List directory: {'✅' if result.success else '❌'}")
        if result.success:
            for line in result.output.split("\n"):
                print(f"    {line}")

        # Read file
        read_call = ToolCall(
            tool_type="file", action="read", args={"path": str(workspace / "demo.txt")}
        )

        result = await tool_executor.execute_tool_call(read_call)
        print(f"  Read file: {'✅' if result.success else '❌'} {result.output[:50]}")

        # Check file exists
        exists_call = ToolCall(
            tool_type="file",
            action="exists",
            args={"path": str(workspace / "demo.txt")},
        )

        result = await tool_executor.execute_tool_call(exists_call)
        print(f"  Check exists: {'✅' if result.success else '❌'} {result.output}")

        print()

        # Demonstrate HTTP tool
        print("4️⃣ Demonstrating HTTP tool...")

        http_call = ToolCall(
            tool_type="http",
            action="request",
            args={
                "method": "GET",
                "url": "https://example.org",
            },
        )

        result = await tool_executor.execute_tool_call(http_call)
        print(f"  HTTP GET: {'✅' if result.success else '❌'}")
        if result.success:
            print(f"  Status: {result.output.split(chr(10))[0]}")
            print(f"  Body preview: {result.output.split(chr(10))[-1][:80]}...")
        if result.error:
            print(f"  Error: {result.error}")

        print()

        # Demonstrate dangerous tool (requires approval)
        print("5️⃣ Demonstrating approval-required operation...")

        # Try to access a sensitive file (will require approval)
        sensitive_call = ToolCall(
            tool_type="file",
            action="read",
            args={"path": str(workspace.parent / ".env")},
        )

        print("Attempting to read .env file (should require approval)...")
        result = await tool_executor.execute_tool_call(sensitive_call)
        print(f"  Sensitive file read: {'✅' if result.success else '❌'}")
        if result.error:
            print(f"  Error (expected): {result.error}")

        # Try a dangerous command
        dangerous_call = ToolCall(
            tool_type="shell",
            action="exec",
            args={"command": "rm -rf " + str(workspace)},
        )

        print("Attempting dangerous command (should require approval)...")
        result = await tool_executor.execute_tool_call(dangerous_call)
        print(f"  Dangerous command: {'✅' if result.success else '❌'}")
        if result.error:
            print(f"  Error (expected): {result.error}")

        # Show approval status
        print()
        print("6️⃣ Approval status:")
        pending = approval_manager.get_pending_requests()
        if pending:
            for request in pending:
                print(
                    f"  📋 Pending: {request.approval_id} - {request.tool_call.tool_type}.{request.tool_call.action}"
                )
        else:
            print("  ✅ No pending approvals")

        print()
        print("🎉 Tool system demo completed!")
        print(f"💾 Demo workspace: {workspace}")
        print("🧹 Clean up with: rm -rf ~/.pulsenode_demo")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(demo_tool_system())
