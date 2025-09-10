#!/usr/bin/env python3
"""
E2E Test Runner for MTG Deckbuilder (M3: Cypress/Playwright Smoke Tests)

This script sets up and runs end-to-end tests for the web UI.
It can start the development server if needed and run smoke tests.

Usage:
    python run_e2e_tests.py --smoke                    # Run smoke tests only
    python run_e2e_tests.py --full                     # Run all tests
    python run_e2e_tests.py --mobile                   # Run mobile tests only
    python run_e2e_tests.py --start-server             # Start dev server then run tests
"""

import argparse
import asyncio
import subprocess
import sys
import os
import time
from pathlib import Path

class E2ETestRunner:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.server_process = None
        self.base_url = os.getenv('TEST_BASE_URL', 'http://localhost:8080')
        
    def start_dev_server(self):
        """Start the development server"""
        print("Starting development server...")
        
        # Try to start the web server
        server_cmd = [
            sys.executable, 
            "-m", "uvicorn",
            "code.web.app:app",
            "--host", "0.0.0.0",
            "--port", "8080",
            "--reload"
        ]
        
        try:
            self.server_process = subprocess.Popen(
                server_cmd,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for server to start
            print("Waiting for server to start...")
            time.sleep(5)
            
            # Check if server is running
            if self.server_process.poll() is None:
                print(f"✓ Server started at {self.base_url}")
                return True
            else:
                print("❌ Failed to start server")
                return False
                
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            return False
    
    def stop_dev_server(self):
        """Stop the development server"""
        if self.server_process:
            print("Stopping development server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            print("✓ Server stopped")
    
    def install_playwright(self):
        """Install Playwright browsers if needed"""
        print("Installing Playwright browsers...")
        try:
            subprocess.run([
                sys.executable, "-m", "playwright", "install", "chromium"
            ], check=True, cwd=self.project_root)
            print("✓ Playwright browsers installed")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install Playwright browsers: {e}")
            return False
    
    def run_tests(self, test_type="smoke"):
        """Run the specified tests"""
        print(f"Running {test_type} tests...")
        
        test_dir = self.project_root / "tests" / "e2e"
        if not test_dir.exists():
            print(f"❌ Test directory not found: {test_dir}")
            return False
        
        # Build pytest command
        cmd = [sys.executable, "-m", "pytest", str(test_dir)]
        
        if test_type == "smoke":
            cmd.extend(["-m", "smoke", "-v"])
        elif test_type == "mobile":
            cmd.extend(["-m", "mobile", "-v"])
        elif test_type == "full":
            cmd.extend(["-v"])
        else:
            cmd.extend(["-v"])
        
        # Set environment variables
        env = os.environ.copy()
        env["TEST_BASE_URL"] = self.base_url
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, env=env)
            return result.returncode == 0
        except Exception as e:
            print(f"❌ Error running tests: {e}")
            return False
    
    def run_quick_smoke_test(self):
        """Run a quick smoke test without pytest"""
        print("Running quick smoke test...")
        
        try:
            # Import and run the smoke test function
            sys.path.insert(0, str(self.project_root))
            from tests.e2e.test_web_smoke import run_smoke_tests
            
            # Set the base URL
            os.environ["TEST_BASE_URL"] = self.base_url
            
            asyncio.run(run_smoke_tests())
            return True
            
        except Exception as e:
            print(f"❌ Quick smoke test failed: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Run E2E tests for MTG Deckbuilder")
    parser.add_argument("--smoke", action="store_true", help="Run smoke tests only")
    parser.add_argument("--full", action="store_true", help="Run all tests")
    parser.add_argument("--mobile", action="store_true", help="Run mobile tests only")
    parser.add_argument("--start-server", action="store_true", help="Start dev server before tests")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke test without pytest")
    parser.add_argument("--install-browsers", action="store_true", help="Install Playwright browsers")
    
    args = parser.parse_args()
    
    runner = E2ETestRunner()
    
    # Install browsers if requested
    if args.install_browsers:
        if not runner.install_playwright():
            sys.exit(1)
    
    # Start server if requested
    server_started = False
    if args.start_server:
        if not runner.start_dev_server():
            sys.exit(1)
        server_started = True
    
    try:
        # Determine test type
        if args.mobile:
            test_type = "mobile"
        elif args.full:
            test_type = "full"
        else:
            test_type = "smoke"
        
        # Run tests
        if args.quick:
            success = runner.run_quick_smoke_test()
        else:
            success = runner.run_tests(test_type)
        
        if success:
            print("🎉 All tests passed!")
            sys.exit(0)
        else:
            print("❌ Some tests failed!")
            sys.exit(1)
            
    finally:
        # Clean up
        if server_started:
            runner.stop_dev_server()

if __name__ == "__main__":
    main()
